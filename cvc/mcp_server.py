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
        1. Workspace passed via cvc_set_workspace tool (explicit override)
        2. Explicit CVC_WORKSPACE env var
        3. IDE-specific env vars (CODEX_WORKSPACE_ROOT, etc.)
        4. Walk up from cwd to find .cvc/, .git/, pyproject.toml
        5. Fallback to cwd with warning to use cvc_set_workspace tool
        """
        # Strategy 1: Already set via cvc_set_workspace tool (highest priority)
        if self.workspace:
            return self.workspace
        
        # Strategy 2: Explicit env var
        if env_ws := os.environ.get("CVC_WORKSPACE"):
            ws = Path(env_ws).resolve()
            if ws.exists():
                logger.info("Workspace from CVC_WORKSPACE: %s", ws)
                return ws
        
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
        
        # Strategy 5: Fallback to cwd (unreliable - user should call cvc_set_workspace)
        logger.warning(
            "⚠️  Could not detect workspace reliably. Using cwd: %s.\n"
            "For multi-workspace support, call cvc_set_workspace tool with your project path.",
            cwd
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
            config = CVCConfig.for_project(mode="mcp")
            
            # Auto-initialize if .cvc/ doesn't exist
            cvc_dir = workspace / ".cvc"
            if not cvc_dir.exists():
                logger.info("Auto-initializing CVC in %s", workspace)
                config.ensure_dirs()
                logger.info("Created .cvc/ directory structure")
            
            # Initialize engine + database
            self.db = ContextDatabase(config)
            self.engine = CVCEngine(config, self.db)
            
            # AUTO-RESTORE: Engine now auto-hydrates from HEAD commit / persistent cache
            # in its __init__, so no separate restore step needed.
            
            self.initialized = True
            
            logger.info(
                "CVC initialized: workspace=%s, branch=%s, context_size=%d",
                workspace, self.engine.active_branch, len(self.engine.context_window)
            )
        
        finally:
            os.chdir(original_cwd)
    
    def _auto_restore_last_commit(self) -> None:
        """
        Auto-restore the last commit's context into memory on startup.
        
        This ensures conversations persist across IDE/MCP server restarts.
        Without this, the context window starts empty every time VS Code restarts,
        causing data loss for users who want to retrieve month-old conversations.
        
        Priority:
        1. Last committed context from database
        2. Persistent cache file (if crash happened before commit)
        3. Empty state (new session)
        
        CROSS-MODE SUPPORT: MCP can restore sessions from Proxy or CLI
        """
        if not self.engine or not self.db:
            return
        
        try:
            # Get HEAD commit for active branch
            bp = self.db.index.get_branch(self.engine.active_branch)
            if not bp:
                logger.warning("No branch found for auto-restore")
                # Try loading from persistent cache as fallback
                self.engine._load_persistent_cache()
                return
            
            # Skip genesis commit (it's empty)
            head_commit = self.db.index.get_commit(bp.head_hash)
            if not head_commit or head_commit.message == "Genesis — CVC initialised":
                logger.info("Genesis commit detected, trying persistent cache")
                self.engine._load_persistent_cache()
                return
            
            # Retrieve the stored context from database
            blob = self.db.retrieve_blob(bp.head_hash)
            if not blob:
                logger.warning("Could not retrieve blob for HEAD %s", bp.head_hash[:12])
                # Fallback to cache
                self.engine._load_persistent_cache()
                return
            
            # Restore context window from database
            if blob.messages:
                self.engine._context_window = list(blob.messages)
                self.engine._reasoning_trace = blob.reasoning_trace
                
                # Cross-mode detection
                previous_mode = head_commit.metadata.mode or "unknown"
                if previous_mode != "mcp":
                    logger.info(
                        "🔄 Cross-mode restore: %d messages from %s → MCP (commit %s)",
                        len(blob.messages),
                        previous_mode.upper(),
                        bp.head_hash[:12]
                    )
                else:
                    logger.info(
                        "✅ Auto-restored %d messages from last commit %s (%s)",
                        len(blob.messages),
                        bp.head_hash[:12],
                        head_commit.message[:60]
                    )
            else:
                logger.info("No messages in HEAD commit, trying persistent cache")
                self.engine._load_persistent_cache()
        
        except Exception as e:
            logger.warning("Auto-restore failed, trying cache: %s", e)
            self.engine._load_persistent_cache()


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
            "By default returns FULL message content. Set full=false for previews."
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
                "full": {
                    "type": "boolean",
                    "description": "Return full message content (true) or previews (false). Default: true.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "cvc_recall",
        "description": (
            "Natural language search across ALL past conversations. "
            "Uses semantic vector search (Tier 3) when available, plus "
            "text-based search on commit messages and deep content search. "
            "Returns matching conversations with excerpts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g. 'how did we implement auth?').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 10.",
                },
                "deep": {
                    "type": "boolean",
                    "description": "Search inside conversation content, not just commit messages. Default: true.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "cvc_export",
        "description": (
            "Export a commit's conversation as a shareable Markdown document. "
            "Perfect for code reviews — includes full conversation, metadata, "
            "reasoning trace, and referenced files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "commit_hash": {
                    "type": "string",
                    "description": "Commit hash to export. If omitted, exports HEAD.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output file path. Default: auto-generated in cwd.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "cvc_inject",
        "description": (
            "Cross-project context transfer: pull relevant conversations from "
            "another CVC project into the current one. Searches the source "
            "project's conversation history and injects matching context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_project": {
                    "type": "string",
                    "description": "Absolute path to the source project directory (must have .cvc/).",
                },
                "query": {
                    "type": "string",
                    "description": "Natural language query to find relevant conversations in source.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum conversations to pull from source. Default: 5.",
                },
            },
            "required": ["source_project", "query"],
        },
    },
    {
        "name": "cvc_diff",
        "description": (
            "Compare two cognitive commits and show knowledge/decision differences. "
            "Shows added/removed messages, reasoning trace changes, source file changes, "
            "metadata differences, and token delta. If only one hash is given, compares against HEAD."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash_a": {
                    "type": "string",
                    "description": "First commit hash (full or short prefix).",
                },
                "hash_b": {
                    "type": "string",
                    "description": "Second commit hash. If omitted, compares against HEAD.",
                },
            },
            "required": ["hash_a"],
        },
    },
    {
        "name": "cvc_stats",
        "description": (
            "Show aggregated analytics across all CVC commits: total tokens, "
            "estimated costs, message counts by role, commit types, providers/models used, "
            "most-discussed source files, branch activity, and timing patterns."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cvc_compact",
        "description": (
            "Compress the context window to reduce token usage. "
            "Smart mode preserves important messages (decisions, code, architecture) "
            "while summarising routine conversation. Simple mode truncates to recent messages. "
            "Auto-commits the compacted state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "smart": {
                    "type": "boolean",
                    "description": "Use smart heuristic compression (default: true). Set false for simple truncation.",
                },
                "keep_recent": {
                    "type": "integer",
                    "description": "Number of recent messages to always keep. Default: 10.",
                },
                "target_ratio": {
                    "type": "number",
                    "description": "Target compression ratio (0.0-1.0). Default: 0.5.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "cvc_timeline",
        "description": (
            "Show a timeline of all cognitive commits across all branches. "
            "Includes commit types, merge points, branch points, provider/model info, "
            "and timing. Returns structured data for rendering a visual timeline."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of commits to include. Default: 50.",
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
            full_content = arguments.get("full", True)  # Default to full content
            
            if commit_hash:
                # Read specific commit - retrieve ACTUAL MESSAGES from database
                commit = engine.db.index.get_commit(commit_hash)
                
                if not commit:
                    return {
                        "error": f"Commit not found: {commit_hash}",
                        "success": False,
                        "messages": []
                    }
                
                # Retrieve the stored conversation content
                blob = engine.db.retrieve_blob(commit.commit_hash)
                if not blob:
                    return {
                        "error": f"Could not retrieve content for commit {commit_hash}",
                        "success": False,
                        "commit_hash": commit.short_hash,
                        "message": commit.message,
                    }
                
                # Return FULL conversation from the commit
                messages = blob.messages[:limit] if blob.messages else []
                
                if full_content:
                    return {
                        "success": True,
                        "source": "database",
                        "commit_hash": commit.short_hash,
                        "full_hash": commit.commit_hash,
                        "commit_message": commit.message,
                        "commit_type": commit.commit_type.value,
                        "timestamp": commit.metadata.timestamp,
                        "message_count": len(messages),
                        "total_messages": len(blob.messages) if blob.messages else 0,
                        "messages": [
                            {
                                "id": i + 1,
                                "role": m.role,
                                "content": m.content,
                                "character_count": len(m.content),
                            }
                            for i, m in enumerate(messages)
                        ],
                    }
                else:
                    return {
                        "success": True,
                        "source": "database",
                        "commit_hash": commit.short_hash,
                        "commit_message": commit.message,
                        "timestamp": commit.metadata.timestamp,
                        "message_count": len(messages),
                        "messages_preview": [
                            {
                                "id": i + 1,
                                "role": m.role,
                                "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                                "full_length": len(m.content),
                            }
                            for i, m in enumerate(messages)
                        ],
                    }
            
            else:
                # Read current context window from MEMORY (uncommitted work)
                messages = engine.context_window[:limit]
                
                if full_content:
                    # Return complete messages with full content
                    return {
                        "success": True,
                        "source": "memory",
                        "commit_hash": engine.head_hash[:12] if engine.head_hash else "none",
                        "full_hash": engine.head_hash,
                        "branch": engine.active_branch,
                        "message_count": len(messages),
                        "context_size": len(engine.context_window),
                        "note": "This is uncommitted context. Use cvc_capture_context to save it permanently.",
                        "messages": [
                            {
                                "id": i + 1,
                                "role": m.role,
                                "content": m.content,  # FULL content, not truncated
                                "character_count": len(m.content),
                            }
                            for i, m in enumerate(messages)
                        ],
                    }
                else:
                    # Return preview version (first 200 chars)
                    return {
                        "success": True,
                        "commit_hash": engine.head_hash[:12],
                        "full_hash": engine.head_hash,
                        "branch": engine.active_branch,
                        "message_count": len(messages),
                        "context_size": len(engine.context_window),
                        "messages_preview": [
                            {
                                "id": i + 1,
                                "role": m.role,
                                "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                                "full_length": len(m.content),
                            }
                            for i, m in enumerate(messages)
                        ],
                    }

        elif tool_name == "cvc_recall":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            deep = arguments.get("deep", True)

            if not query:
                return {"error": "Query is required", "success": False}

            results = engine.recall(query, limit=limit, deep=deep)
            return {
                "success": True,
                "query": query,
                "result_count": len(results),
                "vector_search_available": engine.db.vectors.available,
                "results": [
                    {
                        "rank": i + 1,
                        "commit_hash": r["short_hash"],
                        "full_hash": r["commit_hash"],
                        "message": r["message"],
                        "timestamp": r["timestamp"],
                        "provider": r.get("provider", ""),
                        "model": r.get("model", ""),
                        "commit_type": r["commit_type"],
                        "relevance_source": r["relevance_source"],
                        "distance": r["distance"],
                        "matching_excerpts": [
                            {
                                "role": mm["role"],
                                "content": mm["content"][:300],
                            }
                            for mm in r.get("matching_messages", [])[:3]
                        ],
                    }
                    for i, r in enumerate(results)
                ],
            }

        elif tool_name == "cvc_export":
            commit_hash = arguments.get("commit_hash")
            output_path = arguments.get("output_path")

            try:
                md_content, resolved_hash = engine.export_markdown(commit_hash)
            except ValueError as exc:
                return {"error": str(exc), "success": False}

            if output_path is None:
                output_path = f"cvc-export-{resolved_hash[:12]}.md"

            out = Path(output_path)
            out.write_text(md_content, encoding="utf-8")

            return {
                "success": True,
                "commit_hash": resolved_hash[:12],
                "full_hash": resolved_hash,
                "output_path": str(out.resolve()),
                "size_bytes": len(md_content.encode("utf-8")),
                "line_count": md_content.count("\n"),
                "message": f"Exported conversation to {out.resolve()}",
            }

        elif tool_name == "cvc_inject":
            source_project = arguments.get("source_project", "")
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)

            if not source_project or not query:
                return {"error": "source_project and query are required", "success": False}

            source_path = Path(source_project).resolve()
            result = engine.inject_from_project(source_path, query, limit=limit)
            return result.model_dump()

        elif tool_name == "cvc_diff":
            hash_a = arguments.get("hash_a", "")
            hash_b = arguments.get("hash_b")

            if not hash_a:
                return {"error": "hash_a is required", "success": False}

            try:
                diff_result = engine.diff(hash_a, hash_b)
            except ValueError as exc:
                return {"error": str(exc), "success": False}

            return {"success": True, **diff_result}

        elif tool_name == "cvc_stats":
            stats_result = engine.stats()
            return {"success": True, **stats_result}

        elif tool_name == "cvc_compact":
            smart = arguments.get("smart", True)
            keep_recent = arguments.get("keep_recent", 10)
            target_ratio = arguments.get("target_ratio", 0.5)

            result = engine.compact(
                smart=smart,
                keep_recent=keep_recent,
                target_ratio=target_ratio,
            )
            return result.model_dump()

        elif tool_name == "cvc_timeline":
            limit = arguments.get("limit", 50)
            timeline_result = engine.timeline(limit=limit)
            return {"success": True, **timeline_result}

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
    sys.stderr.write("\n✅ If you configured mcp.json and restarted your IDE, CVC is ALREADY WORKING!\n")
    sys.stderr.write("   Close this terminal and use CVC through your AI assistant.\n\n")
    sys.stderr.write("   This terminal instance will remain open (listening on stdin) but is NOT needed.\n")
    sys.stderr.write("   Press Ctrl+C to stop.\n\n")
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
│  ⚠️  YOU DON'T NEED TO RUN THIS COMMAND MANUALLY!               │
╰──────────────────────────────────────────────────────────────────╯

╭──────────────────────────────────────────────────────────────────╮
│  CVC MCP Server v{version}                                        │
│  Cognitive Version Control — MCP stdio transport                 │
│  ✨ Auto workspace detection + persistent state                  │
╰──────────────────────────────────────────────────────────────────╯

  ┌───────────────────────────────────────────────────────────────┐
  │  ℹ️  HOW MCP WORKS:                                            │
  │                                                               │
  │  1. Your IDE (VS Code/Windsurf/Antigravity) automatically     │
  │     launches 'cvc mcp' as a BACKGROUND PROCESS               │
  │                                                               │
  │  2. The background server connects to your AI assistant       │
  │     (Copilot/Cascade) and provides CVC tools                  │
  │                                                               │
  │  3. You use CVC by asking your AI assistant in chat:          │
  │     "Show me the CVC status" or "Commit this conversation"    │
  │                                                               │
  │  ❌ You do NOT need to run 'cvc mcp' in a terminal!           │
  │  ✅ Just configure mcp.json and restart your IDE              │
  └───────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────┐
  │  📝 QUICK SETUP (if you haven't yet):                         │
  │                                                               │
  │  1. Create/edit: C:\\Users\\<you>\\AppData\\Roaming\\Code\\User\\mcp.json │
  │     (or ~/.config/Code/User/mcp.json on Linux/Mac)            │
  │                                                               │
  │  2. Add this configuration:                                   │
  │                                                               │
  │     {{                                                         │
  │       "servers": {{                                            │
  │         "cvc": {{                                              │
  │           "command": "cvc",                                    │
  │           "args": ["mcp"],                                     │
  │           "type": "stdio"                                      │
  │         }}                                                     │
  │       }},                                                      │
  │       "inputs": []                                             │
  │     }}                                                         │
  │                                                               │
  │  3. Restart VS Code (Ctrl+Shift+P → "Reload Window")          │
  │                                                               │
  │  4. Open Copilot Chat and ask: "What CVC tools do you have?"  │
  │                                                               │
  │  ✅ That's it! CVC is now running in the background.          │
  └───────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────┐
  │  🛠️  AVAILABLE TOOLS (9 total):                               │
  │                                                               │
  │    • cvc_set_workspace   — Set project directory              │
  │    • cvc_status          — Show branch, HEAD, context size    │
  │    • cvc_commit          — Save conversation checkpoint       │
  │    • cvc_get_context     — Read saved context from commits    │
  │    • cvc_log             — View commit history                │
  │    • cvc_branch          — Create cognitive branch            │
  │    • cvc_merge           — Merge branches                     │
  │    • cvc_restore         — Time-travel to commit              │
  │    • cvc_capture_context — Manually save specific messages    │
  └───────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────┐
  │  🚀 GETTING STARTED:                                          │
  │                                                               │
  │  After setup, just use your AI assistant normally:            │
  │                                                               │
  │    You: "Set the CVC workspace to E:\\Projects\\my-app"       │
  │    AI:  ✅ Workspace set to E:\\Projects\\my-app               │
  │                                                               │
  │    You: "Show me the CVC status"                              │
  │    AI:  📊 Branch: main, HEAD: 60ad7bef, Context: 5 msgs      │
  │                                                               │
  │    You: "Commit this conversation about the API"              │
  │    AI:  ✅ Committed 60ad7bef: API implementation              │
  │                                                               │
  │  📖 Full docs: https://github.com/mannuking/AI-Cognitive-Version-Control │
  └───────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────┐
  │  🔧 ADVANCED OPTIONS:                                         │
  │                                                               │
  │  For HTTP-based clients, use SSE transport:                   │
  │    cvc mcp --transport sse --host 127.0.0.1 --port 8080       │
  │                                                               │
  │  For automatic context capture (no manual commits):           │
  │    cvc serve  (proxy mode for Continue.dev/Cline)            │
  │                                                               │
  │  For interactive CLI agent with full CVC features:            │
  │    cvc  (or: cvc agent)                                       │
  └───────────────────────────────────────────────────────────────┘

  ⚠️  THIS TERMINAL INSTANCE IS NOT CONNECTED TO YOUR IDE
  
  If you configured mcp.json correctly and restarted VS Code,
  the MCP server is ALREADY RUNNING in the background.
  
  You can close this terminal (Ctrl+C) and use CVC through
  your AI assistant in VS Code/Windsurf/Antigravity.

  Press Ctrl+C to stop this unnecessary terminal instance.

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
