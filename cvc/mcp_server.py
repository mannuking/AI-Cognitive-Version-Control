"""
cvc.mcp_server — MCP (Model Context Protocol) Server for CVC.

Exposes CVC cognitive versioning operations as MCP tools so that
authentication-based IDEs (Antigravity, Windsurf, GitHub Copilot native)
can use cognitive version control without API endpoint redirection.

These IDEs use their own authentication (Google login, GitHub login,
subscription auth) and do NOT allow overriding the LLM API endpoint.
However, they DO support MCP servers. By running CVC as an MCP server,
the IDE's built-in agent can call CVC tools (commit, branch, merge,
restore, status, log) directly.

Usage:
    cvc mcp                    Start CVC as an MCP server (stdio transport)
    cvc mcp --transport sse    Start CVC as an MCP server (SSE transport)

MCP config for IDEs:

    Antigravity (mcp_config.json):
        {
            "mcpServers": {
                "cvc": {
                    "command": "cvc",
                    "args": ["mcp"]
                }
            }
        }

    VS Code (settings.json → mcp.servers):
        {
            "mcp": {
                "servers": {
                    "cvc": {
                        "command": "cvc",
                        "args": ["mcp"]
                    }
                }
            }
        }

    Windsurf / Cursor (MCP settings):
        Server name: cvc
        Command: cvc mcp
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("cvc.mcp_server")


# ---------------------------------------------------------------------------
# MCP Tool Definitions (JSON Schema for MCP protocol)
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {
        "name": "cvc_status",
        "description": (
            "Show the current CVC cognitive version control status: "
            "active branch, HEAD commit hash, context window size, "
            "and list of all branches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cvc_commit",
        "description": (
            "Create a cognitive commit — save the current AI conversation "
            "context as a checkpoint in the Merkle DAG. Like 'git commit' "
            "but for the AI agent's brain state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message describing the checkpoint.",
                },
                "commit_type": {
                    "type": "string",
                    "enum": ["checkpoint", "analysis", "generation"],
                    "description": "Type of commit. Default: checkpoint.",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "cvc_branch",
        "description": (
            "Create a new cognitive branch and switch to it. Use branches "
            "to explore alternative reasoning paths without losing the "
            "original context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the new branch.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the branch purpose.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "cvc_merge",
        "description": (
            "Merge a source branch into the target branch using semantic "
            "three-way merge. Combines cognitive states from different "
            "exploration paths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_branch": {
                    "type": "string",
                    "description": "Name of the branch to merge from.",
                },
                "target_branch": {
                    "type": "string",
                    "description": "Name of the branch to merge into. Default: main.",
                },
            },
            "required": ["source_branch"],
        },
    },
    {
        "name": "cvc_restore",
        "description": (
            "Time-travel: restore the agent's cognitive state to a previous "
            "commit. Use 'cvc_log' to find commit hashes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "commit_hash": {
                    "type": "string",
                    "description": "Full or short (12-char) commit hash to restore.",
                },
            },
            "required": ["commit_hash"],
        },
    },
    {
        "name": "cvc_log",
        "description": (
            "Show the commit history for the active branch. Returns a list "
            "of commits with hashes, types, and messages."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of commits to return. Default: 20.",
                },
            },
            "required": [],
        },
    },
]


def _get_engine():
    """Lazily initialise CVC engine + database."""
    from cvc.core.models import CVCConfig
    from cvc.core.database import ContextDatabase
    from cvc.operations.engine import CVCEngine

    config = CVCConfig.for_project()
    config.ensure_dirs()
    db = ContextDatabase(config)
    engine = CVCEngine(config, db)
    return engine, db


def _handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a CVC tool call and return the result."""
    from cvc.core.models import (
        CVCCommitRequest,
        CVCBranchRequest,
        CVCMergeRequest,
        CVCRestoreRequest,
    )

    engine, db = _get_engine()

    try:
        if tool_name == "cvc_status":
            branches = db.index.list_branches()
            return {
                "agent_id": engine.config.agent_id,
                "active_branch": engine.active_branch,
                "head_hash": engine.head_hash,
                "context_size": len(engine.context_window),
                "branches": [
                    {
                        "name": b.name,
                        "head": b.head_hash[:12],
                        "status": b.status.value,
                    }
                    for b in branches
                ],
            }

        elif tool_name == "cvc_commit":
            result = engine.commit(CVCCommitRequest(
                message=arguments.get("message", ""),
                commit_type=arguments.get("commit_type", "checkpoint"),
            ))
            return result.model_dump()

        elif tool_name == "cvc_branch":
            result = engine.branch(CVCBranchRequest(
                name=arguments["name"],
                description=arguments.get("description", ""),
            ))
            return result.model_dump()

        elif tool_name == "cvc_merge":
            result = engine.merge(CVCMergeRequest(
                source_branch=arguments["source_branch"],
                target_branch=arguments.get("target_branch", "main"),
            ))
            return result.model_dump()

        elif tool_name == "cvc_restore":
            result = engine.restore(CVCRestoreRequest(
                commit_hash=arguments["commit_hash"],
            ))
            return result.model_dump()

        elif tool_name == "cvc_log":
            entries = engine.log(limit=arguments.get("limit", 20))
            return {"branch": engine.active_branch, "commits": entries}

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    finally:
        db.close()


