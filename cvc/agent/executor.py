"""
cvc.agent.executor — Tool execution engine for the CVC agent.

Executes agent tool calls against the local filesystem, shell, and CVC engine.
All file operations are scoped to the workspace root for safety.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from cvc.core.models import (
    CVCBranchRequest,
    CVCCommitRequest,
    CVCMergeRequest,
    CVCRestoreRequest,
)
from cvc.operations.engine import CVCEngine

logger = logging.getLogger("cvc.agent.executor")

# Max output size to prevent context window explosion
MAX_OUTPUT_CHARS = 30_000
MAX_GREP_MATCHES = 100
MAX_GLOB_RESULTS = 500
MAX_DIR_ENTRIES = 300


class ToolExecutor:
    """
    Executes agent tool calls against the local filesystem and CVC engine.

    All file paths are resolved relative to the workspace root.
    """

    def __init__(self, workspace: Path, engine: CVCEngine) -> None:
        self.workspace = workspace.resolve()
        self.engine = engine

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Execute a tool call and return the result as a string.

        Parameters
        ----------
        tool_name : str
            The name of the tool to execute.
        arguments : dict
            The tool arguments parsed from the LLM response.

        Returns
        -------
        str
            The tool output as a string for inclusion in the conversation.
        """
        dispatch = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "edit_file": self._edit_file,
            "bash": self._bash,
            "glob": self._glob,
            "grep": self._grep,
            "list_dir": self._list_dir,
            "cvc_status": self._cvc_status,
            "cvc_log": self._cvc_log,
            "cvc_commit": self._cvc_commit,
            "cvc_branch": self._cvc_branch,
            "cvc_restore": self._cvc_restore,
            "cvc_merge": self._cvc_merge,
            "cvc_search": self._cvc_search,
            "cvc_diff": self._cvc_diff,
        }

        handler = dispatch.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'"

        try:
            result = handler(arguments)
            return self._truncate(result)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
            return f"Error executing {tool_name}: {exc}"

    # ── Path Resolution ──────────────────────────────────────────────────

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path relative to the workspace root."""
        p = Path(path_str)
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        # Safety: ensure path is within workspace (or allow absolute for reads)
        return p

    # ── File Operations ──────────────────────────────────────────────────

    def _read_file(self, args: dict) -> str:
        path = self._resolve_path(args["path"])
        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error reading file: {e}"

        lines = content.splitlines(keepends=True)
        start = args.get("start_line")
        end = args.get("end_line")

        if start is not None or end is not None:
            s = max(0, (start or 1) - 1)
            e = end if end else len(lines)
            selected = lines[s:e]
            header = f"File: {path.relative_to(self.workspace) if path.is_relative_to(self.workspace) else path}\n"
            header += f"Lines {s + 1}-{min(e, len(lines))} of {len(lines)}\n\n"
            return header + "".join(selected)

        rel = path.relative_to(self.workspace) if path.is_relative_to(self.workspace) else path
        return f"File: {rel} ({len(lines)} lines)\n\n{content}"

    def _write_file(self, args: dict) -> str:
        path = self._resolve_path(args["path"])
        content = args["content"]

        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return f"Error writing file: {e}"

        rel = path.relative_to(self.workspace) if path.is_relative_to(self.workspace) else path
        lines = content.count("\n") + 1
        action = "Updated" if existed else "Created"
        return f"{action} {rel} ({lines} lines)"

    def _edit_file(self, args: dict) -> str:
        path = self._resolve_path(args["path"])
        if not path.exists():
            return f"Error: File not found: {path}"

        old_string = args["old_string"]
        new_string = args["new_string"]

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error reading file: {e}"

        count = content.count(old_string)
        if count == 0:
            # Try to give a helpful hint
            snippet = old_string[:80].replace("\n", "\\n")
            return (
                f"Error: old_string not found in {path.name}. "
                f"Searched for: '{snippet}...'\n"
                f"Make sure the string matches exactly, including whitespace."
            )
        if count > 1:
            return (
                f"Error: old_string matches {count} locations in {path.name}. "
                f"Include more context to make it unique."
            )

        new_content = content.replace(old_string, new_string, 1)
        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            return f"Error writing file: {e}"

        rel = path.relative_to(self.workspace) if path.is_relative_to(self.workspace) else path
        # Show what changed
        old_lines = old_string.count("\n") + 1
        new_lines = new_string.count("\n") + 1
        return f"Edited {rel}: replaced {old_lines} line(s) with {new_lines} line(s)"

    # ── Shell Execution ──────────────────────────────────────────────────

    def _bash(self, args: dict) -> str:
        command = args["command"]
        timeout = args.get("timeout", 120)

        # Pick the right shell
        if sys.platform == "win32":
            shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]

        try:
            result = subprocess.run(
                shell_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.workspace),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout}s\nCommand: {command}"
        except FileNotFoundError as e:
            return f"Error: Shell not found: {e}"

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        if result.returncode != 0:
            output_parts.append(f"\nExit code: {result.returncode}")

        output = "\n".join(output_parts).strip()
        return output if output else "(no output)"

    # ── Search & Discovery ───────────────────────────────────────────────

    def _glob(self, args: dict) -> str:
        pattern = args["pattern"]
        root = self._resolve_path(args.get("path", "."))

        if not root.is_dir():
            return f"Error: Not a directory: {root}"

        matches = []
        try:
            for p in root.rglob("*") if "**" in pattern else root.glob(pattern):
                if len(matches) >= MAX_GLOB_RESULTS:
                    break
                # Skip hidden dirs and common noise
                parts = p.relative_to(root).parts
                if any(part.startswith(".") and part not in (".", "..") for part in parts):
                    continue
                if any(skip in parts for skip in ("node_modules", "__pycache__", ".git", "venv", ".venv")):
                    continue
                if "**" in pattern:
                    # rglob doesn't filter by the actual pattern, so do it manually
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    pure_pattern = pattern.replace("**/", "")
                    if not fnmatch.fnmatch(rel, pattern) and not fnmatch.fnmatch(p.name, pure_pattern):
                        continue
                rel = str(p.relative_to(root)).replace("\\", "/")
                if p.is_dir():
                    rel += "/"
                matches.append(rel)
        except OSError as e:
            return f"Error: {e}"

        if not matches:
            return f"No files matching '{pattern}' in {root}"

        matches.sort()
        header = f"Found {len(matches)} match(es) for '{pattern}':\n\n"
        return header + "\n".join(matches)

    def _grep(self, args: dict) -> str:
        pattern_str = args["pattern"]
        root = self._resolve_path(args.get("path", "."))
        include = args.get("include", "")

        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern_str), re.IGNORECASE)

        results: list[str] = []
        files_checked = 0

        def _search_file(fpath: Path) -> None:
            nonlocal files_checked
            files_checked += 1
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                return
            for i, line in enumerate(text.splitlines(), 1):
                if len(results) >= MAX_GREP_MATCHES:
                    return
                if regex.search(line):
                    rel = str(fpath.relative_to(self.workspace)).replace("\\", "/")
                    results.append(f"{rel}:{i}: {line.rstrip()}")

        if root.is_file():
            _search_file(root)
        elif root.is_dir():
            for fpath in root.rglob("*"):
                if len(results) >= MAX_GREP_MATCHES:
                    break
                if not fpath.is_file():
                    continue
                # Skip noise
                parts = fpath.relative_to(root).parts
                if any(skip in parts for skip in ("node_modules", "__pycache__", ".git", "venv", ".venv", ".cvc")):
                    continue
                if include and not fnmatch.fnmatch(fpath.name, include):
                    continue
                # Skip binary files
                if fpath.suffix in (".pyc", ".so", ".dll", ".exe", ".bin", ".dat", ".db", ".sqlite", ".whl", ".tar", ".gz", ".zip", ".jpg", ".png", ".gif", ".pdf"):
                    continue
                _search_file(fpath)
        else:
            return f"Error: Path not found: {root}"

        if not results:
            return f"No matches for '{pattern_str}' in {root}"

        header = f"Found {len(results)} match(es) for '{pattern_str}' ({files_checked} files searched):\n\n"
        truncated = " (truncated)" if len(results) >= MAX_GREP_MATCHES else ""
        return header + "\n".join(results) + truncated

    def _list_dir(self, args: dict) -> str:
        path = self._resolve_path(args.get("path", "."))

        if not path.exists():
            return f"Error: Directory not found: {path}"
        if not path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = []
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith(".") and item.name not in (".", ".."):
                    # Show dotfiles but mark them
                    pass
                name = item.name
                if item.is_dir():
                    name += "/"
                entries.append(name)
                if len(entries) >= MAX_DIR_ENTRIES:
                    break
        except OSError as e:
            return f"Error listing directory: {e}"

        if not entries:
            return f"Directory '{path}' is empty"

        rel = path.relative_to(self.workspace) if path.is_relative_to(self.workspace) else path
        return f"Contents of {rel}/ ({len(entries)} entries):\n\n" + "\n".join(entries)

    # ── CVC Time Machine Operations ──────────────────────────────────────

    def _cvc_status(self, _args: dict) -> str:
        head = self.engine.head_hash or "(no commits)"
        branch = self.engine.active_branch
        ctx_size = len(self.engine.context_window)

        branches = self.engine.db.index.list_branches()
        branch_list = []
        for b in branches:
            marker = "* " if b.name == branch else "  "
            branch_list.append(f"{marker}{b.name} ({b.head_hash[:12]}) [{b.status.value}]")

        return (
            f"CVC Status:\n"
            f"  Branch:   {branch}\n"
            f"  HEAD:     {head[:12] if head != '(no commits)' else head}\n"
            f"  Context:  {ctx_size} messages\n"
            f"  Provider: {self.engine.config.provider} / {self.engine.config.model}\n\n"
            f"Branches:\n" + "\n".join(branch_list) if branch_list else "No branches"
        )

    def _cvc_log(self, args: dict) -> str:
        limit = args.get("limit", 20)
        entries = self.engine.log(limit=limit)

        if not entries:
            return "No commits yet on this branch."

        lines = [f"Commit log for branch '{self.engine.active_branch}' ({len(entries)} entries):\n"]
        for e in entries:
            lines.append(
                f"  {e['short']}  [{e['type']}]  {e['message'][:70]}"
            )
        return "\n".join(lines)

    def _cvc_commit(self, args: dict) -> str:
        message = args.get("message", "Agent checkpoint")
        result = self.engine.commit(CVCCommitRequest(message=message))
        if result.success:
            return f"Committed: {result.commit_hash[:12]} — {message}"
        return f"Commit failed: {result.message}"

    def _cvc_branch(self, args: dict) -> str:
        name = args["name"]
        desc = args.get("description", "")
        result = self.engine.branch(CVCBranchRequest(name=name, description=desc))
        if result.success:
            return f"Created and switched to branch '{name}' at {result.commit_hash[:12]}"
        return f"Branch failed: {result.message}"

    def _cvc_restore(self, args: dict) -> str:
        commit_hash = args["commit_hash"]
        result = self.engine.restore(CVCRestoreRequest(commit_hash=commit_hash))
        if result.success:
            detail = result.detail or {}
            return (
                f"Time-travelled to commit {commit_hash[:12]}.\n"
                f"Context restored with {detail.get('token_count', '?')} tokens.\n"
                f"You now have the AI's memory from that point in time."
            )
        return f"Restore failed: {result.message}"

    def _cvc_merge(self, args: dict) -> str:
        source = args["source_branch"]
        target = args.get("target_branch", self.engine.active_branch)
        result = self.engine.merge(CVCMergeRequest(source_branch=source, target_branch=target))
        if result.success:
            return f"Merged '{source}' into '{target}' as {result.commit_hash[:12]}"
        return f"Merge failed: {result.message}"

    def _cvc_search(self, args: dict) -> str:
        query = args["query"].lower()
        limit = args.get("limit", 10)

        # Search through all commits for matching messages
        all_branches = self.engine.db.index.list_branches()
        matches = []

        for branch in all_branches:
            commits = self.engine.db.index.list_commits(branch=branch.name, limit=100)
            for commit in commits:
                score = 0
                msg_lower = commit.message.lower()
                # Score based on keyword overlap
                for word in query.split():
                    if word in msg_lower:
                        score += 1
                if score > 0:
                    matches.append({
                        "hash": commit.short_hash,
                        "full_hash": commit.commit_hash,
                        "branch": branch.name,
                        "type": commit.commit_type.value,
                        "message": commit.message,
                        "score": score,
                        "timestamp": commit.metadata.timestamp,
                    })

        # Sort by score descending, then by timestamp
        matches.sort(key=lambda m: (-m["score"], -m["timestamp"]))
        matches = matches[:limit]

        if not matches:
            return f"No commits found matching '{query}'"

        lines = [f"Found {len(matches)} commit(s) matching '{query}':\n"]
        for m in matches:
            lines.append(
                f"  {m['hash']}  [{m['branch']}/{m['type']}]  {m['message'][:60]}"
            )
        lines.append(
            "\nUse cvc_restore with a commit hash to time-travel to that context."
        )
        return "\n".join(lines)

    def _cvc_diff(self, args: dict) -> str:
        commit_a = args.get("commit_a", "HEAD")
        commit_b = args.get("commit_b")

        # Resolve HEAD
        if commit_a == "HEAD":
            commit_a = self.engine.head_hash
            if not commit_a:
                return "No HEAD commit — nothing to diff."

        blob_a = self.engine.db.retrieve_blob(commit_a)
        if blob_a is None:
            return f"Could not find commit {commit_a[:12]}"

        if commit_b:
            blob_b = self.engine.db.retrieve_blob(commit_b)
            if blob_b is None:
                return f"Could not find commit {commit_b[:12]}"
        else:
            # Diff HEAD against current context
            current_msgs = [m.content[:80] for m in self.engine.context_window]
            stored_msgs = [m.content[:80] for m in blob_a.messages]

            diff_lines = [f"Diff: current context vs commit {commit_a[:12]}\n"]
            diff_lines.append(f"  Current:  {len(self.engine.context_window)} messages")
            diff_lines.append(f"  Stored:   {len(blob_a.messages)} messages")

            new_count = len(current_msgs) - len(stored_msgs)
            if new_count > 0:
                diff_lines.append(f"  New since commit: {new_count} messages")
            elif new_count < 0:
                diff_lines.append(f"  Removed since commit: {abs(new_count)} messages")
            else:
                diff_lines.append("  Same number of messages")

            return "\n".join(diff_lines)

        # Compare two commits
        msgs_a = [m.content[:80] for m in blob_a.messages]
        msgs_b = [m.content[:80] for m in blob_b.messages]

        diff_lines = [f"Diff: {commit_a[:12]} vs {commit_b[:12]}\n"]
        diff_lines.append(f"  Commit A: {len(blob_a.messages)} messages")
        diff_lines.append(f"  Commit B: {len(blob_b.messages)} messages")

        return "\n".join(diff_lines)

    # ── Utilities ────────────────────────────────────────────────────────

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) > MAX_OUTPUT_CHARS:
            cut = text[:MAX_OUTPUT_CHARS]
            remaining = len(text) - MAX_OUTPUT_CHARS
            return cut + f"\n\n... (truncated, {remaining:,} chars omitted)"
        return text
