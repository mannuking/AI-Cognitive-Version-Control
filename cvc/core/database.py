"""
cvc.core.database — Three-Tiered Context Database (CDB).

Tier 1 (Index):   SQLite — commit graph, branch pointers, metadata.
Tier 2 (Blob):    Content-Addressable Storage on local disk (.cvc/objects/).
Tier 3 (Semantic): Optional Chroma vector store for similarity search.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Sequence

import zstandard as zstd

from cvc.core.models import (
    BranchPointer,
    BranchStatus,
    CognitiveCommit,
    CommitMetadata,
    CommitType,
    ContentBlob,
    CVCConfig,
)

logger = logging.getLogger("cvc.database")

# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS commits (
    commit_hash     TEXT PRIMARY KEY,
    parent_hashes   TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    commit_type     TEXT    NOT NULL DEFAULT 'checkpoint',
    message         TEXT    NOT NULL DEFAULT '',
    is_delta        INTEGER NOT NULL DEFAULT 0,
    anchor_hash     TEXT,
    blob_key        TEXT    NOT NULL,                -- CAS key for content blob
    metadata_json   TEXT    NOT NULL DEFAULT '{}',
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS branches (
    name            TEXT PRIMARY KEY,
    head_hash       TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'active',
    parent_branch   TEXT,
    description     TEXT    NOT NULL DEFAULT '',
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS git_links (
    git_sha         TEXT PRIMARY KEY,
    cvc_hash        TEXT NOT NULL,
    created_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commits_created ON commits(created_at);
CREATE INDEX IF NOT EXISTS idx_commits_type    ON commits(commit_type);
CREATE INDEX IF NOT EXISTS idx_git_links_cvc   ON git_links(cvc_hash);
"""

_AUDIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT    NOT NULL,           -- 'commit', 'branch', 'merge', 'restore', 'compact', 'inject', 'sync_push', 'sync_pull'
    commit_hash     TEXT,
    branch          TEXT,
    agent_id        TEXT    NOT NULL DEFAULT 'sofia',
    provider        TEXT,
    model           TEXT,
    action_detail   TEXT    NOT NULL DEFAULT '{}',  -- JSON with specifics
    source_mode     TEXT,                        -- 'cli', 'mcp', 'proxy'
    user_identity   TEXT,                        -- OS username or configured identity
    machine_id      TEXT,                        -- Machine hostname
    risk_level      TEXT    NOT NULL DEFAULT 'low',  -- 'low', 'medium', 'high', 'critical'
    code_generated  INTEGER NOT NULL DEFAULT 0,  -- Whether AI-generated code was involved
    files_affected  TEXT    NOT NULL DEFAULT '[]', -- JSON array of file paths
    token_count     INTEGER NOT NULL DEFAULT 0,
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_remotes (
    name            TEXT PRIMARY KEY,
    remote_path     TEXT    NOT NULL,            -- Path or URL to remote CVC repo
    last_push_hash  TEXT,
    last_pull_hash  TEXT,
    last_sync_at    REAL,
    created_at      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created  ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_type     ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_risk     ON audit_log(risk_level);
CREATE INDEX IF NOT EXISTS idx_audit_agent    ON audit_log(agent_id);
"""


# ---------------------------------------------------------------------------
# Tier 1 — SQLite Index Database
# ---------------------------------------------------------------------------

class IndexDB:
    """Synchronous SQLite index for the commit graph and branch pointers."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.executescript(_AUDIT_SCHEMA_SQL)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()

    # -- Commits -----------------------------------------------------------

    def insert_commit(self, commit: CognitiveCommit, blob_key: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO commits
               (commit_hash, parent_hashes, commit_type, message,
                is_delta, anchor_hash, blob_key, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                commit.commit_hash,
                json.dumps(commit.parent_hashes),
                commit.commit_type.value,
                commit.message,
                int(commit.is_delta),
                commit.anchor_hash,
                blob_key,
                commit.metadata.model_dump_json(),
                commit.metadata.timestamp,
            ),
        )
        self._conn.commit()

    def get_commit(self, commit_hash: str) -> CognitiveCommit | None:
        """Fetch a commit by full or short (prefix) hash."""
        row = self._conn.execute(
            "SELECT * FROM commits WHERE commit_hash = ?", (commit_hash,)
        ).fetchone()
        if row is None:
            # Try prefix match
            row = self._conn.execute(
                "SELECT * FROM commits WHERE commit_hash LIKE ? LIMIT 1",
                (f"{commit_hash}%",),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_commit(row)

    def get_ancestors(self, commit_hash: str, limit: int = 100) -> list[CognitiveCommit]:
        """Walk the parent chain backwards, returning up to *limit* ancestors."""
        visited: list[CognitiveCommit] = []
        queue = [commit_hash]
        seen: set[str] = set()
        while queue and len(visited) < limit:
            h = queue.pop(0)
            if h in seen:
                continue
            seen.add(h)
            c = self.get_commit(h)
            if c is None:
                continue
            visited.append(c)
            queue.extend(c.parent_hashes)
        return visited

    def find_lca(self, hash_a: str, hash_b: str) -> str | None:
        """Find the Lowest Common Ancestor of two commits."""
        ancestors_a: set[str] = set()
        queue = [hash_a]
        while queue:
            h = queue.pop(0)
            if h in ancestors_a:
                continue
            ancestors_a.add(h)
            c = self.get_commit(h)
            if c:
                queue.extend(c.parent_hashes)

        queue = [hash_b]
        seen: set[str] = set()
        while queue:
            h = queue.pop(0)
            if h in seen:
                continue
            seen.add(h)
            if h in ancestors_a:
                return h
            c = self.get_commit(h)
            if c:
                queue.extend(c.parent_hashes)
        return None

    def list_commits(
        self,
        branch: str | None = None,
        limit: int = 50,
    ) -> list[CognitiveCommit]:
        """List recent commits, optionally scoped to a branch."""
        if branch:
            bp = self.get_branch(branch)
            if bp is None:
                return []
            return self.get_ancestors(bp.head_hash, limit=limit)
        rows = self._conn.execute(
            "SELECT * FROM commits ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_commit(r) for r in rows]

    def count_commits_since_anchor(self, commit_hash: str) -> int:
        """Count how many commits exist from *commit_hash* back to the last anchor."""
        count = 0
        h: str | None = commit_hash
        while h:
            c = self.get_commit(h)
            if c is None:
                break
            if c.commit_type == CommitType.ANCHOR or not c.is_delta:
                break
            count += 1
            h = c.parent_hashes[0] if c.parent_hashes else None
        return count

    # -- Branches ----------------------------------------------------------

    def upsert_branch(self, branch: BranchPointer) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO branches
               (name, head_hash, status, parent_branch, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                branch.name,
                branch.head_hash,
                branch.status.value,
                branch.parent_branch,
                branch.description,
                branch.created_at,
            ),
        )
        self._conn.commit()

    def get_branch(self, name: str) -> BranchPointer | None:
        row = self._conn.execute(
            "SELECT * FROM branches WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return BranchPointer(
            name=row["name"],
            head_hash=row["head_hash"],
            status=BranchStatus(row["status"]),
            parent_branch=row["parent_branch"],
            description=row["description"],
            created_at=row["created_at"],
        )

    def list_branches(self) -> list[BranchPointer]:
        rows = self._conn.execute(
            "SELECT * FROM branches ORDER BY created_at DESC"
        ).fetchall()
        return [
            BranchPointer(
                name=r["name"],
                head_hash=r["head_hash"],
                status=BranchStatus(r["status"]),
                parent_branch=r["parent_branch"],
                description=r["description"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def advance_head(self, branch_name: str, new_hash: str) -> None:
        self._conn.execute(
            "UPDATE branches SET head_hash = ? WHERE name = ?",
            (new_hash, branch_name),
        )
        self._conn.commit()

    # -- Git Links ---------------------------------------------------------

    def link_git_commit(self, git_sha: str, cvc_hash: str, ts: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO git_links (git_sha, cvc_hash, created_at) VALUES (?, ?, ?)",
            (git_sha, cvc_hash, ts),
        )
        self._conn.commit()

    def get_cvc_hash_for_git(self, git_sha: str) -> str | None:
        row = self._conn.execute(
            "SELECT cvc_hash FROM git_links WHERE git_sha = ?", (git_sha,)
        ).fetchone()
        return row["cvc_hash"] if row else None

    # -- Full-text search --------------------------------------------------

    def search_commits(self, query: str, limit: int = 20) -> list[CognitiveCommit]:
        """
        Search commits whose message contains *query* (case-insensitive).
        Returns up to *limit* matching commits ordered by recency.
        """
        rows = self._conn.execute(
            "SELECT * FROM commits WHERE message LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_commit(r) for r in rows]

    def list_all_commits(self, limit: int = 500) -> list[CognitiveCommit]:
        """List all commits across all branches, ordered by recency."""
        rows = self._conn.execute(
            "SELECT * FROM commits ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_commit(r) for r in rows]

    def get_blob_key(self, commit_hash: str) -> str | None:
        """Public accessor for a commit's blob key."""
        row = self._conn.execute(
            "SELECT blob_key FROM commits WHERE commit_hash = ?", (commit_hash,)
        ).fetchone()
        if row is None:
            row = self._conn.execute(
                "SELECT blob_key FROM commits WHERE commit_hash LIKE ? LIMIT 1",
                (f"{commit_hash}%",),
            ).fetchone()
        return row["blob_key"] if row else None

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _row_to_commit(row: sqlite3.Row) -> CognitiveCommit:
        return CognitiveCommit(
            commit_hash=row["commit_hash"],
            parent_hashes=json.loads(row["parent_hashes"]),
            commit_type=CommitType(row["commit_type"]),
            message=row["message"],
            is_delta=bool(row["is_delta"]),
            anchor_hash=row["anchor_hash"],
            content_blob=ContentBlob(),   # Hydrated separately from CAS
            metadata=CommitMetadata.model_validate_json(row["metadata_json"]),
        )

    # -- Audit log ---------------------------------------------------------

    def insert_audit_event(
        self,
        event_type: str,
        commit_hash: str | None = None,
        branch: str | None = None,
        agent_id: str = "sofia",
        provider: str | None = None,
        model: str | None = None,
        action_detail: dict[str, Any] | None = None,
        source_mode: str | None = None,
        user_identity: str | None = None,
        machine_id: str | None = None,
        risk_level: str = "low",
        code_generated: bool = False,
        files_affected: list[str] | None = None,
        token_count: int = 0,
    ) -> int:
        """Insert an audit log entry and return the audit_id."""
        import platform
        _user = user_identity or os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
        _machine = machine_id or platform.node()
        cursor = self._conn.execute(
            """INSERT INTO audit_log
               (event_type, commit_hash, branch, agent_id, provider, model,
                action_detail, source_mode, user_identity, machine_id,
                risk_level, code_generated, files_affected, token_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_type,
                commit_hash,
                branch,
                agent_id,
                provider,
                model,
                json.dumps(action_detail or {}),
                source_mode,
                _user,
                _machine,
                risk_level,
                int(code_generated),
                json.dumps(files_affected or []),
                token_count,
                time.time(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def query_audit_log(
        self,
        event_type: str | None = None,
        risk_level: str | None = None,
        agent_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the audit log with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if risk_level:
            conditions.append("risk_level = ?")
            params.append(risk_level)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)
        if until is not None:
            conditions.append("created_at <= ?")
            params.append(until)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = self._conn.execute(
            f"SELECT * FROM audit_log WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()

        return [
            {
                "audit_id": r["audit_id"],
                "event_type": r["event_type"],
                "commit_hash": r["commit_hash"],
                "branch": r["branch"],
                "agent_id": r["agent_id"],
                "provider": r["provider"],
                "model": r["model"],
                "action_detail": json.loads(r["action_detail"]) if r["action_detail"] else {},
                "source_mode": r["source_mode"],
                "user_identity": r["user_identity"],
                "machine_id": r["machine_id"],
                "risk_level": r["risk_level"],
                "code_generated": bool(r["code_generated"]),
                "files_affected": json.loads(r["files_affected"]) if r["files_affected"] else [],
                "token_count": r["token_count"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def audit_summary(self) -> dict[str, Any]:
        """Return aggregate audit statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        if total == 0:
            return {"total_events": 0}

        by_type = self._conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM audit_log GROUP BY event_type ORDER BY cnt DESC"
        ).fetchall()
        by_risk = self._conn.execute(
            "SELECT risk_level, COUNT(*) as cnt FROM audit_log GROUP BY risk_level ORDER BY cnt DESC"
        ).fetchall()
        by_agent = self._conn.execute(
            "SELECT agent_id, COUNT(*) as cnt FROM audit_log GROUP BY agent_id ORDER BY cnt DESC"
        ).fetchall()
        by_provider = self._conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM audit_log WHERE provider IS NOT NULL GROUP BY provider ORDER BY cnt DESC"
        ).fetchall()
        code_gen_count = self._conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE code_generated = 1"
        ).fetchone()[0]
        total_tokens = self._conn.execute(
            "SELECT COALESCE(SUM(token_count), 0) FROM audit_log"
        ).fetchone()[0]
        first_ts = self._conn.execute(
            "SELECT MIN(created_at) FROM audit_log"
        ).fetchone()[0]
        last_ts = self._conn.execute(
            "SELECT MAX(created_at) FROM audit_log"
        ).fetchone()[0]

        return {
            "total_events": total,
            "events_by_type": {r["event_type"]: r["cnt"] for r in by_type},
            "events_by_risk": {r["risk_level"]: r["cnt"] for r in by_risk},
            "events_by_agent": {r["agent_id"]: r["cnt"] for r in by_agent},
            "events_by_provider": {r["provider"]: r["cnt"] for r in by_provider},
            "code_generation_events": code_gen_count,
            "total_tokens_audited": total_tokens,
            "first_event": first_ts,
            "last_event": last_ts,
        }

    # -- Sync remotes ------------------------------------------------------

    def upsert_remote(
        self, name: str, remote_path: str, last_push: str | None = None,
        last_pull: str | None = None,
    ) -> None:
        """Create or update a sync remote."""
        now = time.time()
        existing = self._conn.execute(
            "SELECT * FROM sync_remotes WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            updates = ["remote_path = ?", "last_sync_at = ?"]
            params: list[Any] = [remote_path, now]
            if last_push is not None:
                updates.append("last_push_hash = ?")
                params.append(last_push)
            if last_pull is not None:
                updates.append("last_pull_hash = ?")
                params.append(last_pull)
            params.append(name)
            self._conn.execute(
                f"UPDATE sync_remotes SET {', '.join(updates)} WHERE name = ?",
                params,
            )
        else:
            self._conn.execute(
                """INSERT INTO sync_remotes (name, remote_path, last_push_hash, last_pull_hash, last_sync_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, remote_path, last_push, last_pull, now, now),
            )
        self._conn.commit()

    def get_remote(self, name: str) -> dict[str, Any] | None:
        """Get a sync remote by name."""
        row = self._conn.execute(
            "SELECT * FROM sync_remotes WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return {
            "name": row["name"],
            "remote_path": row["remote_path"],
            "last_push_hash": row["last_push_hash"],
            "last_pull_hash": row["last_pull_hash"],
            "last_sync_at": row["last_sync_at"],
            "created_at": row["created_at"],
        }

    def list_remotes(self) -> list[dict[str, Any]]:
        """List all configured sync remotes."""
        rows = self._conn.execute(
            "SELECT * FROM sync_remotes ORDER BY created_at"
        ).fetchall()
        return [
            {
                "name": r["name"],
                "remote_path": r["remote_path"],
                "last_push_hash": r["last_push_hash"],
                "last_pull_hash": r["last_pull_hash"],
                "last_sync_at": r["last_sync_at"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_raw_commit_row(self, commit_hash: str) -> dict[str, Any] | None:
        """Get the raw SQLite row for a commit (for sync transfer)."""
        row = self._conn.execute(
            "SELECT * FROM commits WHERE commit_hash = ?", (commit_hash,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Tier 2 — Content-Addressable Storage (CAS)
# ---------------------------------------------------------------------------

class BlobStore:
    """
    Git-style content-addressable blob store.

    Objects are stored as:  .cvc/objects/<hash[:2]>/<hash[2:]>
    All blobs are Zstandard-compressed before writing.
    """

    ZSTD_LEVEL = 6

    def __init__(self, objects_dir: Path) -> None:
        self._root = objects_dir
        self._root.mkdir(parents=True, exist_ok=True)
        self._cctx = zstd.ZstdCompressor(level=self.ZSTD_LEVEL)
        self._dctx = zstd.ZstdDecompressor()

    def _path_for(self, key: str) -> Path:
        return self._root / key[:2] / key[2:]

    def put(self, data: bytes) -> str:
        """Store raw bytes, returning the SHA-256 content address."""
        key = hashlib.sha256(data).hexdigest()
        path = self._path_for(key)
        if path.exists():
            return key  # Deduplication — already stored
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._cctx.compress(data))
        return key

    def get(self, key: str) -> bytes | None:
        """Retrieve and decompress a blob by its SHA-256 key."""
        path = self._path_for(key)
        if not path.exists():
            return None
        return self._dctx.decompress(path.read_bytes())

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def put_json(self, obj: Any) -> str:
        """Convenience: serialise a JSON-compatible object and store it."""
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
        return self.put(raw.encode("utf-8"))

    def get_json(self, key: str) -> Any | None:
        data = self.get(key)
        if data is None:
            return None
        return json.loads(data.decode("utf-8"))

    def delete(self, key: str) -> bool:
        path = self._path_for(key)
        if path.exists():
            path.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Tier 3 — Semantic Vector Store (optional)
# ---------------------------------------------------------------------------

class SemanticStore:
    """
    Thin wrapper around Chroma for commit-summary similarity search.

    This tier is optional; if Chroma is not installed, all operations
    degrade gracefully to no-ops.
    """

    def __init__(self, persist_dir: Path, enabled: bool = False) -> None:
        self._enabled = enabled
        self._collection = None
        if not enabled:
            return
        try:
            import chromadb  # type: ignore[import-untyped]

            client = chromadb.PersistentClient(path=str(persist_dir))
            self._collection = client.get_or_create_collection(
                name="cvc_commits",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Chroma vector store initialised at %s", persist_dir)
        except ImportError:
            logger.warning("chromadb not installed — Tier 3 disabled")
            self._enabled = False
        except Exception as exc:
            # ChromaDB crashes on Python 3.14+ due to pydantic v1 incompatibility
            logger.warning("chromadb failed to initialise — Tier 3 disabled: %s", exc)
            self._enabled = False

    @property
    def available(self) -> bool:
        return self._enabled and self._collection is not None

    def add(self, commit_hash: str, summary: str, metadata: dict[str, Any] | None = None) -> None:
        if not self.available:
            return
        assert self._collection is not None
        self._collection.upsert(
            ids=[commit_hash],
            documents=[summary],
            metadatas=[metadata or {}],
        )

    def search(self, query: str, n: int = 5) -> list[dict[str, Any]]:
        if not self.available:
            return []
        assert self._collection is not None
        results = self._collection.query(query_texts=[query], n_results=n)
        out: list[dict[str, Any]] = []
        for i, doc_id in enumerate(results["ids"][0]):
            out.append({
                "commit_hash": doc_id,
                "document": results["documents"][0][i] if results["documents"] else "",
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
            })
        return out


# ---------------------------------------------------------------------------
# Delta Compression Engine
# ---------------------------------------------------------------------------

class DeltaEngine:
    """
    Delta compression between context blobs using a simple binary diff.

    Implements the concept of VCDIFF / xdelta-style delta encoding described
    in the CVC paper.  For production deployments this should delegate to
    a compiled VCDIFF library; here we use Zstandard *dictionary* compression
    as an efficient, pure-Python-accessible approximation that achieves
    comparable compression ratios on sequential text data.
    """

    def __init__(self) -> None:
        self._cctx = zstd.ZstdCompressor(level=9)
        self._dctx = zstd.ZstdDecompressor()

    def compute_delta(self, anchor_data: bytes, target_data: bytes) -> bytes:
        """
        Compute a delta from *anchor_data* → *target_data*.

        Uses Zstandard dictionary compression: the anchor serves as the
        dictionary, and only the diff against it is stored.
        """
        dict_data = zstd.ZstdCompressionDict(anchor_data)
        cctx = zstd.ZstdCompressor(level=9, dict_data=dict_data)
        return cctx.compress(target_data)

    def apply_delta(self, anchor_data: bytes, delta: bytes) -> bytes:
        """Reconstruct *target_data* by applying *delta* on top of *anchor_data*."""
        dict_data = zstd.ZstdCompressionDict(anchor_data)
        dctx = zstd.ZstdDecompressor(dict_data=dict_data)
        return dctx.decompress(delta)


# ---------------------------------------------------------------------------
# Context Database — unified façade
# ---------------------------------------------------------------------------

class ContextDatabase:
    """
    Unified façade over all three tiers of the Context Database.

    Provides high-level methods used by the CVC operations layer
    (commit, branch, merge, restore).
    """

    def __init__(self, config: CVCConfig) -> None:
        config.ensure_dirs()
        self.config = config
        self.index = IndexDB(config.db_path)
        self.blobs = BlobStore(config.objects_dir)
        self.vectors = SemanticStore(config.chroma_persist_dir, config.vector_enabled)
        self.delta_engine = DeltaEngine()
        self._ensure_default_branch()

    # -- High-level operations ---------------------------------------------

    def store_commit(self, commit: CognitiveCommit) -> str:
        """
        Persist a CognitiveCommit across all three tiers.

        Handles delta compression: if the commit count since the last anchor
        exceeds ``config.anchor_interval``, a full anchor is stored instead.
        """
        raw_blob = commit.content_blob.canonical_bytes()

        # Decide: anchor or delta?
        parent_count = 0
        if commit.parent_hashes:
            parent_count = self.index.count_commits_since_anchor(commit.parent_hashes[0])

        if parent_count >= self.config.anchor_interval or not commit.parent_hashes:
            # Store full anchor
            blob_key = self.blobs.put(raw_blob)
            commit.is_delta = False
            commit.anchor_hash = None
            if commit.commit_type != CommitType.MERGE:
                commit.commit_type = CommitType.ANCHOR
        else:
            # Attempt delta against nearest anchor
            anchor_commit = self._find_nearest_anchor(commit.parent_hashes[0])
            if anchor_commit:
                anchor_blob = self.blobs.get(self._get_blob_key(anchor_commit.commit_hash))
                if anchor_blob is not None:
                    delta = self.delta_engine.compute_delta(anchor_blob, raw_blob)
                    blob_key = self.blobs.put(delta)
                    commit.is_delta = True
                    commit.anchor_hash = anchor_commit.commit_hash
                else:
                    blob_key = self.blobs.put(raw_blob)
            else:
                blob_key = self.blobs.put(raw_blob)

        # Compute Merkle hash *after* deciding delta/anchor
        commit.compute_hash()

        # Tier 1: Index
        self.index.insert_commit(commit, blob_key)

        # Tier 3: Vector (best-effort)
        if self.vectors.available and commit.message:
            self.vectors.add(
                commit.commit_hash,
                commit.message,
                {"type": commit.commit_type.value, "ts": commit.metadata.timestamp},
            )

        logger.info(
            "Stored commit %s [%s] %s",
            commit.short_hash,
            "delta" if commit.is_delta else "full",
            commit.message[:80],
        )
        return commit.commit_hash

    def retrieve_blob(self, commit_hash: str) -> ContentBlob | None:
        """
        Fully reconstruct the ContentBlob for a commit, resolving deltas.
        """
        commit = self.index.get_commit(commit_hash)
        if commit is None:
            return None

        blob_key = self._get_blob_key(commit_hash)
        if blob_key is None:
            return None

        raw = self.blobs.get(blob_key)
        if raw is None:
            return None

        if commit.is_delta and commit.anchor_hash:
            anchor_blob_key = self._get_blob_key(commit.anchor_hash)
            if anchor_blob_key is None:
                logger.error("Anchor %s missing for delta commit %s", commit.anchor_hash, commit_hash)
                return None
            anchor_data = self.blobs.get(anchor_blob_key)
            if anchor_data is None:
                return None
            reconstructed = self.delta_engine.apply_delta(anchor_data, raw)
            return ContentBlob.model_validate_json(reconstructed)

        return ContentBlob.model_validate_json(raw)

    def search_similar(self, query: str, n: int = 5) -> list[dict]:
        """Semantic search over commit summaries."""
        return self.vectors.search(query, n)

    def search_conversations(
        self,
        query: str,
        limit: int = 10,
        deep: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search across all conversations: semantic + text.

        Returns a list of dicts with keys:
          commit_hash, short_hash, message, timestamp, provider, model,
          relevance_source ('semantic' | 'message' | 'content'),
          distance (float, lower = more relevant),
          matching_messages (list of relevant messages from the blob).

        If *deep* is True, also searches inside content blobs for query terms.
        """
        results: dict[str, dict[str, Any]] = {}

        # 1. Semantic vector search (if available)
        if self.vectors.available:
            semantic_hits = self.vectors.search(query, n=limit)
            for hit in semantic_hits:
                ch = hit["commit_hash"]
                commit = self.index.get_commit(ch)
                if commit is None:
                    continue
                results[ch] = {
                    "commit_hash": ch,
                    "short_hash": ch[:12],
                    "message": commit.message,
                    "timestamp": commit.metadata.timestamp,
                    "provider": commit.metadata.provider or "",
                    "model": commit.metadata.model or "",
                    "commit_type": commit.commit_type.value,
                    "relevance_source": "semantic",
                    "distance": hit.get("distance", 0.0),
                    "matching_messages": [],
                }

        # 2. Text search on commit messages
        text_hits = self.index.search_commits(query, limit=limit * 2)
        for commit in text_hits:
            ch = commit.commit_hash
            if ch in results:
                continue  # Already found via semantic
            results[ch] = {
                "commit_hash": ch,
                "short_hash": ch[:12],
                "message": commit.message,
                "timestamp": commit.metadata.timestamp,
                "provider": commit.metadata.provider or "",
                "model": commit.metadata.model or "",
                "commit_type": commit.commit_type.value,
                "relevance_source": "message",
                "distance": 0.5,  # Mid-range score for text matches
                "matching_messages": [],
            }

        # 3. Deep content search — scan blob content for query terms
        if deep:
            query_lower = query.lower()
            query_terms = query_lower.split()
            all_commits = self.index.list_all_commits(limit=500)
            for commit in all_commits:
                ch = commit.commit_hash
                if ch in results:
                    # Already have this commit, but enrich with content matches
                    pass
                # Try to get the blob and search through messages
                try:
                    blob = self.retrieve_blob(ch)
                    if blob is None:
                        continue
                    matching_msgs = []
                    for msg in blob.messages:
                        content_lower = msg.content.lower()
                        if any(term in content_lower for term in query_terms):
                            matching_msgs.append({
                                "role": msg.role,
                                "content": msg.content[:500],
                                "timestamp": msg.timestamp,
                            })
                    if matching_msgs:
                        if ch not in results:
                            results[ch] = {
                                "commit_hash": ch,
                                "short_hash": ch[:12],
                                "message": commit.message,
                                "timestamp": commit.metadata.timestamp,
                                "provider": commit.metadata.provider or "",
                                "model": commit.metadata.model or "",
                                "commit_type": commit.commit_type.value,
                                "relevance_source": "content",
                                "distance": 0.7,
                                "matching_messages": matching_msgs[:5],
                            }
                        else:
                            results[ch]["matching_messages"] = matching_msgs[:5]
                except Exception:
                    continue

        # Sort by distance (lower = more relevant), then by timestamp (newer first)
        sorted_results = sorted(
            results.values(),
            key=lambda r: (r["distance"], -r["timestamp"]),
        )
        return sorted_results[:limit]

    # -- Internal helpers --------------------------------------------------

    def _get_blob_key(self, commit_hash: str) -> str | None:
        row = self.index._conn.execute(
            "SELECT blob_key FROM commits WHERE commit_hash = ?", (commit_hash,)
        ).fetchone()
        if row is None:
            # prefix match
            row = self.index._conn.execute(
                "SELECT blob_key FROM commits WHERE commit_hash LIKE ? LIMIT 1",
                (f"{commit_hash}%",),
            ).fetchone()
        return row["blob_key"] if row else None

    def _find_nearest_anchor(self, commit_hash: str) -> CognitiveCommit | None:
        """Walk the parent chain to find the nearest non-delta commit."""
        h: str | None = commit_hash
        while h:
            c = self.index.get_commit(h)
            if c is None:
                return None
            if not c.is_delta:
                return c
            h = c.parent_hashes[0] if c.parent_hashes else None
        return None

    def _ensure_default_branch(self) -> None:
        if self.index.get_branch(self.config.default_branch) is None:
            # Create a genesis commit
            genesis = CognitiveCommit(
                commit_type=CommitType.ANCHOR,
                message="Genesis — CVC initialised",
                metadata=CommitMetadata(
                    agent_id=self.config.agent_id,
                    mode=self.config.mode,
                ),
            )
            genesis.compute_hash()
            blob_key = self.blobs.put(genesis.content_blob.canonical_bytes())
            self.index.insert_commit(genesis, blob_key)
            self.index.upsert_branch(
                BranchPointer(
                    name=self.config.default_branch,
                    head_hash=genesis.commit_hash,
                    description="Default branch",
                )
            )
            logger.info("Created default branch '%s' with genesis commit", self.config.default_branch)

    def close(self) -> None:
        self.index.close()
