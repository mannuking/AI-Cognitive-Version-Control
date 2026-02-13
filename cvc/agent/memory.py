"""
cvc.agent.memory — Persistent memory across sessions.

Stores a summary of each session in ~/.cvc/memory.md so the agent can
automatically recall what was worked on previously. Also supports an
embedding-based memory index for semantic recall.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cvc.core.models import get_global_config_dir

logger = logging.getLogger("cvc.agent.memory")

MEMORY_FILE = "memory.md"
MEMORY_INDEX_FILE = "memory_index.json"
MAX_MEMORY_ENTRIES = 50
MAX_SESSION_SUMMARY_LEN = 500


def _memory_dir() -> Path:
    """Get the global CVC directory for memory storage."""
    d = get_global_config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _memory_path() -> Path:
    return _memory_dir() / MEMORY_FILE


def _index_path() -> Path:
    return _memory_dir() / MEMORY_INDEX_FILE


def load_memory() -> str:
    """
    Load the persistent memory file.
    Returns the content as a string, or empty string if no memory exists.
    """
    path = _memory_path()
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def load_memory_entries() -> list[dict[str, Any]]:
    """Load the structured memory index."""
    path = _index_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_memory_entry(
    workspace: str,
    summary: str,
    topics: list[str] | None = None,
    model: str = "",
    turn_count: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """
    Append a session summary to the memory file and index.
    """
    now = datetime.now()

    # Update the markdown memory file
    md_path = _memory_path()
    entry_md = (
        f"\n---\n"
        f"## Session: {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"- **Workspace**: {workspace}\n"
        f"- **Model**: {model}\n"
        f"- **Turns**: {turn_count}\n"
    )
    if cost_usd > 0:
        entry_md += f"- **Cost**: ${cost_usd:.4f}\n"
    if topics:
        entry_md += f"- **Topics**: {', '.join(topics)}\n"
    entry_md += f"\n{summary}\n"

    try:
        existing = md_path.read_text(encoding="utf-8") if md_path.exists() else (
            "# CVC Agent Memory\n\n"
            "This file stores summaries of past sessions for context.\n"
        )
        md_path.write_text(existing + entry_md, encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to save memory: %s", e)

    # Update the structured index
    entries = load_memory_entries()
    entries.append({
        "timestamp": time.time(),
        "date": now.isoformat(),
        "workspace": workspace,
        "summary": summary[:MAX_SESSION_SUMMARY_LEN],
        "topics": topics or [],
        "model": model,
        "turn_count": turn_count,
        "cost_usd": cost_usd,
    })

    # Keep only the most recent entries
    entries = entries[-MAX_MEMORY_ENTRIES:]

    try:
        _index_path().write_text(
            json.dumps(entries, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("Failed to save memory index: %s", e)


def get_relevant_memories(workspace: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Get the most relevant past session memories for a workspace.
    Returns recent sessions for the same workspace, plus the most recent
    sessions from any workspace.
    """
    entries = load_memory_entries()
    if not entries:
        return []

    # Prioritize same-workspace sessions
    same_workspace = [e for e in entries if e.get("workspace") == workspace]
    other = [e for e in entries if e.get("workspace") != workspace]

    # Take recent same-workspace entries and fill with others
    result = same_workspace[-limit:]
    remaining = limit - len(result)
    if remaining > 0:
        result.extend(other[-remaining:])

    return result


def build_memory_context(workspace: str) -> str:
    """
    Build a memory context string for injection into the system prompt.
    Returns empty string if no relevant memories exist.
    """
    memories = get_relevant_memories(workspace, limit=5)
    if not memories:
        return ""

    parts = ["## Previous Session Memory"]
    for mem in memories:
        date = mem.get("date", "unknown")[:16]
        ws = mem.get("workspace", "?")
        summary = mem.get("summary", "")
        topics = mem.get("topics", [])

        part = f"- **{date}** ({ws})"
        if topics:
            part += f" — Topics: {', '.join(topics)}"
        part += f"\n  {summary}"
        parts.append(part)

    return "\n".join(parts)


def generate_session_summary(messages: list[dict]) -> tuple[str, list[str]]:
    """
    Generate a brief summary and topic list from conversation messages.
    This is a heuristic-based summary (not LLM-generated to avoid cost).
    """
    topics: set[str] = set()
    user_msgs: list[str] = []
    files_mentioned: set[str] = set()

    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                user_msgs.append(content[:200])

        # Track file operations
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                if name in ("read_file", "write_file", "edit_file"):
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                        if "path" in args:
                            files_mentioned.add(args["path"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Track topics from tool names
                if "cvc_" in name:
                    topics.add("CVC operations")
                elif name == "bash":
                    topics.add("shell commands")
                elif name in ("read_file", "write_file", "edit_file"):
                    topics.add("file editing")
                elif name in ("glob", "grep"):
                    topics.add("code search")

    # Build summary from first and last user messages
    summary_parts = []
    if user_msgs:
        summary_parts.append(f"Started with: {user_msgs[0][:100]}")
        if len(user_msgs) > 1:
            summary_parts.append(f"Last topic: {user_msgs[-1][:100]}")

    if files_mentioned:
        files_list = ", ".join(sorted(files_mentioned)[:5])
        summary_parts.append(f"Files touched: {files_list}")
        topics.add("file editing")

    summary = ". ".join(summary_parts) if summary_parts else "Brief session"

    return summary, list(topics)
