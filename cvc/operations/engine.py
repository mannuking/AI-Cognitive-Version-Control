"""
cvc.operations.engine — The four CVC operations (commit, branch, merge, restore).

These are the agent-invocable tools that make CVC a state-based system.
Each operation mutates the three-tiered Context Database and returns a
structured ``CVCOperationResponse``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from cvc.core.database import ContextDatabase
from cvc.core.models import (
    BranchPointer,
    BranchStatus,
    ChatMessage,
    CognitiveCommit,
    CommitMetadata,
    CommitType,
    ContentBlob,
    ContextMessage,
    CVCBranchRequest,
    CVCCommitRequest,
    CVCConfig,
    CVCMergeRequest,
    CVCOperationResponse,
    CVCRestoreRequest,
)

logger = logging.getLogger("cvc.operations")


class CVCEngine:
    """
    Stateful engine that owns the Context Database and exposes commit /
    branch / merge / restore as first-class operations.
    """

    def __init__(self, config: CVCConfig, db: ContextDatabase) -> None:
        self.config = config
        self.db = db
        self._active_branch: str = config.default_branch
        self._context_window: list[ContextMessage] = []
        self._reasoning_trace: str = ""

        # Auto-hydrate context from the HEAD commit so that
        # `cvc status`, session resume, and every other command that
        # instantiates the engine immediately sees the real message count.
        self._hydrate_from_head()

    # -- Public accessors --------------------------------------------------

    @property
    def active_branch(self) -> str:
        return self._active_branch

    @property
    def context_window(self) -> list[ContextMessage]:
        return list(self._context_window)

    @property
    def head_hash(self) -> str | None:
        bp = self.db.index.get_branch(self._active_branch)
        return bp.head_hash if bp else None

    # -- Context window management -----------------------------------------

    def push_message(self, msg: ContextMessage) -> None:
        """Append a message to the live context window."""
        self._context_window.append(msg)
        self._save_persistent_cache()  # Auto-save on every message

    def push_chat_message(self, cm: ChatMessage) -> None:
        content_str = cm.content if isinstance(cm.content, str) else str(cm.content)
        self.push_message(
            ContextMessage(
                role=cm.role,
                content=content_str,
                name=cm.name,
                tool_call_id=cm.tool_call_id,
            )
        )

    def set_reasoning_trace(self, trace: str) -> None:
        self._reasoning_trace = trace

    def get_context_as_messages(self) -> list[dict[str, Any]]:
        """Export the current context window as OpenAI-compatible dicts."""
        return [m.model_dump(exclude_none=True) for m in self._context_window]
    
    # -- Context hydration (startup) ------------------------------------

    def _hydrate_from_head(self) -> None:
        """
        Populate the in-memory context window from the most recent source
        of truth, checked in this order:

          1. The HEAD commit's content blob (authoritative, committed data).
          2. The persistent JSON cache (uncommitted but saved-to-disk data).

        If the persistent cache contains *more* messages than the HEAD blob
        (i.e. messages were pushed after the last commit but before a crash
        or clean shutdown), the cache wins so no data is lost.
        """
        head_messages: list[ContextMessage] = []
        head_trace = ""

        # --- 1. Try the HEAD commit blob ---------------------------------
        try:
            bp = self.db.index.get_branch(self._active_branch)
            if bp is not None:
                blob = self.db.retrieve_blob(bp.head_hash)
                if blob is not None and blob.messages:
                    head_messages = list(blob.messages)
                    head_trace = blob.reasoning_trace
                    logger.info(
                        "Hydrated %d messages from HEAD commit %s",
                        len(head_messages),
                        bp.head_hash[:12],
                    )
        except Exception as exc:
            logger.debug("HEAD blob hydration failed (non-fatal): %s", exc)

        # --- 2. Try the persistent cache ---------------------------------
        cache_messages: list[ContextMessage] = []
        cache_trace = ""
        try:
            cache_file = self.config.cvc_root / "context_cache.json"
            if cache_file.exists():
                cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
                msgs_raw = cache_data.get("messages", [])
                if msgs_raw:
                    cache_messages = [
                        ContextMessage.model_validate(m) for m in msgs_raw
                    ]
                    cache_trace = cache_data.get("reasoning_trace", "")
        except Exception as exc:
            logger.debug("Persistent cache load failed (non-fatal): %s", exc)

        # --- Pick whichever source has more data -------------------------
        if len(cache_messages) > len(head_messages):
            self._context_window = cache_messages
            self._reasoning_trace = cache_trace
            logger.info(
                "Using persistent cache (%d msgs) over HEAD blob (%d msgs)",
                len(cache_messages),
                len(head_messages),
            )
        elif head_messages:
            self._context_window = head_messages
            self._reasoning_trace = head_trace
        # else: both empty → context_window stays []

    def _save_persistent_cache(self) -> None:
        """
        Save the current context window to a persistent cache file.
        
        This prevents data loss if the MCP server or proxy crashes before commit.
        The cache is loaded on startup if no commits exist yet.
        """
        try:
            cache_file = self.config.cvc_root / "context_cache.json"
            cache_data = {
                "branch": self._active_branch,
                "messages": [m.model_dump() for m in self._context_window],
                "reasoning_trace": self._reasoning_trace,
                "timestamp": time.time(),
            }
            cache_file.write_text(json.dumps(cache_data, indent=2))
        except Exception as e:
            logger.warning("Failed to save persistent cache (non-fatal): %s", e)
    
    def _load_persistent_cache(self) -> bool:
        """
        Load the persistent cache if it exists and no commits have been made.
        
        Returns True if cache was loaded, False otherwise.
        """
        try:
            cache_file = self.config.cvc_root / "context_cache.json"
            if not cache_file.exists():
                return False
            
            cache_data = json.loads(cache_file.read_text())
            messages_data = cache_data.get("messages", [])
            
            if messages_data:
                self._context_window = [
                    ContextMessage.model_validate(m) for m in messages_data
                ]
                self._reasoning_trace = cache_data.get("reasoning_trace", "")
                logger.info(
                    "Loaded %d messages from persistent cache (timestamp: %s)",
                    len(self._context_window),
                    cache_data.get("timestamp", "unknown")
                )
                return True
        except Exception as e:
            logger.warning("Failed to load persistent cache (non-fatal): %s", e)
        
        return False

    # ======================================================================
    # 4.1  COMMIT
    # ======================================================================

    def commit(
        self,
        request: CVCCommitRequest,
        summary: str | None = None,
        git_sha: str | None = None,
    ) -> CVCOperationResponse:
        """
        Freeze the current context window and persist it as a Merkle DAG node.

        If *summary* is provided (e.g., from a secondary Reflector LLM), it
        is used as the commit message.  Otherwise, the request message is used.
        """
        bp = self.db.index.get_branch(self._active_branch)
        if bp is None:
            return CVCOperationResponse(
                success=False, operation="commit", message=f"Branch '{self._active_branch}' not found"
            )

        blob = ContentBlob(
            messages=list(self._context_window),
            reasoning_trace=self._reasoning_trace,
            token_count=sum(len(m.content.split()) for m in self._context_window),  # approx
        )

        meta = CommitMetadata(
            agent_id=self.config.agent_id,
            mode=self.config.mode,
            git_commit_sha=git_sha,
            provider=self.config.provider,
            model=self.config.model,
            tags=request.tags,
        )

        commit = CognitiveCommit(
            parent_hashes=[bp.head_hash],
            commit_type=request.commit_type,
            message=summary or request.message,
            content_blob=blob,
            metadata=meta,
        )

        commit_hash = self.db.store_commit(commit)

        # Advance HEAD
        self.db.index.advance_head(self._active_branch, commit_hash)

        # Link to Git if available
        if git_sha:
            self.db.index.link_git_commit(git_sha, commit_hash, meta.timestamp)

        logger.info("COMMIT %s on %s: %s", commit.short_hash, self._active_branch, commit.message[:60])

        return CVCOperationResponse(
            success=True,
            operation="commit",
            commit_hash=commit_hash,
            branch=self._active_branch,
            message=f"Committed {commit.short_hash}: {commit.message[:80]}",
        )

    # ======================================================================
    # 4.2  BRANCH
    # ======================================================================

    def branch(self, request: CVCBranchRequest) -> CVCOperationResponse:
        """
        Create a new branch pointer and reset the context window.

        The agent gets a clean working state containing only the global roadmap
        and the branch-specific goal — no accumulated entropy from the parent.
        """
        # Determine source commit
        if request.source_commit:
            source = self.db.index.get_commit(request.source_commit)
            if source is None:
                return CVCOperationResponse(
                    success=False,
                    operation="branch",
                    message=f"Source commit '{request.source_commit}' not found",
                )
            source_hash = source.commit_hash
        else:
            bp = self.db.index.get_branch(self._active_branch)
            if bp is None:
                return CVCOperationResponse(
                    success=False, operation="branch", message="No active branch"
                )
            source_hash = bp.head_hash

        # Check for name collision
        if self.db.index.get_branch(request.name):
            return CVCOperationResponse(
                success=False,
                operation="branch",
                message=f"Branch '{request.name}' already exists",
            )

        # Create branch pointer
        new_branch = BranchPointer(
            name=request.name,
            head_hash=source_hash,
            description=request.description,
            parent_branch=self._active_branch,
        )
        self.db.index.upsert_branch(new_branch)

        # Switch to the new branch
        old_branch = self._active_branch
        self._active_branch = request.name

        # Reset context window — the agent gets a clean slate
        # Preserve only system-level messages (roadmap / instructions)
        system_msgs = [m for m in self._context_window if m.role == "system"]
        self._context_window = system_msgs
        self._reasoning_trace = ""

        # Inject branch-entry message
        self._context_window.append(
            ContextMessage(
                role="system",
                content=(
                    f"[CVC] Branched to '{request.name}' from {old_branch} "
                    f"at commit {source_hash[:12]}. "
                    f"Goal: {request.description or 'Explore alternative approach'}. "
                    f"Context has been reset for isolated exploration."
                ),
            )
        )

        logger.info("BRANCH '%s' from %s @ %s", request.name, old_branch, source_hash[:12])

        return CVCOperationResponse(
            success=True,
            operation="branch",
            commit_hash=source_hash,
            branch=request.name,
            message=f"Created and switched to branch '{request.name}'",
            detail={"parent_branch": old_branch, "source_commit": source_hash},
        )

    # ======================================================================
    # 4.3  MERGE (Semantic Three-Way Merge)
    # ======================================================================

    def merge(
        self,
        request: CVCMergeRequest,
        synthesized_summary: str | None = None,
    ) -> CVCOperationResponse:
        """
        Semantic Three-Way Merge.

        1. Compute the Lowest Common Ancestor (LCA).
        2. Diff LCA → source and LCA → target.
        3. Synthesise insights (via LLM, passed as *synthesized_summary*).
        4. Inject summary into target branch context and archive source.
        """
        source_bp = self.db.index.get_branch(request.source_branch)
        target_bp = self.db.index.get_branch(request.target_branch)

        if source_bp is None:
            return CVCOperationResponse(
                success=False, operation="merge",
                message=f"Source branch '{request.source_branch}' not found",
            )
        if target_bp is None:
            return CVCOperationResponse(
                success=False, operation="merge",
                message=f"Target branch '{request.target_branch}' not found",
            )

        # 1. LCA
        lca_hash = self.db.index.find_lca(source_bp.head_hash, target_bp.head_hash)

        # 2. Gather source branch insights
        source_blob = self.db.retrieve_blob(source_bp.head_hash)
        source_commits = self.db.index.get_ancestors(source_bp.head_hash, limit=20)
        source_digest = "\n".join(
            f"- [{c.short_hash}] {c.message}" for c in source_commits
        )

        # 3. Build merge summary
        if not synthesized_summary:
            synthesized_summary = (
                f"Merged branch '{request.source_branch}' into '{request.target_branch}'.\n"
                f"LCA: {lca_hash[:12] if lca_hash else 'none'}.\n"
                f"Source commits:\n{source_digest}"
            )

        # 4. Create merge commit
        merge_blob = ContentBlob(
            messages=list(self._context_window),
            reasoning_trace=(
                f"MERGE: {request.source_branch} → {request.target_branch}\n"
                f"{synthesized_summary}"
            ),
        )

        merge_meta = CommitMetadata(
            agent_id=self.config.agent_id,
            mode=self.config.mode,
        )

        merge_commit = CognitiveCommit(
            parent_hashes=[target_bp.head_hash, source_bp.head_hash],
            commit_type=CommitType.MERGE,
            message=synthesized_summary[:200],
            content_blob=merge_blob,
            metadata=merge_meta,
        )

        commit_hash = self.db.store_commit(merge_commit)

        # Advance target HEAD
        self.db.index.advance_head(request.target_branch, commit_hash)

        # Archive source branch
        source_bp.status = BranchStatus.MERGED
        self.db.index.upsert_branch(source_bp)

        # Inject synthesis into context
        self._context_window.append(
            ContextMessage(
                role="system",
                content=(
                    f"[CVC] Merged '{request.source_branch}' → '{request.target_branch}'.\n"
                    f"Synthesis: {synthesized_summary}"
                ),
            )
        )

        # Switch to target
        self._active_branch = request.target_branch

        logger.info("MERGE %s → %s as %s", request.source_branch, request.target_branch, commit_hash[:12])

        return CVCOperationResponse(
            success=True,
            operation="merge",
            commit_hash=commit_hash,
            branch=request.target_branch,
            message=f"Merged '{request.source_branch}' into '{request.target_branch}'",
            detail={
                "lca": lca_hash,
                "source_head": source_bp.head_hash,
                "target_head": target_bp.head_hash,
            },
        )

    # ======================================================================
    # 4.4  RESTORE / TIME-TRAVEL
    # ======================================================================

    def restore(self, request: CVCRestoreRequest) -> CVCOperationResponse:
        """
        The "Undo Button" for the AI mind.

        1. Retrieve the blob from the CAS.
        2. Wipe the current context window.
        3. Re-hydrate the window with the stored state.
        """
        commit = self.db.index.get_commit(request.commit_hash)
        if commit is None:
            return CVCOperationResponse(
                success=False, operation="restore",
                message=f"Commit '{request.commit_hash}' not found",
            )

        blob = self.db.retrieve_blob(commit.commit_hash)
        if blob is None:
            return CVCOperationResponse(
                success=False, operation="restore",
                message=f"Blob for commit '{commit.commit_hash}' could not be reconstructed",
            )

        # Wipe and re-hydrate
        self._context_window = list(blob.messages)
        self._reasoning_trace = blob.reasoning_trace

        # Create a rollback commit recording this action
        rollback_blob = ContentBlob(
            messages=list(self._context_window),
            reasoning_trace=f"ROLLBACK to {commit.short_hash}",
        )
        rollback_commit = CognitiveCommit(
            parent_hashes=[self.head_hash or commit.commit_hash],
            commit_type=CommitType.ROLLBACK,
            message=f"Restored to {commit.short_hash}: {commit.message[:60]}",
            content_blob=rollback_blob,
            metadata=CommitMetadata(
                agent_id=self.config.agent_id,
                mode=self.config.mode,
            ),
        )
        rollback_hash = self.db.store_commit(rollback_commit)
        self.db.index.advance_head(self._active_branch, rollback_hash)

        # Inject restoration notice
        self._context_window.append(
            ContextMessage(
                role="system",
                content=(
                    f"[CVC] Context restored to commit {commit.short_hash} "
                    f"({commit.message[:60]}). All subsequent state has been rolled back."
                ),
            )
        )

        logger.info("RESTORE to %s on %s", commit.short_hash, self._active_branch)

        return CVCOperationResponse(
            success=True,
            operation="restore",
            commit_hash=commit.commit_hash,
            branch=self._active_branch,
            message=f"Restored to {commit.short_hash}",
            detail={
                "restored_commit": commit.commit_hash,
                "rollback_commit": rollback_hash,
                "token_count": rollback_blob.token_count,
            },
        )

    # -- Utility -----------------------------------------------------------

    def switch_branch(self, branch_name: str) -> CVCOperationResponse:
        """Switch the active branch and load its HEAD context."""
        bp = self.db.index.get_branch(branch_name)
        if bp is None:
            return CVCOperationResponse(
                success=False, operation="switch",
                message=f"Branch '{branch_name}' not found",
            )

        blob = self.db.retrieve_blob(bp.head_hash)
        if blob:
            self._context_window = list(blob.messages)
            self._reasoning_trace = blob.reasoning_trace

        self._active_branch = branch_name
        return CVCOperationResponse(
            success=True, operation="switch",
            branch=branch_name, commit_hash=bp.head_hash,
            message=f"Switched to branch '{branch_name}' at {bp.head_hash[:12]}",
        )

    def log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the commit log for the active branch."""
        commits = self.db.index.list_commits(branch=self._active_branch, limit=limit)
        return [
            {
                "hash": c.commit_hash,
                "short": c.short_hash,
                "type": c.commit_type.value,
                "message": c.message,
                "timestamp": c.metadata.timestamp,
                "parents": c.parent_hashes,
                "is_delta": c.is_delta,
            }
            for c in commits
        ]

    # ======================================================================
    # 4.5  RECALL (Natural Language Search)
    # ======================================================================

    def recall(
        self,
        query: str,
        limit: int = 10,
        deep: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search across ALL past conversations using natural language.

        Combines Tier 3 semantic vector search (when available),
        commit message text search, and deep content-blob search
        to find conversations matching the query.

        Returns a list of result dicts (see ContextDatabase.search_conversations).
        """
        return self.db.search_conversations(query, limit=limit, deep=deep)

    # ======================================================================
    # 4.6  EXPORT (Conversation to Markdown)
    # ======================================================================

    def export_markdown(self, commit_hash: str | None = None) -> tuple[str, str]:
        """
        Export a commit's conversation as a structured Markdown document.

        If *commit_hash* is None, exports the current HEAD commit.
        Returns a tuple of (markdown_string, resolved_commit_hash).

        Raises ValueError if the commit or blob is not found.
        """
        # Resolve commit
        if commit_hash is None:
            commit_hash = self.head_hash
        if commit_hash is None:
            raise ValueError("No HEAD commit found. Create a commit first.")

        commit = self.db.index.get_commit(commit_hash)
        if commit is None:
            raise ValueError(f"Commit '{commit_hash}' not found.")

        blob = self.db.retrieve_blob(commit.commit_hash)
        if blob is None:
            raise ValueError(f"Blob for commit '{commit.commit_hash}' could not be reconstructed.")

        # Build markdown
        from datetime import datetime
        lines: list[str] = []

        # Header
        lines.append(f"# CVC Conversation Export")
        lines.append("")
        lines.append(f"**Commit**: `{commit.commit_hash[:12]}`  ")
        lines.append(f"**Branch**: `{self._active_branch}`  ")
        lines.append(f"**Type**: `{commit.commit_type.value}`  ")
        lines.append(f"**Message**: {commit.message}  ")
        ts = datetime.fromtimestamp(commit.metadata.timestamp)
        lines.append(f"**Date**: {ts.strftime('%Y-%m-%d %H:%M:%S')}  ")
        if commit.metadata.provider:
            lines.append(f"**Provider**: `{commit.metadata.provider}`  ")
        if commit.metadata.model:
            lines.append(f"**Model**: `{commit.metadata.model}`  ")
        if commit.metadata.agent_id:
            lines.append(f"**Agent**: `{commit.metadata.agent_id}`  ")
        lines.append(f"**Token Count**: ~{blob.token_count}  ")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Messages
        lines.append("## Conversation")
        lines.append("")

        role_emoji = {
            "system": "⚙️",
            "user": "👤",
            "assistant": "🤖",
            "tool": "🔧",
        }

        for msg in blob.messages:
            emoji = role_emoji.get(msg.role, "❓")
            role_label = msg.role.upper()
            msg_ts = datetime.fromtimestamp(msg.timestamp)
            lines.append(f"### {emoji} {role_label}")
            lines.append(f"*{msg_ts.strftime('%H:%M:%S')}*")
            lines.append("")
            # Handle content — preserve code blocks and formatting
            content = msg.content.strip()
            if content:
                lines.append(content)
            else:
                lines.append("*(empty)*")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Reasoning trace
        if blob.reasoning_trace:
            lines.append("## Reasoning Trace")
            lines.append("")
            lines.append(blob.reasoning_trace)
            lines.append("")

        # Source files
        if blob.source_files:
            lines.append("## Source Files Referenced")
            lines.append("")
            for path, file_hash in sorted(blob.source_files.items()):
                lines.append(f"- `{path}` (`{file_hash[:12]}`)")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Exported by CVC (Cognitive Version Control) on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        return "\n".join(lines), commit.commit_hash

    # ======================================================================
    # 4.7  INJECT (Cross-Project Context Transfer)
    # ======================================================================

    def inject_from_project(
        self,
        source_root: Path,
        query: str,
        limit: int = 5,
    ) -> CVCOperationResponse:
        """
        Pull relevant conversations from another CVC project into the
        current context.

        1. Opens the source project's CVC database (read-only).
        2. Searches for conversations matching *query*.
        3. Extracts matching messages and injects them as system-level
           context into the current project's context window.
        4. Commits the injected context as a new checkpoint.

        Returns a CVCOperationResponse with details about the injection.
        """
        from cvc.core.database import ContextDatabase
        from cvc.core.models import CVCConfig

        source_cvc = source_root / ".cvc"
        if not source_cvc.is_dir():
            return CVCOperationResponse(
                success=False,
                operation="inject",
                message=f"No .cvc/ directory found at '{source_root}'",
            )

        # Open source database
        try:
            source_config = CVCConfig.for_project(project_root=source_root)
            source_db = ContextDatabase(source_config)
        except Exception as exc:
            return CVCOperationResponse(
                success=False,
                operation="inject",
                message=f"Failed to open source CVC database: {exc}",
            )

        # Search the source project
        try:
            results = source_db.search_conversations(query, limit=limit, deep=True)
        except Exception as exc:
            source_db.close()
            return CVCOperationResponse(
                success=False,
                operation="inject",
                message=f"Search failed on source project: {exc}",
            )

        if not results:
            source_db.close()
            return CVCOperationResponse(
                success=False,
                operation="inject",
                message=f"No conversations matching '{query}' found in source project.",
            )

        # Extract relevant messages from matching conversations
        injected_messages: list[ContextMessage] = []
        source_project_name = source_root.name

        for result in results:
            ch = result["commit_hash"]
            try:
                blob = source_db.retrieve_blob(ch)
                if blob is None:
                    continue
            except Exception:
                continue

            # Collect relevant messages — either matching ones or all if few
            if result["matching_messages"]:
                for mm in result["matching_messages"]:
                    injected_messages.append(
                        ContextMessage(
                            role="system",
                            content=(
                                f"[CVC INJECT from '{source_project_name}' "
                                f"commit {ch[:12]}] "
                                f"({mm['role'].upper()}): {mm['content']}"
                            ),
                        )
                    )
            else:
                # No specific matching messages — take assistant messages as context
                assistant_msgs = [m for m in blob.messages if m.role == "assistant"]
                for m in assistant_msgs[:3]:
                    content_preview = m.content[:800]
                    injected_messages.append(
                        ContextMessage(
                            role="system",
                            content=(
                                f"[CVC INJECT from '{source_project_name}' "
                                f"commit {ch[:12]}] "
                                f"({m.role.upper()}): {content_preview}"
                            ),
                        )
                    )

        source_db.close()

        if not injected_messages:
            return CVCOperationResponse(
                success=False,
                operation="inject",
                message="Found matching commits but could not extract messages.",
            )

        # Inject into current context window
        summary_msg = ContextMessage(
            role="system",
            content=(
                f"[CVC] Injected {len(injected_messages)} message(s) from project "
                f"'{source_project_name}' matching query: \"{query}\". "
                f"From {len(results)} matching conversation(s)."
            ),
        )
        self.push_message(summary_msg)
        for msg in injected_messages:
            self.push_message(msg)

        # Auto-commit the injection
        inject_commit_result = self.commit(
            CVCCommitRequest(
                message=f"Injected context from '{source_project_name}' — query: \"{query}\"",
                commit_type=CommitType.CHECKPOINT,
                tags=["inject", f"source:{source_project_name}"],
            )
        )

        detail = {
            "source_project": str(source_root),
            "query": query,
            "matching_commits": len(results),
            "injected_messages": len(injected_messages),
            "commits_searched": [r["short_hash"] for r in results],
        }

        return CVCOperationResponse(
            success=True,
            operation="inject",
            commit_hash=inject_commit_result.commit_hash,
            branch=self._active_branch,
            message=(
                f"Injected {len(injected_messages)} message(s) from "
                f"'{source_project_name}' ({len(results)} matching conversation(s))"
            ),
            detail=detail,
        )

    # ======================================================================
    # 5.1  DIFF (Knowledge / Decision Diff Between Commits)
    # ======================================================================

    def diff(
        self,
        hash_a: str,
        hash_b: str | None = None,
    ) -> dict[str, Any]:
        """
        Compare two commits and show knowledge/decision differences.

        If *hash_b* is None, compares *hash_a* against the current HEAD.
        Returns a structured diff with added/removed messages, changed
        reasoning, source file changes, and metadata differences.
        """
        # Resolve commits
        commit_a = self.db.index.get_commit(hash_a)
        if commit_a is None:
            raise ValueError(f"Commit '{hash_a}' not found.")

        if hash_b is None:
            hash_b = self.head_hash
        if hash_b is None:
            raise ValueError("No HEAD commit found. Create a commit first.")
        commit_b = self.db.index.get_commit(hash_b)
        if commit_b is None:
            raise ValueError(f"Commit '{hash_b}' not found.")

        # Retrieve blobs
        blob_a = self.db.retrieve_blob(commit_a.commit_hash)
        blob_b = self.db.retrieve_blob(commit_b.commit_hash)
        if blob_a is None:
            raise ValueError(f"Blob for commit '{commit_a.commit_hash}' could not be reconstructed.")
        if blob_b is None:
            raise ValueError(f"Blob for commit '{commit_b.commit_hash}' could not be reconstructed.")

        # Build content fingerprints for messages (role + content hash)
        def _msg_key(m: ContextMessage) -> str:
            return f"{m.role}:{hashlib.sha256(m.content.encode()).hexdigest()[:16]}"

        import hashlib
        keys_a = {_msg_key(m) for m in blob_a.messages}
        keys_b = {_msg_key(m) for m in blob_b.messages}

        # Messages only in A (removed going A→B)
        only_a_keys = keys_a - keys_b
        only_b_keys = keys_b - keys_a

        removed_messages = []
        for m in blob_a.messages:
            if _msg_key(m) in only_a_keys:
                removed_messages.append({
                    "role": m.role,
                    "content": m.content[:500],
                    "timestamp": m.timestamp,
                })

        added_messages = []
        for m in blob_b.messages:
            if _msg_key(m) in only_b_keys:
                added_messages.append({
                    "role": m.role,
                    "content": m.content[:500],
                    "timestamp": m.timestamp,
                })

        # Source file diff
        files_a = set(blob_a.source_files.keys())
        files_b = set(blob_b.source_files.keys())
        added_files = sorted(files_b - files_a)
        removed_files = sorted(files_a - files_b)
        modified_files = sorted(
            f for f in files_a & files_b
            if blob_a.source_files[f] != blob_b.source_files[f]
        )

        # Reasoning trace diff
        trace_changed = blob_a.reasoning_trace != blob_b.reasoning_trace
        trace_a = blob_a.reasoning_trace[:1000] if blob_a.reasoning_trace else ""
        trace_b = blob_b.reasoning_trace[:1000] if blob_b.reasoning_trace else ""

        # Metadata comparison
        meta_diffs: dict[str, Any] = {}
        for field in ("provider", "model", "agent_id", "mode"):
            va = getattr(commit_a.metadata, field, None)
            vb = getattr(commit_b.metadata, field, None)
            if va != vb:
                meta_diffs[field] = {"from": va, "to": vb}

        # Token delta
        token_delta = blob_b.token_count - blob_a.token_count

        return {
            "commit_a": {
                "hash": commit_a.commit_hash,
                "short": commit_a.short_hash,
                "message": commit_a.message,
                "type": commit_a.commit_type.value,
                "timestamp": commit_a.metadata.timestamp,
                "message_count": len(blob_a.messages),
                "token_count": blob_a.token_count,
            },
            "commit_b": {
                "hash": commit_b.commit_hash,
                "short": commit_b.short_hash,
                "message": commit_b.message,
                "type": commit_b.commit_type.value,
                "timestamp": commit_b.metadata.timestamp,
                "message_count": len(blob_b.messages),
                "token_count": blob_b.token_count,
            },
            "messages": {
                "added": added_messages,
                "removed": removed_messages,
                "added_count": len(added_messages),
                "removed_count": len(removed_messages),
                "common_count": len(keys_a & keys_b),
            },
            "source_files": {
                "added": added_files,
                "removed": removed_files,
                "modified": modified_files,
            },
            "reasoning_trace": {
                "changed": trace_changed,
                "from": trace_a,
                "to": trace_b,
            },
            "metadata_changes": meta_diffs,
            "token_delta": token_delta,
        }

    # ======================================================================
    # 5.2  STATS (Analytics Dashboard)
    # ======================================================================

    def stats(self) -> dict[str, Any]:
        """
        Aggregate analytics across all commits:
        total tokens, message counts, commit types, providers/models,
        most-discussed source files, branch activity, and timing patterns.
        """
        from datetime import datetime
        from collections import Counter

        all_commits = self.db.index.list_all_commits(limit=10000)
        all_branches = self.db.index.list_branches()

        if not all_commits:
            return {
                "total_commits": 0,
                "message": "No commits found. Create a commit first.",
            }

        total_tokens = 0
        total_messages = 0
        role_counter: Counter[str] = Counter()
        type_counter: Counter[str] = Counter()
        provider_counter: Counter[str] = Counter()
        model_counter: Counter[str] = Counter()
        file_counter: Counter[str] = Counter()
        tag_counter: Counter[str] = Counter()
        hourly_counter: Counter[int] = Counter()
        daily_counter: Counter[str] = Counter()
        commit_sizes: list[int] = []
        timestamps: list[float] = []

        for commit in all_commits:
            type_counter[commit.commit_type.value] += 1
            if commit.metadata.provider:
                provider_counter[commit.metadata.provider] += 1
            if commit.metadata.model:
                model_counter[commit.metadata.model] += 1
            for tag in commit.metadata.tags:
                tag_counter[tag] += 1
            timestamps.append(commit.metadata.timestamp)

            # Try to reconstruct blob for deeper stats
            try:
                blob = self.db.retrieve_blob(commit.commit_hash)
                if blob:
                    total_tokens += blob.token_count
                    msg_count = len(blob.messages)
                    total_messages += msg_count
                    commit_sizes.append(msg_count)
                    for m in blob.messages:
                        role_counter[m.role] += 1
                    for path in blob.source_files:
                        file_counter[path] += 1
                else:
                    commit_sizes.append(0)
            except Exception:
                commit_sizes.append(0)

            # Time patterns
            try:
                dt = datetime.fromtimestamp(commit.metadata.timestamp)
                hourly_counter[dt.hour] += 1
                daily_counter[dt.strftime("%A")] += 1
            except Exception:
                pass

        # Time span
        if timestamps:
            first_ts = min(timestamps)
            last_ts = max(timestamps)
            first_dt = datetime.fromtimestamp(first_ts)
            last_dt = datetime.fromtimestamp(last_ts)
            span_days = max((last_ts - first_ts) / 86400, 0.01)
        else:
            first_dt = last_dt = datetime.now()
            span_days = 0

        # Average commit size
        avg_size = sum(commit_sizes) / len(commit_sizes) if commit_sizes else 0

        # Peak hours
        peak_hours = hourly_counter.most_common(3)
        busiest_day = daily_counter.most_common(1)

        return {
            "total_commits": len(all_commits),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_tokens * 0.000015, 4),  # rough estimate
            "branches": {
                "total": len(all_branches),
                "active": sum(1 for b in all_branches if b.status == BranchStatus.ACTIVE),
                "merged": sum(1 for b in all_branches if b.status == BranchStatus.MERGED),
                "names": [b.name for b in all_branches],
            },
            "commit_types": dict(type_counter.most_common()),
            "messages_by_role": dict(role_counter.most_common()),
            "providers": dict(provider_counter.most_common()),
            "models": dict(model_counter.most_common()),
            "top_files": dict(file_counter.most_common(15)),
            "top_tags": dict(tag_counter.most_common(10)),
            "time_span": {
                "first_commit": first_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "last_commit": last_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "span_days": round(span_days, 1),
                "commits_per_day": round(len(all_commits) / max(span_days, 0.01), 1),
            },
            "average_commit_size": round(avg_size, 1),
            "peak_hours": [{"hour": h, "commits": c} for h, c in peak_hours],
            "busiest_day": busiest_day[0][0] if busiest_day else "N/A",
            "current_branch": self._active_branch,
            "current_context_messages": len(self._context_window),
        }

    # ======================================================================
    # 5.3  COMPACT (AI-Powered Context Compression)
    # ======================================================================

    def compact(
        self,
        smart: bool = True,
        keep_recent: int = 10,
        target_ratio: float = 0.5,
    ) -> CVCOperationResponse:
        """
        Compress the context window to reduce token usage while preserving
        key decisions, architecture notes, and recent conversation flow.

        If *smart* is True, uses heuristic-based intelligent compression:
          - Preserves system messages (instructions, injected context)
          - Preserves the most recent *keep_recent* messages
          - Summarises older user/assistant exchanges into condensed form
          - Retains messages containing code blocks, decisions, or key terms

        If *smart* is False, simply truncates to *keep_recent* messages.

        *target_ratio* is the target compression ratio (0.5 = keep ~50% of tokens).
        """
        if not self._context_window:
            return CVCOperationResponse(
                success=False,
                operation="compact",
                message="Context window is empty. Nothing to compact.",
            )

        original_count = len(self._context_window)
        original_tokens = sum(len(m.content.split()) for m in self._context_window)

        if not smart:
            # Simple truncation — keep only recent messages
            if original_count <= keep_recent:
                return CVCOperationResponse(
                    success=True,
                    operation="compact",
                    message=f"Context already small enough ({original_count} messages).",
                    detail={
                        "original_messages": original_count,
                        "final_messages": original_count,
                        "compression_ratio": 1.0,
                    },
                )

            kept = self._context_window[-keep_recent:]
            removed_count = original_count - keep_recent

            # Add a compaction notice
            summary_msg = ContextMessage(
                role="system",
                content=(
                    f"[CVC COMPACT] Truncated {removed_count} older messages. "
                    f"Kept the {keep_recent} most recent messages."
                ),
            )
            self._context_window = [summary_msg] + kept
            self._save_persistent_cache()

            final_tokens = sum(len(m.content.split()) for m in self._context_window)

            return CVCOperationResponse(
                success=True,
                operation="compact",
                branch=self._active_branch,
                message=f"Truncated {removed_count} messages (kept {keep_recent} recent).",
                detail={
                    "original_messages": original_count,
                    "final_messages": len(self._context_window),
                    "original_tokens": original_tokens,
                    "final_tokens": final_tokens,
                    "compression_ratio": round(final_tokens / max(original_tokens, 1), 3),
                    "mode": "truncate",
                },
            )

        # ── Smart compression ──────────────────────────────────────────────

        # Key terms that indicate important messages worth preserving
        KEY_TERMS = {
            "decision", "decided", "architecture", "design", "important",
            "critical", "error", "fix", "bug", "security", "api", "schema",
            "database", "migration", "deploy", "config", "breaking",
            "requirement", "constraint", "must", "should", "trade-off",
            "conclusion", "solution", "approach", "strategy", "pattern",
        }

        def _is_important(msg: ContextMessage) -> bool:
            """Heuristic: is this message important enough to keep verbatim?"""
            # System messages are always important
            if msg.role == "system":
                return True
            content_lower = msg.content.lower()
            # Messages with code blocks
            if "```" in msg.content:
                return True
            # Messages with key decision terms
            if any(term in content_lower for term in KEY_TERMS):
                return True
            # Very short messages (questions, confirmations) — keep
            if len(msg.content) < 100:
                return True
            return False

        # Split into zones
        if original_count <= keep_recent:
            return CVCOperationResponse(
                success=True,
                operation="compact",
                message=f"Context already small enough ({original_count} messages).",
                detail={
                    "original_messages": original_count,
                    "final_messages": original_count,
                    "compression_ratio": 1.0,
                },
            )

        older = self._context_window[:-keep_recent]
        recent = self._context_window[-keep_recent:]

        # Classify older messages
        important_msgs: list[ContextMessage] = []
        compressible_msgs: list[ContextMessage] = []

        for msg in older:
            if _is_important(msg):
                important_msgs.append(msg)
            else:
                compressible_msgs.append(msg)

        # Compress the compressible messages into summaries
        # Group into chunks of ~5 messages for summarisation
        summaries: list[ContextMessage] = []
        chunk_size = 5

        for i in range(0, len(compressible_msgs), chunk_size):
            chunk = compressible_msgs[i:i + chunk_size]

            # Build a condensed summary of the chunk
            chunk_roles = [m.role for m in chunk]
            role_counts = {}
            for r in chunk_roles:
                role_counts[r] = role_counts.get(r, 0) + 1

            # Extract key points from each message
            key_points: list[str] = []
            for m in chunk:
                # Take first sentence or first 150 chars
                content = m.content.strip()
                first_line = content.split("\n")[0][:150]
                if len(content) > 150:
                    key_points.append(f"[{m.role}] {first_line}…")
                else:
                    key_points.append(f"[{m.role}] {first_line}")

            summary_text = (
                f"[CVC COMPACT] Summary of {len(chunk)} messages "
                f"({', '.join(f'{c} {r}' for r, c in role_counts.items())}):\n"
                + "\n".join(f"  • {kp}" for kp in key_points)
            )

            summaries.append(
                ContextMessage(role="system", content=summary_text)
            )

        # Reassemble: compaction header + important old msgs + summaries + recent
        compaction_header = ContextMessage(
            role="system",
            content=(
                f"[CVC COMPACT] Context compacted: {original_count} → "
                f"{len(important_msgs) + len(summaries) + len(recent) + 1} messages. "
                f"{len(compressible_msgs)} messages summarised, "
                f"{len(important_msgs)} important messages preserved verbatim."
            ),
        )

        self._context_window = (
            [compaction_header]
            + important_msgs
            + summaries
            + recent
        )
        self._save_persistent_cache()

        final_count = len(self._context_window)
        final_tokens = sum(len(m.content.split()) for m in self._context_window)

        # Auto-commit the compacted state
        compact_commit = self.commit(
            CVCCommitRequest(
                message=f"Smart compaction: {original_count} → {final_count} messages",
                commit_type=CommitType.CHECKPOINT,
                tags=["compact", "smart"],
            )
        )

        return CVCOperationResponse(
            success=True,
            operation="compact",
            commit_hash=compact_commit.commit_hash,
            branch=self._active_branch,
            message=(
                f"Smart compaction: {original_count} → {final_count} messages "
                f"({original_tokens} → {final_tokens} tokens)"
            ),
            detail={
                "original_messages": original_count,
                "final_messages": final_count,
                "original_tokens": original_tokens,
                "final_tokens": final_tokens,
                "compression_ratio": round(final_tokens / max(original_tokens, 1), 3),
                "important_preserved": len(important_msgs),
                "summarised_chunks": len(summaries),
                "recent_kept": len(recent),
                "mode": "smart",
            },
        )

    # ======================================================================
    # 5.4  TIMELINE (Branch-Aware Commit Timeline)
    # ======================================================================

    def timeline(self, limit: int = 50) -> dict[str, Any]:
        """
        Build a complete timeline of all commits across all branches,
        including branch points, merges, and provider/model information.

        Returns structured data suitable for rendering an ASCII timeline
        or a rich visual in the CLI.
        """
        from datetime import datetime

        all_branches = self.db.index.list_branches()
        all_commits = self.db.index.list_all_commits(limit=limit)

        if not all_commits:
            return {"total_commits": 0, "branches": [], "events": []}

        # Build a commit-to-branch mapping
        commit_branch_map: dict[str, list[str]] = {}
        for branch in all_branches:
            ancestors = self.db.index.get_ancestors(branch.head_hash, limit=limit)
            for c in ancestors:
                commit_branch_map.setdefault(c.commit_hash, []).append(branch.name)

        # Build timeline events
        events: list[dict[str, Any]] = []
        seen: set[str] = set()

        for commit in all_commits:
            if commit.commit_hash in seen:
                continue
            seen.add(commit.commit_hash)

            try:
                dt = datetime.fromtimestamp(commit.metadata.timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = "unknown"

            branches = commit_branch_map.get(commit.commit_hash, ["?"])

            # Determine event type
            if commit.commit_type == CommitType.MERGE:
                event_type = "merge"
                icon = "⊕"
            elif commit.commit_type == CommitType.ANCHOR:
                event_type = "anchor"
                icon = "◆"
            elif commit.commit_type == CommitType.ROLLBACK:
                event_type = "rollback"
                icon = "↺"
            elif len(commit.parent_hashes) == 0:
                event_type = "genesis"
                icon = "★"
            else:
                event_type = "commit"
                icon = "●"

            # Check if this is a branch point (appears in multiple branches)
            is_branch_point = len(branches) > 1

            events.append({
                "hash": commit.commit_hash,
                "short": commit.short_hash,
                "message": commit.message,
                "type": commit.commit_type.value,
                "event_type": event_type,
                "icon": icon,
                "timestamp": commit.metadata.timestamp,
                "time_str": time_str,
                "provider": commit.metadata.provider or "",
                "model": commit.metadata.model or "",
                "branches": branches,
                "is_branch_point": is_branch_point,
                "is_merge": commit.commit_type == CommitType.MERGE,
                "parents": commit.parent_hashes,
                "is_delta": commit.is_delta,
                "tags": commit.metadata.tags,
            })

        # Sort by timestamp (newest first)
        events.sort(key=lambda e: e["timestamp"], reverse=True)

        # Trim to limit
        events = events[:limit]

        return {
            "total_commits": len(events),
            "branches": [
                {
                    "name": b.name,
                    "head": b.head_hash[:12],
                    "status": b.status.value,
                    "is_active": b.name == self._active_branch,
                }
                for b in all_branches
            ],
            "events": events,
            "active_branch": self._active_branch,
        }
