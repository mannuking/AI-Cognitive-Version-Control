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
import sqlite3
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
