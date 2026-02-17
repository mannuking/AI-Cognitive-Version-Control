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
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("cvc.mcp_server")


# ---------------------------------------------------------------------------
# Persistent Session State (stdio transport is stateful)
# ---------------------------------------------------------------------------

class _MCPSession:
    """Persistent state for the MCP server session."""
    
    def __init__(self) -> None:
        self.workspace: Path | None = None
        self.engine = None
        self.db = None
        self.initialized: bool = False
    
    def detect_workspace(self) -> Path:
        """
        Multi-strategy workspace detection with graceful fallbacks.
        
        Priority order:
        1. Explicit CVC_WORKSPACE env var
        2. Workspace passed via cvc_set_workspace tool
        3. IDE-specific env vars (CODEX_WORKSPACE_ROOT, etc.)
        4. Walk up from cwd to find .cvc/, .git/, pyproject.toml
        5. Fallback to os.getcwd() with warning
        """
        # Strategy 1: Explicit env var
        if env_ws := os.environ.get("CVC_WORKSPACE"):
            ws = Path(env_ws).resolve()
            if ws.exists():
                logger.info("Workspace from CVC_WORKSPACE: %s", ws)
                return ws
        
        # Strategy 2: Already set (via tool call)
        if self.workspace:
            return self.workspace
        
        # Strategy 3: IDE-specific env vars
        for var in ["CODEX_WORKSPACE_ROOT", "PROJECT_ROOT", "WORKSPACE_FOLDER"]:
            if val := os.environ.get(var):
                ws = Path(val).resolve()
                if ws.exists():
                    logger.info("Workspace from %s: %s", var, ws)
                    return ws
        
        # Strategy 4: Walk up from cwd to find markers
        cwd = Path.cwd().resolve()
        current = cwd
        for _ in range(10):  # Max 10 levels up
            if any((current / marker).exists() for marker in [".cvc", ".git", "pyproject.toml", "package.json"]):
                logger.info("Workspace detected via marker: %s", current)
                return current
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent
        
        # Strategy 5: Fallback to cwd (unreliable but better than nothing)
        logger.warning(
            "Could not detect workspace reliably. Using cwd: %s. "
            "Set CVC_WORKSPACE env var for accuracy.", cwd
        )
        return cwd
    
    def ensure_initialized(self) -> None:
        """Initialize CVC engine for the detected workspace (auto-init if needed)."""
        if self.initialized and self.engine and self.db:
            return
        
        from cvc.core.models import CVCConfig
        from cvc.core.database import ContextDatabase
        from cvc.operations.engine import CVCEngine
        
        # Detect workspace
        workspace = self.detect_workspace()
        self.workspace = workspace
        
        # Change to workspace directory for CVCConfig.for_project()
        original_cwd = Path.cwd()
        try:
            os.chdir(workspace)
            
            # Load or create config
            config = CVCConfig.for_project()
            
            # Auto-initialize if .cvc/ doesn't exist
            cvc_dir = workspace / ".cvc"
            if not cvc_dir.exists():
                logger.info("Auto-initializing CVC in %s", workspace)
                config.ensure_dirs()
                logger.info("Created .cvc/ directory structure")
            
            # Initialize engine + database
            self.db = ContextDatabase(config)
            self.engine = CVCEngine(config, self.db)
            self.initialized = True
            
            logger.info(
                "CVC initialized: workspace=%s, branch=%s, context_size=%d",
                workspace, self.engine.active_branch, len(self.engine.context_window)
            )
        
        finally:
            os.chdir(original_cwd)


# Global session instance (persists for entire MCP server lifetime)
_session = _MCPSession()


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
    {
        "name": "cvc_capture_context",
        "description": (
            "Manually capture conversation messages into CVC context. "
            "Use this when IDE doesn't support automatic context capture (e.g., "
            "GitHub Copilot). Pass the conversation history as an array of messages. "
            "Each message should have 'role' (user/assistant/system) and 'content'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "description": "Array of conversation messages to capture.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "enum": ["user", "assistant", "system"],
                                "description": "Message role",
                            },
                            "content": {
                                "type": "string",
                                "description": "Message content",
                            },
                        },
                        "required": ["role", "content"],
                    },
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional commit message after capturing context.",
                },
            },
            "required": ["messages"],
        },
    },
    {
        "name": "cvc_set_workspace",
        "description": (
            "Manually set the workspace/project directory for CVC operations. "
            "By default, CVC auto-detects the workspace from CVC_WORKSPACE env var "
            "or by walking up from cwd to find .cvc/.git markers. Use this to override."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the workspace/project directory.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "cvc_get_context",
        "description": (
            "Read the saved context from the current HEAD commit or a specific commit. "
            "Returns the conversation history that was saved in that checkpoint. "
            "Useful for reviewing what was saved in previous sessions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "commit_hash": {
                    "type": "string",
                    "description": "Optional: specific commit to read. If omitted, reads HEAD.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return. Default: 50.",
                },
            },
            "required": [],
        },
    },
]


