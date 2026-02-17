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
