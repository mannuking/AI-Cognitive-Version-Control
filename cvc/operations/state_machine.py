"""
cvc.operations.state_machine — LangGraph state machine for CVC.

The state machine tracks the current Branch and Commit, deciding whether
incoming requests are standard generations or CVC Control Commands
(commit / branch / merge / restore).

This module implements the "State-Based Shift" — transitioning the agent
from a stream-based architecture to a state-based one.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from cvc.core.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CVCBranchRequest,
    CVCCommitRequest,
    CVCMergeRequest,
    CVCOperationResponse,
    CVCRestoreRequest,
)
from cvc.operations.engine import CVCEngine

logger = logging.getLogger("cvc.state_machine")


# ---------------------------------------------------------------------------
# CVC Tool Definitions (MCP / Function-Calling)
# ---------------------------------------------------------------------------

CVC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "cvc_commit",
            "description": (
                "Freeze the current context window and create a cognitive checkpoint. "
                "Use when you've reached a stable intermediate state and want to save "
                "a restore point before proceeding with risky operations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "A concise summary of what was accomplished up to this point.",
                    },
                    "commit_type": {
                        "type": "string",
                        "enum": ["checkpoint", "analysis", "generation"],
                        "description": "The category of this commit.",
                        "default": "checkpoint",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for indexing (e.g., ['auth', 'refactor']).",
                        "default": [],
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_branch",
            "description": (
                "Create a new isolated exploration branch. Use when you want to "
                "try a different approach without polluting the main context with "
                "experimental reasoning. The context window will be reset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Branch name (e.g., 'fix-refactor', 'approach-b').",
                    },
                    "source_commit": {
                        "type": "string",
                        "description": "Commit hash to branch from. Defaults to current HEAD.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Goal or purpose of this branch.",
                        "default": "",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_merge",
            "description": (
                "Merge a completed branch back into the target branch using "
                "semantic three-way merge. Synthesises insights learned in the "
                "source branch into a concise summary for the target."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_branch": {
                        "type": "string",
                        "description": "The branch to merge from.",
                    },
                    "target_branch": {
                        "type": "string",
                        "description": "The branch to merge into (default: 'main').",
                        "default": "main",
                    },
                },
                "required": ["source_branch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_restore",
            "description": (
                "Time-travel: roll back to a previous cognitive state. "
                "Use when stuck in an error loop, hallucination, or dead end. "
                "The context window will be wiped and re-hydrated from the "
                "stored state. Supports full or short commit hashes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_hash": {
                        "type": "string",
                        "description": "The commit hash (full or prefix) to restore to.",
                    },
                },
                "required": ["commit_hash"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class NodeType(StrEnum):
    ROUTER = "router"
    CVC_HANDLER = "cvc_handler"
    PASSTHROUGH = "passthrough"


class CVCGraphState(TypedDict, total=False):
    """State flowing through the LangGraph CVC state machine."""
    # Input
    request: ChatCompletionRequest
    # Routing
    is_cvc_command: bool
    cvc_tool_name: str
    cvc_tool_args: dict[str, Any]
    # Output
    response: ChatCompletionResponse | None
    cvc_result: CVCOperationResponse | None
    # Metadata
    active_branch: str
    head_hash: str
    committed_prefix_len: int


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------

def build_cvc_graph(engine: CVCEngine) -> StateGraph:
    """
    Construct the LangGraph state machine that routes requests between
    standard LLM generation and CVC control commands.

    Graph topology:
        START → router
          ├─ (CVC command) → cvc_handler → END
          └─ (generation)  → passthrough → END
    """

    def router_node(state: CVCGraphState) -> CVCGraphState:
        """
        Inspect the incoming request to determine if it contains a
        CVC control command (tool call) or is a standard generation.
        """
        request = state["request"]
        state["active_branch"] = engine.active_branch
        state["head_hash"] = engine.head_hash or ""
        state["committed_prefix_len"] = len(engine.context_window)

        # Check if any message contains a CVC tool call
        for msg in reversed(request.messages):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    if fn_name.startswith("cvc_"):
                        args_str = fn.get("arguments", "{}")
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        state["is_cvc_command"] = True
                        state["cvc_tool_name"] = fn_name
                        state["cvc_tool_args"] = args
                        logger.info("Routed to CVC handler: %s(%s)", fn_name, args)
                        return state

        # Check for inline CVC commands in the latest user message
        if request.messages:
            last = request.messages[-1]
            content = last.content if isinstance(last.content, str) else ""
            if content.strip().startswith("/cvc "):
                parts = content.strip().split(maxsplit=2)
                cmd = parts[1] if len(parts) > 1 else ""
                arg_text = parts[2] if len(parts) > 2 else "{}"
                if cmd in ("commit", "branch", "merge", "restore", "log", "status"):
                    state["is_cvc_command"] = True
                    state["cvc_tool_name"] = f"cvc_{cmd}"
                    try:
                        state["cvc_tool_args"] = json.loads(arg_text)
                    except json.JSONDecodeError:
                        state["cvc_tool_args"] = {"message": arg_text} if cmd == "commit" else {"name": arg_text}
                    return state

        state["is_cvc_command"] = False
        return state

    def cvc_handler_node(state: CVCGraphState) -> CVCGraphState:
        """Execute the CVC operation identified by the router."""
        tool_name = state.get("cvc_tool_name", "")
        args = state.get("cvc_tool_args", {})
        result: CVCOperationResponse

        if tool_name == "cvc_commit":
            req = CVCCommitRequest(**args)
            result = engine.commit(req)
        elif tool_name == "cvc_branch":
            req = CVCBranchRequest(**args)
            result = engine.branch(req)
        elif tool_name == "cvc_merge":
            req = CVCMergeRequest(**args)
            result = engine.merge(req)
        elif tool_name == "cvc_restore":
            req = CVCRestoreRequest(**args)
            result = engine.restore(req)
        elif tool_name == "cvc_log":
            log_entries = engine.log()
            result = CVCOperationResponse(
                success=True,
                operation="log",
                branch=engine.active_branch,
                message=f"{len(log_entries)} commits",
                detail={"commits": log_entries},
            )
        elif tool_name == "cvc_status":
            branches = engine.db.index.list_branches()
            result = CVCOperationResponse(
                success=True,
                operation="status",
                branch=engine.active_branch,
                commit_hash=engine.head_hash,
                message=f"On branch {engine.active_branch}",
                detail={
                    "branches": [
                        {"name": b.name, "head": b.head_hash[:12], "status": b.status.value}
                        for b in branches
                    ]
                },
            )
        else:
            result = CVCOperationResponse(
                success=False,
                operation=tool_name,
                message=f"Unknown CVC command: {tool_name}",
            )

        state["cvc_result"] = result
        state["active_branch"] = engine.active_branch
        state["head_hash"] = engine.head_hash or ""
        return state

    def passthrough_node(state: CVCGraphState) -> CVCGraphState:
        """
        For standard generation requests — record messages in the context
        window and pass through.  The actual LLM call is made by the proxy.
        """
        request = state["request"]
        for msg in request.messages:
            engine.push_chat_message(msg)

        state["committed_prefix_len"] = len(engine.context_window)
        return state

    # -- Build graph -------------------------------------------------------
    graph = StateGraph(CVCGraphState)

    graph.add_node("router", router_node)
    graph.add_node("cvc_handler", cvc_handler_node)
    graph.add_node("passthrough", passthrough_node)

    graph.add_edge(START, "router")

    def route_decision(state: CVCGraphState) -> str:
        return "cvc_handler" if state.get("is_cvc_command") else "passthrough"

    graph.add_conditional_edges("router", route_decision, {
        "cvc_handler": "cvc_handler",
        "passthrough": "passthrough",
    })

    graph.add_edge("cvc_handler", END)
    graph.add_edge("passthrough", END)

    return graph
