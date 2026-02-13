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
from fastapi.responses import JSONResponse, StreamingResponse

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
# Time Machine configuration
# ---------------------------------------------------------------------------

# When CVC_TIME_MACHINE=1 (set by ``cvc launch``), auto-commit fires much
# more aggressively — every 3 assistant turns instead of every 10.
_TIME_MACHINE_ENABLED: bool = os.environ.get("CVC_TIME_MACHINE", "0") == "1"
_TIME_MACHINE_INTERVAL: int = int(os.environ.get("CVC_TIME_MACHINE_INTERVAL", "3"))
_NORMAL_INTERVAL: int = int(os.environ.get("CVC_AUTO_COMMIT_INTERVAL", "10"))

# Session detection — if no traffic for this many seconds, new session
_SESSION_TIMEOUT: int = int(os.environ.get("CVC_SESSION_TIMEOUT", "1800"))  # 30 min


# ---------------------------------------------------------------------------
# Application state (module-level singletons, initialised in lifespan)
# ---------------------------------------------------------------------------

_config: CVCConfig | None = None
_db: ContextDatabase | None = None
_engine: CVCEngine | None = None
_adapter: BaseAdapter | None = None
_bridge: VCSBridge | None = None
_graph: Any = None  # Compiled LangGraph


# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------

class _SessionTracker:
    """Lightweight tracker for agent sessions going through the proxy."""

    def __init__(self) -> None:
        self.sessions: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._last_request_ts: float = 0.0

    def touch(self, *, tool_hint: str = "") -> dict[str, Any]:
        """
        Called on every inbound request.  Starts a new session if enough
        idle time has elapsed (Time Machine session splitting).
        """
        now = time.time()
        gap = now - self._last_request_ts if self._last_request_ts else 0
        self._last_request_ts = now

        if self._current is None or gap > _SESSION_TIMEOUT:
            # Archive previous session
            if self._current is not None:
                self._current["ended_at"] = now - gap
                self.sessions.append(self._current)

            self._current = {
                "id": len(self.sessions) + 1,
                "started_at": now,
                "ended_at": None,
                "tool": tool_hint or "unknown",
                "messages": 0,
                "commits": 0,
                "branch_at_start": "",
            }

        self._current["messages"] += 1
        if tool_hint and self._current["tool"] == "unknown":
            self._current["tool"] = tool_hint
        return self._current

    @property
    def current(self) -> dict[str, Any] | None:
        return self._current

    def record_commit(self) -> None:
        if self._current:
            self._current["commits"] += 1

    def all_sessions(self) -> list[dict[str, Any]]:
        result = list(self.sessions)
        if self._current:
            result.append({**self._current, "active": True})
        return result


_session_tracker = _SessionTracker()


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

    # Auth mode — determines whether CVC uses its own key or passes through
    # the client's auth header to the upstream provider.
    app.state.auth_mode = _config.auth_mode if hasattr(_config, 'auth_mode') else 'stored'
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

try:
    from cvc import __version__ as _cvc_version
except ImportError:
    _cvc_version = "1.1.4"

