"""
cvc.agent.auto_context — Multi-file awareness and auto-context injection.

Automatically reads project configuration files on startup, indexes the
file tree, and injects a summary into the system prompt. Also auto-reads
files mentioned in error messages.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("cvc.agent.auto_context")

# Project manifest files to read on startup (in priority order)
PROJECT_MANIFESTS = [
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "CMakeLists.txt",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "composer.json",
    "Gemfile",
    ".tool-versions",
]

# Directories to skip when indexing the file tree
SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".cvc", ".svn", ".hg",
    "venv", ".venv", "env", ".env", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", "target",
    ".next", ".nuxt", "coverage", ".nyc_output", ".eggs",
    "*.egg-info", ".terraform", ".angular",
}

# Binary/large file extensions to skip
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".dat",
    ".db", ".sqlite", ".sqlite3", ".whl", ".tar", ".gz", ".zip",
    ".rar", ".7z", ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".ico", ".svg", ".pdf", ".mp3", ".mp4", ".avi", ".mov",
    ".ttf", ".woff", ".woff2", ".eot", ".lock",
}

MAX_TREE_DEPTH = 4
MAX_TREE_FILES = 200
MAX_MANIFEST_SIZE = 10_000  # chars


def _load_cvcignore(workspace: Path) -> list[str]:
    """Load .cvcignore patterns if the file exists."""
    ignore_file = workspace / ".cvcignore"
    if not ignore_file.exists():
        return []
    try:
        patterns = []
        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
        return patterns
    except OSError:
        return []


def _should_skip(path: Path, ignore_patterns: list[str], workspace: Path) -> bool:
    """Check if a path should be skipped based on ignore patterns."""
    rel = str(path.relative_to(workspace)).replace("\\", "/")
    name = path.name

    # Check built-in skip dirs
    if path.is_dir() and name in SKIP_DIRS:
        return True
    if any(fnmatch.fnmatch(name, pattern) for pattern in SKIP_DIRS if "*" in pattern):
        return True

    # Check built-in skip extensions
    if path.is_file() and path.suffix.lower() in SKIP_EXTENSIONS:
        return True

    # Check .cvcignore patterns
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        # Check if a parent dir matches a directory pattern
        if pattern.endswith("/") and fnmatch.fnmatch(rel + "/", pattern):
            return True

    return False


def build_file_tree(workspace: Path, max_depth: int = MAX_TREE_DEPTH) -> str:
    """
    Build a condensed file tree summary of the workspace.
    Returns a formatted string suitable for injection into the system prompt.
    """
    ignore_patterns = _load_cvcignore(workspace)
    lines: list[str] = []
    file_count = 0

    def _walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal file_count
        if depth > max_depth or file_count > MAX_TREE_FILES:
            return

        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return

        visible = [e for e in entries if not _should_skip(e, ignore_patterns, workspace)]

        for i, entry in enumerate(visible):
            if file_count > MAX_TREE_FILES:
                lines.append(f"{prefix}... (truncated)")
                return

            is_last = i == len(visible) - 1
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            if entry.is_dir():
                # Count children to show in summary
                try:
                    child_count = sum(1 for _ in entry.iterdir())
                except OSError:
                    child_count = 0
                lines.append(f"{prefix}{connector}{entry.name}/")
                _walk(entry, prefix + extension, depth + 1)
            else:
                file_count += 1
                size = ""
                try:
                    sz = entry.stat().st_size
                    if sz > 1_000_000:
                        size = f" ({sz / 1_000_000:.1f}MB)"
                    elif sz > 10_000:
                        size = f" ({sz / 1_000:.0f}KB)"
                except OSError:
                    pass
                lines.append(f"{prefix}{connector}{entry.name}{size}")

    lines.append(f"{workspace.name}/")
    _walk(workspace, "", 0)

    if file_count > MAX_TREE_FILES:
        lines.append(f"\n(Showing {MAX_TREE_FILES} of {file_count}+ files)")

    return "\n".join(lines)


def read_project_manifests(workspace: Path) -> dict[str, str]:
    """
    Read project manifest files (pyproject.toml, package.json, etc.)
    Returns a dict of {filename: content}.
    """
    manifests: dict[str, str] = {}
    for name in PROJECT_MANIFESTS:
        path = workspace / name
        if path.exists() and path.is_file():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if len(content) > MAX_MANIFEST_SIZE:
                    content = content[:MAX_MANIFEST_SIZE] + "\n... (truncated)"
                manifests[name] = content
            except OSError:
                continue
    return manifests


def extract_files_from_error(error_text: str, workspace: Path) -> list[Path]:
    """
    Extract file paths mentioned in error messages/tracebacks.
    Returns a list of file paths that exist in the workspace.
    """
    import re

    files: list[Path] = []
    seen = set()

    # Common error patterns:
    # Python: File "path/to/file.py", line 42
    # Node: at Object.<anonymous> (path/to/file.js:42:10)
    # Rust: --> src/main.rs:42:5
    # Generic: path/to/file.ext:42
    patterns = [
        r'File "([^"]+)"',                    # Python traceback
        r'at .+? \((.+?):\d+:\d+\)',           # Node.js
        r'--> (.+?):\d+:\d+',                  # Rust
        r"([a-zA-Z0-9_./-]+\.\w+):\d+",       # Generic file:line
        r"in (.+?) on line \d+",               # PHP
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, error_text):
            fpath_str = match.group(1).strip()
            if fpath_str in seen:
                continue
            seen.add(fpath_str)

            # Try resolving relative to workspace
            fpath = Path(fpath_str)
            if not fpath.is_absolute():
                fpath = workspace / fpath
            fpath = fpath.resolve()

            if fpath.exists() and fpath.is_file():
                files.append(fpath)

    return files[:5]  # Limit to 5 files


def build_auto_context(workspace: Path) -> str:
    """
    Build the full auto-context string for injection into the system prompt.
    Includes file tree and project manifests.
    """
    parts: list[str] = []

    # File tree
    tree = build_file_tree(workspace)
    if tree:
        parts.append(f"## Project File Tree\n```\n{tree}\n```")

    # Manifests
    manifests = read_project_manifests(workspace)
    if manifests:
        parts.append("## Project Configuration Files")
        for name, content in manifests.items():
            parts.append(f"### {name}\n```\n{content}\n```")

    return "\n\n".join(parts)