# ---------------------------------------------------------------------------
# MCP stdio Transport (JSON-RPC over stdin/stdout)
# ---------------------------------------------------------------------------

def run_mcp_stdio() -> None:
    """
    Run the CVC MCP server using stdio transport.

    This is the simplest transport: the IDE launches 'cvc mcp' as a
    subprocess and communicates via JSON-RPC 2.0 over stdin/stdout.
    """
    logger.info("CVC MCP Server starting (stdio transport)")

    # Read JSON-RPC messages from stdin, write responses to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send_jsonrpc_error(None, -32700, "Parse error")
            continue

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        try:
            if method == "initialize":
                _send_jsonrpc_result(msg_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "cvc",
                        "version": _get_version(),
                    },
                })

            elif method == "notifications/initialized":
                # No response needed for notifications
                pass

            elif method == "tools/list":
                _send_jsonrpc_result(msg_id, {"tools": MCP_TOOLS})

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = _handle_tool_call(tool_name, arguments)
                _send_jsonrpc_result(msg_id, {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(result, indent=2, default=str),
                    }],
                })

            elif method == "ping":
                _send_jsonrpc_result(msg_id, {})

            else:
                _send_jsonrpc_error(msg_id, -32601, f"Method not found: {method}")

        except Exception as exc:
            logger.error("MCP error handling %s: %s", method, exc)
            _send_jsonrpc_error(msg_id, -32603, str(exc))


def _send_jsonrpc_result(msg_id: Any, result: Any) -> None:
    """Send a JSON-RPC 2.0 success response to stdout."""
    response = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": result,
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _send_jsonrpc_error(msg_id: Any, code: int, message: str) -> None:
    """Send a JSON-RPC 2.0 error response to stdout."""
    response = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def _get_version() -> str:
    try:
        from cvc import __version__
        return __version__
    except ImportError:
        return "0.3.0"


# ---------------------------------------------------------------------------
# MCP SSE Transport (HTTP Server-Sent Events)
# ---------------------------------------------------------------------------

def run_mcp_sse(host: str = "127.0.0.1", port: int = 8001) -> None:
    """
    Run the CVC MCP server using SSE (Server-Sent Events) transport.

    This transport runs an HTTP server that exposes:
    - GET /sse  — SSE event stream for server→client messages
    - POST /messages — Client→server JSON-RPC messages
    """
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    import asyncio
    import queue

    mcp_app = FastAPI(title="CVC MCP Server (SSE)")
    message_queue: queue.Queue = queue.Queue()

    @mcp_app.get("/sse")
    async def sse_stream():
        async def event_generator():
            # Send the endpoint URL as the first event
            yield f"event: endpoint\ndata: http://{host}:{port}/messages\n\n"
            while True:
                try:
                    msg = message_queue.get_nowait()
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
        )

    @mcp_app.post("/messages")
    async def handle_message(request):
        body = await request.json()
        method = body.get("method", "")
        msg_id = body.get("id")
        params = body.get("params", {})

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cvc", "version": _get_version()},
            }
        elif method == "tools/list":
            result = {"tools": MCP_TOOLS}
        elif method == "tools/call":
            tool_result = _handle_tool_call(
                params.get("name", ""),
                params.get("arguments", {}),
            )
            result = {
                "content": [{
                    "type": "text",
                    "text": json.dumps(tool_result, indent=2, default=str),
                }],
            }
        elif method == "ping":
            result = {}
        else:
            message_queue.put({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })
            return {"ok": True}

        response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        message_queue.put(response)
        return {"ok": True}

    logger.info("CVC MCP Server starting (SSE transport) on %s:%d", host, port)
    uvicorn.run(mcp_app, host=host, port=port, log_level="info")
