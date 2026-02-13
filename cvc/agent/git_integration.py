"""
cvc.agent.git_integration — Git integration for the CVC agent.

Auto-detects Git repositories, shows uncommitted changes on startup,
offers to create Git commits alongside CVC commits, and provides
git status information via /git command.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("cvc.agent.git_integration")


def is_git_repo(workspace: Path) -> bool:
    """Check if the workspace is inside a Git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=str(workspace),
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def git_status(workspace: Path) -> dict[str, Any]:
    """
    Get the current Git status.
    Returns dict with branch, modified files, untracked files, etc.
    """
    result: dict[str, Any] = {
        "is_git": False,
        "branch": "",
        "staged": [],
        "modified": [],
        "untracked": [],
        "ahead": 0,
        "behind": 0,
        "clean": True,
    }

    if not is_git_repo(workspace):
        return result

    result["is_git"] = True

    try:
        # Current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(workspace), timeout=5,
        )
        result["branch"] = branch_result.stdout.strip()

        # Status --porcelain
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(workspace), timeout=5,
        )

        for line in status_result.stdout.splitlines():
            if not line.strip():
                continue
            status_code = line[:2]
            filepath = line[3:].strip()

            if status_code[0] in ("M", "A", "D", "R"):
                result["staged"].append(filepath)
            if status_code[1] == "M":
                result["modified"].append(filepath)
            elif status_code[1] == "D":
                result["modified"].append(filepath)
            elif status_code == "??":
                result["untracked"].append(filepath)

        result["clean"] = not (result["staged"] or result["modified"] or result["untracked"])

        # Ahead/behind
        try:
            ab_result = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"HEAD...@{{upstream}}"],
                capture_output=True, text=True, cwd=str(workspace), timeout=5,
            )
            if ab_result.returncode == 0:
                parts = ab_result.stdout.strip().split()
                if len(parts) == 2:
                    result["ahead"] = int(parts[0])
                    result["behind"] = int(parts[1])
        except Exception:
            pass

    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("Git status failed: %s", e)

    return result


def git_diff_summary(workspace: Path) -> str:
    """Get a summary of uncommitted Git changes."""
    try:
        # Staged changes
        staged = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True, text=True, cwd=str(workspace), timeout=10,
        )
        # Unstaged changes
        unstaged = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, cwd=str(workspace), timeout=10,
        )

        parts = []
        if staged.stdout.strip():
            parts.append(f"Staged changes:\n{staged.stdout.strip()}")
        if unstaged.stdout.strip():
            parts.append(f"Unstaged changes:\n{unstaged.stdout.strip()}")

        return "\n\n".join(parts) if parts else "Working tree clean"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "Could not read Git diff"


def git_commit(workspace: Path, message: str, add_all: bool = True) -> tuple[bool, str]:
    """
    Create a Git commit.
    Returns (success, message_or_hash).
    """
    try:
        if add_all:
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, text=True, cwd=str(workspace), timeout=10,
            )

        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, cwd=str(workspace), timeout=10,
        )

        if result.returncode == 0:
            # Get the commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=str(workspace), timeout=5,
            )
            commit_hash = hash_result.stdout.strip()
            return True, commit_hash
        else:
            error = result.stderr.strip() or result.stdout.strip()
            if "nothing to commit" in error.lower():
                return False, "Nothing to commit — working tree clean"
            return False, error

    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def git_log(workspace: Path, limit: int = 10) -> list[dict[str, str]]:
    """Get recent Git commit log."""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%h|%s|%an|%ar"],
            capture_output=True, text=True, cwd=str(workspace), timeout=10,
        )

        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "author": parts[2],
                    "time": parts[3],
                })
        return commits
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def format_git_status(status: dict[str, Any]) -> str:
    """Format git status for display."""
    if not status.get("is_git"):
        return "Not a Git repository"

    lines = [f"Git branch: {status['branch']}"]

    if status["ahead"]:
        lines.append(f"  ↑ {status['ahead']} ahead")
    if status["behind"]:
        lines.append(f"  ↓ {status['behind']} behind")

    if status["staged"]:
        lines.append(f"  Staged ({len(status['staged'])}): {', '.join(status['staged'][:5])}")
    if status["modified"]:
        lines.append(f"  Modified ({len(status['modified'])}): {', '.join(status['modified'][:5])}")
    if status["untracked"]:
        lines.append(f"  Untracked ({len(status['untracked'])}): {', '.join(status['untracked'][:5])}")

    if status["clean"]:
        lines.append("  Working tree clean ✓")

    return "\n".join(lines)
