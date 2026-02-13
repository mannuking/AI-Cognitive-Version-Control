"""
cvc.vcs.bridge — VCS Synchronisation via Shadow Branches and Git hooks.

Implements the Shadow Branch Pattern (§3.4):
- Shadow Branch (cvc/main): stores the .cvc/ directory with Merkle DAGs.
- Git Hooks: post-commit and post-checkout bridge code ↔ cognitive state.
- Git Notes (refs/notes/cvc): attach CVC commit hashes to Git commits,
  enabling ``git log --show-notes=cvc`` for "Cognitive Blame".
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from textwrap import dedent
from typing import Any

from cvc.core.database import ContextDatabase
from cvc.core.models import CVCConfig

logger = logging.getLogger("cvc.vcs.bridge")


class VCSBridge:
    """
    Bi-directional bridge between the CVC database and the host Git
    repository.  Manages shadow branches, Git Notes, and hook scripts.
    """

    SHADOW_PREFIX = "cvc/"
    NOTES_REF = "refs/notes/cvc"

    def __init__(self, config: CVCConfig, db: ContextDatabase) -> None:
        self.config = config
        self.db = db
        self._repo_root = self._find_git_root()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def install_hooks(self) -> dict[str, str]:
        """
        Install post-commit and post-checkout Git hooks that trigger
        CVC synchronisation.  Returns a mapping of hook name → path.
        """
        if self._repo_root is None:
            return {"error": "Not inside a Git repository"}

        hooks_dir = self._repo_root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        installed: dict[str, str] = {}

        for hook_name, script in self._hook_scripts().items():
            hook_path = hooks_dir / hook_name
            # Preserve existing hooks by chaining
            if hook_path.exists():
                existing = hook_path.read_text(encoding="utf-8")
                if "# CVC-HOOK" not in existing:
                    script = existing.rstrip() + "\n\n" + script
                else:
                    continue  # Already installed

            hook_path.write_text(script, encoding="utf-8")
            # Make executable (Windows doesn't need this but Git for Windows respects it)
            hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
            installed[hook_name] = str(hook_path)
            logger.info("Installed Git hook: %s", hook_path)

        return installed

    # ------------------------------------------------------------------
    # Shadow Branch operations
    # ------------------------------------------------------------------

    def capture_snapshot(self, git_sha: str | None = None) -> dict[str, Any]:
        """
        Capture the current CVC state into the shadow branch.

        Called by the post-commit hook or manually after an agent commits code.
        """
        if self._repo_root is None:
            return {"error": "Not inside a Git repository"}

        if git_sha is None:
            git_sha = self._current_git_sha()

        if git_sha is None:
            return {"error": "Could not determine current Git SHA"}

        # Get current CVC HEAD
        main_bp = self.db.index.get_branch(self.config.default_branch)
        if main_bp is None:
            return {"error": "No CVC default branch found"}

        cvc_hash = main_bp.head_hash

        # Attach Git Note
        self._set_git_note(git_sha, cvc_hash)

        # Link in the index
        self.db.index.link_git_commit(git_sha, cvc_hash, time.time())

        result = {
            "git_sha": git_sha,
            "cvc_hash": cvc_hash,
            "shadow_branch": f"{self.SHADOW_PREFIX}{self.config.default_branch}",
        }

        logger.info("Snapshot captured: git=%s ↔ cvc=%s", git_sha[:8], cvc_hash[:12])
        return result

    def restore_for_checkout(self, git_sha: str) -> str | None:
        """
        When ``git checkout`` moves HEAD, find the corresponding CVC state
        and return its commit hash so the engine can restore it.
        """
        # Try Git Note first
        cvc_hash = self._get_git_note(git_sha)
        if cvc_hash:
            return cvc_hash.strip()

        # Fallback to index
        return self.db.index.get_cvc_hash_for_git(git_sha)

    # ------------------------------------------------------------------
    # Git Notes (refs/notes/cvc)
    # ------------------------------------------------------------------

    def _set_git_note(self, git_sha: str, cvc_hash: str) -> bool:
        """Attach a CVC commit hash as a Git Note on the given Git commit."""
        try:
            self._git("notes", "--ref", self.NOTES_REF, "add", "-f", "-m", cvc_hash, git_sha)
            return True
        except subprocess.CalledProcessError:
            logger.warning("Failed to set Git note on %s", git_sha)
            return False

    def _get_git_note(self, git_sha: str) -> str | None:
        """Read the CVC note attached to a Git commit."""
        try:
            result = self._git("notes", "--ref", self.NOTES_REF, "show", git_sha)
            return result.strip() if result else None
        except subprocess.CalledProcessError:
            return None

    # ------------------------------------------------------------------
    # Hook script generation
    # ------------------------------------------------------------------

    def _hook_scripts(self) -> dict[str, str]:
        """Generate the shell scripts for Git hooks."""
        # Use Python to invoke the CVC CLI
        python_cmd = "python -m cvc.cli"

        post_commit = dedent(f"""\
            #!/bin/sh
            # CVC-HOOK: post-commit — capture cognitive state snapshot
            GIT_SHA=$(git rev-parse HEAD)
            {python_cmd} capture-snapshot --git-sha "$GIT_SHA" 2>/dev/null || true
        """)

        post_checkout = dedent(f"""\
            #!/bin/sh
            # CVC-HOOK: post-checkout — restore cognitive state for checked-out commit
            NEW_HEAD="$2"
            BRANCH_CHECKOUT="$3"
            if [ "$BRANCH_CHECKOUT" = "1" ]; then
                GIT_SHA=$(git rev-parse HEAD)
                {python_cmd} restore-for-checkout --git-sha "$GIT_SHA" 2>/dev/null || true
            fi
        """)

        return {
            "post-commit": post_commit,
            "post-checkout": post_checkout,
        }

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _git(self, *args: str) -> str:
        """Run a Git command in the repo root."""
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=str(self._repo_root) if self._repo_root else None,
            timeout=30,
        )
        result.check_returncode()
        return result.stdout

    def _current_git_sha(self) -> str | None:
        try:
            return self._git("rev-parse", "HEAD").strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    @staticmethod
    def _find_git_root() -> Path | None:
        """Walk up from CWD to find the .git directory."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return Path(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None
