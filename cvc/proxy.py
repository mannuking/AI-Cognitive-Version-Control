"""
cvc.proxy — The Cognitive Proxy (FastAPI Interceptor).

A local middleware service that sits between the agent (e.g., Cursor, VS Code,
or any OpenAI-compatible client) and the upstream LLM provider.  It:

1. Intercepts every request on an OpenAI-compatible API surface.
2. Routes it through the LangGraph state machine to detect CVC commands.
3. For CVC commands: executes the operation and returns the result.
4. For generation: enriches the prompt with committed context, injects
   cache-control headers, and proxies to the upstream provider.
5. Records the assistant response in the context window.
6. Auto-commits at configurable intervals.

Runs on ``http://127.0.0.1:8000`` by default.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cvc.adapters import BaseAdapter, create_adapter
from cvc.core.database import ContextDatabase
from cvc.core.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CVCBranchRequest,
    CVCCommitRequest,
    CVCConfig,
    CVCMergeRequest,
    CVCOperationResponse,
    CVCRestoreRequest,
    UsageInfo,
)
from cvc.operations.engine import CVCEngine
from cvc.operations.state_machine import CVC_TOOLS, CVCGraphState, build_cvc_graph
from cvc.vcs.bridge import VCSBridge

logger = logging.getLogger("cvc.proxy")


# ---------------------------------------------------------------------------
# Application state (module-level singletons, initialised in lifespan)
# ---------------------------------------------------------------------------

_config: CVCConfig | None = None
_db: ContextDatabase | None = None
_engine: CVCEngine | None = None
_adapter: BaseAdapter | None = None
_bridge: VCSBridge | None = None
_graph: Any = None  # Compiled LangGraph


def _load_config() -> CVCConfig:
    """Build configuration using the unified project discovery + global config system."""
    return CVCConfig.for_project()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all CVC subsystems on startup, tear down on shutdown."""
    global _config, _db, _engine, _adapter, _bridge, _graph

    _config = _load_config()
    _config.ensure_dirs()

    _db = ContextDatabase(_config)
    _engine = CVCEngine(_config, _db)
    _adapter = create_adapter(
        provider=_config.provider,
        api_key=_config.api_key,
        model=_config.model,
        base_url=_config.upstream_base_url,
    )
    _bridge = VCSBridge(_config, _db)

    # Build and compile the LangGraph state machine
    graph_builder = build_cvc_graph(_engine)
    _graph = graph_builder.compile()

    logger.info(
        "CVC Proxy started — agent=%s branch=%s provider=%s model=%s",
        _config.agent_id,
        _config.default_branch,
        _config.provider,
        _config.model,
    )

    yield

    # Teardown
    if _adapter:
        await _adapter.close()
    if _db:
        _db.close()
    logger.info("CVC Proxy shut down.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CVC — Cognitive Version Control Proxy",
    description="Git for the AI Mind. Intercepts LLM API calls and manages cognitive state.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# OpenAI-Compatible Chat Completions Endpoint (The Interceptor)
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    """
    The primary interception point.

    Every request from the agent (Cursor / VS Code / CLI) flows through here.
    The LangGraph state machine decides whether it's a CVC command or a
    standard generation.
    """
    assert _engine is not None and _graph is not None and _adapter is not None

    # 1. Run the request through the LangGraph state machine
    initial_state: CVCGraphState = {
        "request": request,
        "is_cvc_command": False,
        "cvc_tool_name": "",
        "cvc_tool_args": {},
        "response": None,
        "cvc_result": None,
        "active_branch": _engine.active_branch,
        "head_hash": _engine.head_hash or "",
        "committed_prefix_len": 0,
    }

    result_state = _graph.invoke(initial_state)

    # 2. If it was a CVC command, return the operation result directly
    if result_state.get("is_cvc_command") and result_state.get("cvc_result"):
        cvc_result: CVCOperationResponse = result_state["cvc_result"]
        # Wrap in a chat-completion envelope so the client can parse it
        wrapped = ChatCompletionResponse(
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(
                        role="assistant",
                        content=json.dumps(cvc_result.model_dump(), indent=2),
                    ),
                    finish_reason="stop",
                )
            ],
        )
        return JSONResponse(
            content=wrapped.model_dump(),
            headers={"X-CVC-Operation": cvc_result.operation},
        )

    # 3. Standard generation — proxy to upstream provider
    committed_prefix_len = result_state.get("committed_prefix_len", 0)

    try:
        response = await _adapter.complete(
            request, committed_prefix_len=committed_prefix_len
        )
    except Exception as exc:
        logger.error("Upstream provider error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    # 4. Record the assistant response in the context window
    if response.choices:
        assistant_msg = response.choices[0].message
        _engine.push_chat_message(assistant_msg)

        # Log cache performance
        if response.usage.cache_read_tokens > 0:
            logger.info(
                "Cache HIT: %d tokens read from cache (%.1f%% of prompt)",
                response.usage.cache_read_tokens,
                (response.usage.cache_read_tokens / max(response.usage.prompt_tokens, 1)) * 100,
            )

    # 5. Auto-commit if enabled
    if request.cvc_auto_commit and _should_auto_commit():
        auto_result = _engine.commit(
            CVCCommitRequest(
                message=f"Auto-checkpoint after {len(_engine.context_window)} messages",
                commit_type="checkpoint",
            )
        )
        if auto_result.success:
            response.model_dump()  # Ensure serialisable
            logger.info("Auto-commit: %s", auto_result.commit_hash and auto_result.commit_hash[:12])

    return JSONResponse(content=response.model_dump())


def _should_auto_commit() -> bool:
    """Heuristic: auto-commit every 10 assistant turns."""
    assert _engine is not None
    assistant_msgs = [m for m in _engine.context_window if m.role == "assistant"]
    return len(assistant_msgs) > 0 and len(assistant_msgs) % 10 == 0


# ---------------------------------------------------------------------------
# CVC Control Endpoints (Direct REST — alternative to function-calling)
# ---------------------------------------------------------------------------

@app.post("/cvc/commit", response_model=CVCOperationResponse)
async def cvc_commit_endpoint(request: CVCCommitRequest) -> CVCOperationResponse:
    assert _engine is not None
    return _engine.commit(request)


@app.post("/cvc/branch", response_model=CVCOperationResponse)
async def cvc_branch_endpoint(request: CVCBranchRequest) -> CVCOperationResponse:
    assert _engine is not None
    return _engine.branch(request)


@app.post("/cvc/merge", response_model=CVCOperationResponse)
async def cvc_merge_endpoint(request: CVCMergeRequest) -> CVCOperationResponse:
    assert _engine is not None
    return _engine.merge(request)


@app.post("/cvc/restore", response_model=CVCOperationResponse)
async def cvc_restore_endpoint(request: CVCRestoreRequest) -> CVCOperationResponse:
    assert _engine is not None
    return _engine.restore(request)


@app.get("/cvc/status")
async def cvc_status() -> dict[str, Any]:
    """Current CVC state: active branch, HEAD, branch list."""
    assert _engine is not None and _db is not None
    branches = _db.index.list_branches()
    return {
        "agent_id": _engine.config.agent_id,
        "active_branch": _engine.active_branch,
        "head_hash": _engine.head_hash,
        "context_size": len(_engine.context_window),
        "branches": [
            {
                "name": b.name,
                "head": b.head_hash[:12],
                "status": b.status.value,
            }
            for b in branches
        ],
    }


@app.get("/cvc/log")
async def cvc_log(limit: int = 20) -> dict[str, Any]:
    """Commit log for the active branch."""
    assert _engine is not None
    return {
        "branch": _engine.active_branch,
        "commits": _engine.log(limit=limit),
    }


@app.get("/cvc/search")
async def cvc_search(query: str, n: int = 5) -> dict[str, Any]:
    """Semantic search over commit summaries (Tier 3)."""
    assert _db is not None
    return {
        "query": query,
        "results": _db.search_similar(query, n=n),
    }


@app.get("/cvc/tools")
async def cvc_tools() -> list[dict[str, Any]]:
    """Return CVC tool definitions for function-calling / MCP integration."""
    return CVC_TOOLS


# ---------------------------------------------------------------------------
# VCS Bridge endpoints
# ---------------------------------------------------------------------------

@app.post("/cvc/vcs/capture")
async def vcs_capture(git_sha: str | None = None) -> dict[str, Any]:
    """Capture a CVC snapshot linked to the current Git commit."""
    assert _bridge is not None
    return _bridge.capture_snapshot(git_sha)


@app.post("/cvc/vcs/install-hooks")
async def vcs_install_hooks() -> dict[str, str]:
    """Install Git hooks for CVC synchronisation."""
    assert _bridge is not None
    return _bridge.install_hooks()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "cvc-proxy", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# OpenAI-Compatible Model Discovery
# ---------------------------------------------------------------------------

@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """
    OpenAI-compatible model listing endpoint.

    Tools like Cursor, Cline, Continue.dev, and Open WebUI query this
    endpoint to auto-discover available models.  We return the model
    configured in the CVC proxy.
    """
    assert _config is not None
    model_id = _config.model
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": f"cvc-proxy ({_config.provider})",
                "permission": [],
            }
        ],
    }