def _get_engine():
    """Get the persistent CVC engine from the session (auto-initializes if needed)."""
    _session.ensure_initialized()
    return _session.engine, _session.db


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

        elif tool_name == "cvc_capture_context":
            from cvc.core.models import ContextMessage
            messages = arguments.get("messages", [])
            captured_count = 0
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    engine.push_message(ContextMessage(role=role, content=content))
                    captured_count += 1
            
            # Auto-commit if requested
            commit_msg = arguments.get("commit_message")
            commit_hash = None
            if commit_msg:
                result = engine.commit(CVCCommitRequest(
                    message=commit_msg,
                    commit_type="checkpoint",
                ))
                if result.success:
                    commit_hash = result.commit_hash[:12]
            
            return {
                "success": True,
                "captured_messages": captured_count,
                "new_context_size": len(engine.context_window),
                "commit_hash": commit_hash,
                "message": f"Captured {captured_count} messages into CVC context.",
            }

        elif tool_name == "cvc_set_workspace":
            workspace_path = Path(arguments["path"]).resolve()
            if not workspace_path.exists():
                return {
                    "error": f"Path does not exist: {workspace_path}",
                    "success": False,
                }
            
            # Update session workspace and reinitialize
            _session.workspace = workspace_path
            _session.initialized = False
            _session.ensure_initialized()
            
            return {
                "success": True,
                "workspace": str(_session.workspace),
                "message": f"Workspace set to: {_session.workspace}",
                "cvc_initialized": (_session.workspace / ".cvc").exists(),
            }

        elif tool_name == "cvc_get_context":
            commit_hash = arguments.get("commit_hash")
            limit = arguments.get("limit", 50)
            
            if commit_hash:
                # Read specific commit - use log to find the commit
                entries = engine.log(limit=100)  # Search in log
                commit_entry = None
                for entry in entries:
                    if entry['hash'].startswith(commit_hash) or entry['short'] == commit_hash:
                        commit_entry = entry
                        break
                
                if not commit_entry:
                    return {
                        "error": f"Commit not found: {commit_hash}",
                        "success": False,
                        "messages": []
                    }
                
                # Return commit info with message preview
                return {
                    "success": True,
                    "commit_hash": commit_entry['short'],
                    "full_hash": commit_entry['hash'],
                    "type": commit_entry['type'],
                    "message": commit_entry['message'],
                    "timestamp": commit_entry.get('timestamp'),
                    "note": "To restore this context, use cvc_restore tool with commit hash",
                }
            else:
                # Read current context window
                messages = engine.context_window[:limit]
                
                return {
                    "success": True,
                    "commit_hash": engine.head_hash[:12],
                    "full_hash": engine.head_hash,
                    "branch": engine.active_branch,
                    "message_count": len(messages),
                    "context_size": len(engine.context_window),
                    "messages_preview": [
                        {
                            "role": m.role,
                            "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                            "full_length": len(m.content),
                        }
                        for m in messages
                    ],
                }

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as exc:
        logger.error("Tool execution error: %s", exc, exc_info=True)
        return {"error": str(exc), "success": False}


# ---------------------------------------------------------------------------
# MCP stdio Transport (JSON-RPC over stdin/stdout)
# ---------------------------------------------------------------------------

def run_mcp_stdio() -> None:
    """
    Run the CVC MCP server using stdio transport.

    This is the simplest transport: the IDE launches 'cvc mcp' as a
    subprocess and communicates via JSON-RPC 2.0 over stdin/stdout.
    """
    # Configure logging to stderr (stdout is the protocol channel)
    _setup_stderr_logging()

    # Detect interactive terminal — user ran 'cvc mcp' manually
    if sys.stdin.isatty():
        _print_stdio_guidance()

    logger.info("CVC MCP Server ready (stdio transport) — waiting for JSON-RPC messages")
    sys.stderr.write("CVC MCP Server ready (stdio) — awaiting IDE connection…\n")
    sys.stderr.flush()

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
        return "0.5.0"


