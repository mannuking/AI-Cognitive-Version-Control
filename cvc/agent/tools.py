"""
cvc.agent.tools — Agent tool definitions modeled after Claude Code CLI.

Defines all tools the CVC agent can use:
  - File operations: read_file, write_file, edit_file
  - Shell: bash (cross-platform)
  - Search: glob, grep, list_dir
  - CVC Time Machine: cvc_status, cvc_log, cvc_commit, cvc_branch,
    cvc_restore, cvc_merge, cvc_search, cvc_diff
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Tool definitions in OpenAI function-calling schema
# ---------------------------------------------------------------------------

AGENT_TOOLS: list[dict[str, Any]] = [
    # ── File Operations ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file at the given path. "
                "Returns the file content as text. For large files, use "
                "start_line and end_line to read a specific range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute file path to read.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line number (1-based). Omit to read from beginning.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line number (1-based, inclusive). Omit to read to end.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create a new file or overwrite an existing file with the given content. "
                "Parent directories are created automatically if they don't exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit a file by finding and replacing an exact string. "
                "The old_string must match exactly (including whitespace and indentation). "
                "Include enough context lines to make the match unique."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to edit.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find in the file. Must match exactly.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement text.",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },

    # ── Shell Execution ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a shell command and return stdout/stderr. "
                "Uses PowerShell on Windows, bash on macOS/Linux. "
                "Use for running tests, installing packages, git commands, "
                "build tools, and any CLI operations. "
                "Commands run in the workspace root directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 120).",
                    },
                },
                "required": ["command"],
            },
        },
    },

    # ── Search & Discovery ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": (
                "Find files matching a glob pattern. "
                "Returns a list of matching file paths relative to the search root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py', 'src/**/*.ts', '*.md'.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Root directory to search from (default: workspace root).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "Search for a text pattern across files. "
                "Returns matching lines with file paths and line numbers. "
                "Supports regex patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (plain text or regex).",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in (default: workspace root).",
                    },
                    "include": {
                        "type": "string",
                        "description": "Only search files matching this glob (e.g. '*.py').",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "List the contents of a directory. "
                "Returns names with '/' suffix for directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list (default: workspace root).",
                    },
                },
            },
        },
    },

    # ── CVC Time Machine Operations ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "cvc_status",
            "description": (
                "Show the current CVC status: active branch, HEAD commit hash, "
                "context window size, and list of all branches."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_log",
            "description": (
                "Show the commit history for the active CVC branch. "
                "Each entry includes the short hash, type, and message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of commits to show (default: 20).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_commit",
            "description": (
                "Create a cognitive commit — save the current conversation/context state. "
                "This is like a checkpoint in the Time Machine. You can restore to this "
                "point later."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "A descriptive commit message summarizing the current state.",
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
                "Create a new CVC branch to explore an alternative approach. "
                "The context is reset for isolated exploration. "
                "Use this when you want to try a different strategy without losing progress."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Branch name (e.g. 'refactor-auth', 'try-redis').",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what this branch explores.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_restore",
            "description": (
                "Time-travel: restore the conversation context to a previous commit. "
                "This brings back the AI's memory to that exact point in time. "
                "Use cvc_log first to find the commit hash you want to restore to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_hash": {
                        "type": "string",
                        "description": "The commit hash to restore to (full or short 12-char).",
                    },
                },
                "required": ["commit_hash"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_merge",
            "description": (
                "Merge insights from one CVC branch into another. "
                "Performs a semantic three-way merge."
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
                        "description": "The branch to merge into (default: active branch).",
                    },
                },
                "required": ["source_branch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_search",
            "description": (
                "Search through CVC commit history to find previous conversations "
                "and context about a specific topic. Use this when the user asks to "
                "'go back to when we discussed X' or 'find the context about Y'. "
                "Returns matching commits with their messages and hashes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query — what to find in history.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 10).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cvc_diff",
            "description": (
                "Show the difference between the current context and a previous commit, "
                "or between two commits. Useful for understanding what changed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_a": {
                        "type": "string",
                        "description": "First commit hash (or 'HEAD' for current).",
                    },
                    "commit_b": {
                        "type": "string",
                        "description": "Second commit hash to compare against.",
                    },
                },
                "required": ["commit_a"],
            },
        },
    },
]


def get_tool_names() -> list[str]:
    """Return a list of all agent tool names."""
    return [t["function"]["name"] for t in AGENT_TOOLS]


def get_tools_for_provider(provider: str) -> list[dict[str, Any]]:
    """
    Return tool definitions formatted for a specific provider.

    - OpenAI / Ollama: Use the defs as-is (OpenAI function calling format)
    - Anthropic: Convert to Anthropic's tool format
    - Google: Convert to Google's function declarations format
    """
    if provider == "anthropic":
        return _to_anthropic_tools(AGENT_TOOLS)
    elif provider == "google":
        return _to_google_tools(AGENT_TOOLS)
    else:
        return AGENT_TOOLS  # OpenAI / Ollama


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool defs to Anthropic format."""
    converted = []
    for t in tools:
        fn = t["function"]
        converted.append({
            "name": fn["name"],
            "description": fn["description"],
            "input_schema": fn["parameters"],
        })
    return converted


def _to_google_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool defs to Google Gemini function declarations."""
    declarations = []
    for t in tools:
        fn = t["function"]
        declarations.append({
            "name": fn["name"],
            "description": fn["description"],
            "parameters": fn["parameters"],
        })
    return [{"functionDeclarations": declarations}]