app = FastAPI(
    title="CVC — Cognitive Version Control Proxy",
    description="Git for the AI Mind. Intercepts LLM API calls and manages cognitive state.",
    version=_cvc_version,
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
async def chat_completions(raw_request: Request) -> JSONResponse:
    """
    The primary interception point.

    Every request from the agent (Cursor / VS Code / CLI) flows through here.
    The LangGraph state machine decides whether it's a CVC command or a
    standard generation.

    Supports auth pass-through: if the client sends an Authorization header,
    CVC can forward it to the upstream provider.
    """
    assert _engine is not None and _graph is not None and _adapter is not None

    body = await raw_request.json()
    request = ChatCompletionRequest(**body)

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
        auto_msg = _build_auto_commit_message()
        auto_result = _engine.commit(
            CVCCommitRequest(
                message=auto_msg,
                commit_type="checkpoint",
            )
        )
        if auto_result.success:
            _session_tracker.record_commit()
            logger.info("Auto-commit: %s", auto_result.commit_hash and auto_result.commit_hash[:12])

    return JSONResponse(content=response.model_dump())


def _should_auto_commit() -> bool:
    """
    Auto-commit heuristic.

    - **Time Machine mode** (``CVC_TIME_MACHINE=1``): commits every
      ``_TIME_MACHINE_INTERVAL`` assistant turns (default 3).
    - **Normal mode**: commits every ``_NORMAL_INTERVAL`` turns (default 10).
    """
    assert _engine is not None
    assistant_msgs = [m for m in _engine.context_window if m.role == "assistant"]
    count = len(assistant_msgs)
    if count == 0:
        return False
    interval = _TIME_MACHINE_INTERVAL if _TIME_MACHINE_ENABLED else _NORMAL_INTERVAL
    return count % interval == 0


def _build_auto_commit_message() -> str:
    """Generate a concise auto-commit message from recent context."""
    assert _engine is not None
    recent = [m for m in _engine.context_window if m.role in ("user", "assistant")]
    if not recent:
        return "Auto-checkpoint"
    # Use the last user message as summary hint
    last_user = next((m for m in reversed(recent) if m.role == "user"), None)
    if last_user:
        summary = last_user.content[:120].replace("\n", " ").strip()
        return f"Auto: {summary}"
    return f"Auto-checkpoint ({len(recent)} messages)"


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


@app.get("/cvc/sessions")
async def cvc_sessions() -> dict[str, Any]:
    """
    Return the session history — every contiguous period of tool-proxy
    interaction.  This powers ``cvc sessions`` and the Time Machine UI.
    """
    sessions = _session_tracker.all_sessions()
    return {
        "time_machine": _TIME_MACHINE_ENABLED,
        "auto_commit_interval": _TIME_MACHINE_INTERVAL if _TIME_MACHINE_ENABLED else _NORMAL_INTERVAL,
        "session_timeout_seconds": _SESSION_TIMEOUT,
        "total": len(sessions),
        "sessions": sessions,
    }


@app.get("/cvc/config")
async def cvc_runtime_config() -> dict[str, Any]:
    """Return the current proxy runtime configuration."""
    return {
        "time_machine": _TIME_MACHINE_ENABLED,
        "auto_commit_interval": _TIME_MACHINE_INTERVAL if _TIME_MACHINE_ENABLED else _NORMAL_INTERVAL,
        "session_timeout_seconds": _SESSION_TIMEOUT,
        "provider": _config.provider if _config else "unknown",
        "model": _config.model if _config else "unknown",
        "agent_id": _config.agent_id if _config else "unknown",
    }


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
    return {"status": "ok", "service": "cvc-proxy", "version": _cvc_version}


# ---------------------------------------------------------------------------
# Auth Pass-Through Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def auth_passthrough_middleware(request: Request, call_next):
    """
    When auth_mode is 'pass_through', extract the client's Bearer token
    (or x-api-key header) and stash it on request.state so downstream
    handlers can forward it to the upstream provider.

    Also tracks sessions and identifies the connecting tool from
    the User-Agent header (e.g. 'claude-code/1.x', 'aider/0.x').
    """
    # Extract client auth from the incoming request
    auth_header = request.headers.get("authorization", "")
    x_api_key = request.headers.get("x-api-key", "")
    request.state.client_api_key = ""
    request.state.client_bearer = ""

    if x_api_key:
        request.state.client_api_key = x_api_key
    if auth_header.lower().startswith("bearer "):
        request.state.client_bearer = auth_header[7:].strip()

    # Session tracking — detect tool from User-Agent
    ua = request.headers.get("user-agent", "").lower()
    tool_hint = ""
    if "claude" in ua:
        tool_hint = "claude"
    elif "aider" in ua:
        tool_hint = "aider"
    elif "codex" in ua:
        tool_hint = "codex"
    elif "cursor" in ua:
        tool_hint = "cursor"
    elif "copilot" in ua:
        tool_hint = "copilot"
    elif "gemini" in ua:
        tool_hint = "gemini"

    session = _session_tracker.touch(tool_hint=tool_hint)
    if _engine and not session.get("branch_at_start"):
        session["branch_at_start"] = _engine.active_branch

    return await call_next(request)


# ---------------------------------------------------------------------------
# Anthropic Messages API — Native Claude Code CLI Support
# ---------------------------------------------------------------------------

@app.post("/v1/messages")
async def anthropic_messages(request: Request) -> JSONResponse:
    """
    Anthropic-native Messages API endpoint.

    Claude Code CLI sends requests to ANTHROPIC_BASE_URL + '/v1/messages'
    using the Anthropic wire format (not OpenAI). This endpoint:

    1. Accepts the Anthropic Messages API format natively.
    2. Runs CVC interception (command detection, context enrichment).
    3. Forwards to the upstream Anthropic API (or configured provider).
    4. Returns the response in Anthropic Messages format.

    This means users can simply set:
        export ANTHROPIC_BASE_URL=http://127.0.0.1:8000
    and Claude Code CLI works with full CVC cognitive versioning.
    """
    assert _engine is not None and _config is not None

    body = await request.json()

    # --- Convert Anthropic format → internal OpenAI format ---
    messages_in = body.get("messages", [])
    system_text = body.get("system", "")

    # Build OpenAI-style messages list
    openai_messages: list[dict[str, Any]] = []
    if system_text:
        if isinstance(system_text, list):
            # Anthropic system can be a list of content blocks
            sys_parts = [b.get("text", "") for b in system_text if b.get("type") == "text"]
            system_text = "\n".join(sys_parts)
        openai_messages.append({"role": "system", "content": system_text})

    for msg in messages_in:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Anthropic content can be string or list of blocks
        if isinstance(content, list):
            text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            content = "\n".join(text_parts)
        openai_messages.append({"role": role, "content": content})

    # Build ChatCompletionRequest for the CVC pipeline
    internal_request = ChatCompletionRequest(
        model=body.get("model", _config.model),
        messages=[ChatMessage(**m) for m in openai_messages],
        temperature=body.get("temperature", 0.7),
        max_tokens=body.get("max_tokens", 4096),
    )

    # Convert tools if present
    anthropic_tools = body.get("tools", [])
    if anthropic_tools:
        # Convert Anthropic tool format → OpenAI tool format for CVC pipeline
        openai_tools = []
        for t in anthropic_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        internal_request.tools = openai_tools

    # --- Run through CVC state machine (same as /v1/chat/completions) ---
    assert _graph is not None
    initial_state: CVCGraphState = {
        "request": internal_request,
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

    # If CVC command, wrap result in Anthropic format
    if result_state.get("is_cvc_command") and result_state.get("cvc_result"):
        cvc_result: CVCOperationResponse = result_state["cvc_result"]
        return JSONResponse(content={
            "id": f"msg_cvc_{int(time.time())}",
            "type": "message",
            "role": "assistant",
            "model": internal_request.model,
            "content": [{
                "type": "text",
                "text": json.dumps(cvc_result.model_dump(), indent=2),
            }],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }, headers={"X-CVC-Operation": cvc_result.operation})

    # --- Forward to upstream Anthropic API ---
    # Use client's API key if available (pass-through), else use stored key
    client_api_key = getattr(request.state, 'client_api_key', '') or \
                     getattr(request.state, 'client_bearer', '')
    upstream_key = client_api_key or _config.api_key

    if not upstream_key:
        raise HTTPException(
            status_code=401,
            detail="No API key available. Either pass x-api-key / Authorization header, "
                   "or configure an API key via 'cvc setup'.",
        )

    import httpx
    headers = {
        "x-api-key": upstream_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    # Forward anthropic-beta if present
    beta = request.headers.get("anthropic-beta")
    if beta:
        headers["anthropic-beta"] = beta

    # Build the upstream body — pass through most fields as-is
    upstream_body = dict(body)
    # Inject CVC context enrichment
    committed_prefix_len = result_state.get("committed_prefix_len", 0)

    try:
        upstream_url = _config.upstream_base_url.rstrip("/")
        if _config.provider == "anthropic":
            upstream_url = "https://api.anthropic.com"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{upstream_url}/v1/messages",
                json=upstream_body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Upstream Anthropic error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    # Record assistant response in CVC context
    content_blocks = data.get("content", [])
    text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
    if text_parts:
        _engine.push_chat_message(ChatMessage(role="assistant", content="\n".join(text_parts)))

    return JSONResponse(content=data)


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