def _setup_stderr_logging() -> None:
    """Route all CVC MCP logging to stderr so stdout stays clean for JSON-RPC."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s — %(message)s", datefmt="%H:%M:%S"
    ))
    mcp_logger = logging.getLogger("cvc.mcp_server")
    mcp_logger.addHandler(handler)
    mcp_logger.setLevel(logging.INFO)
    # Prevent propagation to root logger (which might write to stdout)
    mcp_logger.propagate = False


def _print_stdio_guidance() -> None:
    """
    When the user runs 'cvc mcp' directly in a terminal (stdin is a TTY),
    print helpful guidance to stderr explaining that stdio transport is
    meant for IDE integration, not interactive use.
    """
    version = _get_version()
    sys.stderr.write(f"""
╭──────────────────────────────────────────────────────────────────╮
│  CVC MCP Server v{version}                                        │
│  Cognitive Version Control — MCP stdio transport                 │
│  ✨ NEW: Auto workspace detection + persistent state             │
╰──────────────────────────────────────────────────────────────────╯

  This server communicates via JSON-RPC over stdin/stdout.
  It's designed to be launched BY your IDE, not run manually.

  ┌───────────────────────────────────────────────────────────────┐
  │  🔧 WORKSPACE DETECTION (auto-initializes .cvc/ if needed)    │
  │                                                               │
  │  The server auto-detects your project workspace using:       │
  │    1. CVC_WORKSPACE env var (highest priority)                │
  │    2. Walk up from cwd to find .cvc, .git, pyproject.toml     │
  │    3. IDE-specific env vars (CODEX_WORKSPACE_ROOT, etc.)      │
  │                                                               │
  │  Or use cvc_set_workspace tool to manually override.          │
  └───────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────┐
  │  📝 IDE CONFIGURATION EXAMPLES:                               │
  │                                                               │
  │  VS Code - User Settings (settings.json):                     │
  │    "mcp": {{                                                   │
  │      "servers": {{                                             │
  │        "cvc": {{                                               │
  │          "command": "cvc",                                     │
  │          "args": ["mcp"],                                      │
  │          "env": {{                                             │
  │            "CVC_WORKSPACE": "${{workspaceFolder}}"             │
  │          }}                                                    │
  │        }}                                                      │
  │      }}                                                        │
  │    }}                                                          │
  │                                                               │
  │  VS Code - Workspace (.vscode/mcp.json):                      │
  │    {{                                                          │
  │      "servers": {{                                             │
  │        "cvc": {{                                               │
  │          "command": "cvc",                                     │
  │          "args": ["mcp"]                                       │
  │        }}                                                      │
  │      }}                                                        │
  │    }}                                                          │
  │    (auto-detects workspace from .vscode location)             │
  │                                                               │
  │  Cursor / Windsurf (.cursor/mcp.json or IDE settings):        │
  │    {{                                                          │
  │      "mcpServers": {{                                          │
  │        "cvc": {{                                               │
  │          "command": "cvc",                                     │
  │          "args": ["mcp"],                                      │
  │          "env": {{                                             │
  │            "CVC_WORKSPACE": "/absolute/path/to/your/project"   │
  │          }}                                                    │
  │        }}                                                      │
  │      }}                                                        │
  │    }}                                                          │
  └───────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────┐
  │  🛠️  AVAILABLE TOOLS (10 total):                              │
  │                                                               │
  │    • cvc_status          — Show branch, HEAD, context size    │
  │    • cvc_commit          — Save conversation checkpoint       │
  │    • cvc_branch          — Create cognitive branch            │
  │    • cvc_merge           — Merge branches                     │
  │    • cvc_restore         — Time-travel to commit              │
  │    • cvc_log             — View commit history                │
  │    • cvc_capture_context — Manually save conversation         │
  │    • cvc_set_workspace   — Override workspace path            │
  │    • cvc_get_context     — Read saved context from commits    │
  └───────────────────────────────────────────────────────────────┘

  💡 TIP: For automatic context capture, use 'cvc serve' with
      Continue.dev or Cline extensions. MCP mode requires manual
      capture via cvc_capture_context tool.

  Or use SSE transport for HTTP-based integration:
    cvc mcp --transport sse


  The server is now listening on stdin for JSON-RPC messages.
  Press Ctrl+C to stop.

""")
    sys.stderr.flush()


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
