"""
cvc.core.models — Pydantic schemas for the Cognitive Version Control Merkle DAG.

Every cognitive commit is a node in a content-addressed Merkle DAG.  The SHA-256
hash of each node is derived from:
    hash = SHA-256( parent_hash || serialized_content_blob || metadata_json )

This guarantees cryptographic immutability: altering any ancestor invalidates
every descendant hash, making tampering immediately detectable.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Cross-platform directory helpers
# ---------------------------------------------------------------------------

def get_global_config_dir() -> Path:
    """
    Return the user-level config directory for CVC, created if needed.

    - Windows:  %LOCALAPPDATA%\\cvc  (e.g. C:\\Users\\X\\AppData\\Local\\cvc)
    - macOS:    ~/Library/Application Support/cvc
    - Linux:    $XDG_CONFIG_HOME/cvc  (default ~/.config/cvc)
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "cvc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def discover_cvc_root(start: Path | None = None) -> Path | None:
    """
    Walk up from *start* (default: CWD) looking for a ``.cvc/`` directory,
    similar to how Git walks up to find ``.git/``.

    Returns the **project root** (parent of ``.cvc/``), or ``None``.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / ".cvc"
        if candidate.is_dir():
            return current
        parent = current.parent
        if parent == current:
            break  # Reached filesystem root
        current = parent
    return None


class GlobalConfig(BaseModel):
    """
    User-level defaults stored in the global config directory.
    Saved as ``config.json`` so new projects inherit the user's preferred
    provider, model, and agent identity.

    API keys are stored per-provider so the user only needs to enter them
    once via ``cvc setup``.  Environment variables always take precedence.
    """
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    agent_id: str = "sofia"
    api_keys: dict[str, str] = {}

    @classmethod
    def load(cls) -> "GlobalConfig":
        """Load from disk, returning defaults if the file doesn't exist."""
        path = get_global_config_dir() / "config.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception:
                return cls()
        return cls()

    def save(self) -> Path:
        """Persist to disk. Returns the file path."""
        path = get_global_config_dir() / "config.json"
        path.write_text(
            json.dumps(self.model_dump(), indent=2),
            encoding="utf-8",
        )
        return path


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class CommitType(StrEnum):
    """Classification of cognitive commits."""
    CHECKPOINT = "checkpoint"       # Manual or auto save-point
    ANALYSIS = "analysis"           # Agent completed an analysis phase
    GENERATION = "generation"       # Agent produced code / output
    ROLLBACK = "rollback"           # Commit created on rollback restoration
    MERGE = "merge"                 # Result of a semantic merge
    ANCHOR = "anchor"               # Full anchor state (no delta)


class BranchStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Content Blob — the raw cognitive payload
# ---------------------------------------------------------------------------

class ContextMessage(BaseModel):
    """A single message in the agent's context window."""
    role: str                       # system | user | assistant | tool
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    timestamp: float = Field(default_factory=time.time)


class ContentBlob(BaseModel):
    """
    The serialized cognitive state at the moment of a commit.

    Contains the full conversation context, any tool outputs,
    and the agent's internal reasoning trace.
    """
    messages: list[ContextMessage] = Field(default_factory=list)
    reasoning_trace: str = ""
    tool_outputs: dict[str, Any] = Field(default_factory=dict)
    source_files: dict[str, str] = Field(default_factory=dict)   # path → hash
    token_count: int = 0

    def canonical_bytes(self) -> bytes:
        """Deterministic serialisation for hashing (sorted keys, no whitespace)."""
        return json.dumps(
            self.model_dump(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")


# ---------------------------------------------------------------------------
# Commit Metadata
# ---------------------------------------------------------------------------

class CommitMetadata(BaseModel):
    """Immutable metadata attached to every cognitive commit."""
    timestamp: float = Field(default_factory=time.time)
    agent_id: str = "sofia"
    mode: str | None = None                 # Which service created this: "mcp", "proxy", or "cli"
    git_commit_sha: str | None = None      # The linked codebase commit
    provider: str | None = None             # e.g. "anthropic", "openai"
    model: str | None = None                # e.g. "claude-sonnet-4-20250514"
    cache_id: str | None = None             # Provider-side cache handle
    tags: list[str] = Field(default_factory=list)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")


# ---------------------------------------------------------------------------
# The Cognitive Commit — a Merkle DAG Node
# ---------------------------------------------------------------------------

class CognitiveCommit(BaseModel):
    """
    A single node in the Merkle DAG.

    The ``commit_hash`` is computed as:
        SHA-256( parent_hash || content_blob.canonical_bytes() || metadata.canonical_bytes() )

    For merge commits, ``parent_hashes`` contains ≥ 2 parents.
    """
    commit_hash: str = ""                   # Populated by compute_hash()
    parent_hashes: list[str] = Field(default_factory=list)
    commit_type: CommitType = CommitType.CHECKPOINT
    message: str = ""
    content_blob: ContentBlob = Field(default_factory=ContentBlob)
    metadata: CommitMetadata = Field(default_factory=CommitMetadata)

    # Delta compression fields
    is_delta: bool = False
    anchor_hash: str | None = None          # The full anchor this delta is relative to
    delta_bytes: bytes | None = None        # VCDIFF-encoded delta (stored in CAS, not in index)

    def compute_hash(self) -> str:
        """Derive the SHA-256 Merkle hash from content + parents + metadata."""
        h = hashlib.sha256()
        for ph in sorted(self.parent_hashes):
            h.update(ph.encode("utf-8"))
        h.update(self.content_blob.canonical_bytes())
        h.update(self.metadata.canonical_bytes())
        self.commit_hash = h.hexdigest()
        return self.commit_hash

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_hash(self) -> str:
        return self.commit_hash[:12] if self.commit_hash else ""


# ---------------------------------------------------------------------------
# Branch Pointer
# ---------------------------------------------------------------------------

class BranchPointer(BaseModel):
    """A named pointer to the tip of a commit chain (analogous to a Git ref)."""
    name: str
    head_hash: str                          # Points to the latest CognitiveCommit
    status: BranchStatus = BranchStatus.ACTIVE
    created_at: float = Field(default_factory=time.time)
    description: str = ""
    parent_branch: str | None = None        # For tracking branch lineage


# ---------------------------------------------------------------------------
# Request / Response models for the Cognitive Proxy API
# ---------------------------------------------------------------------------

class CVCCommitRequest(BaseModel):
    """Payload for the cvc_commit tool."""
    message: str = ""
    commit_type: CommitType = CommitType.CHECKPOINT
    tags: list[str] = Field(default_factory=list)


class CVCBranchRequest(BaseModel):
    """Payload for the cvc_branch tool."""
    name: str
    source_commit: str | None = None        # Defaults to current HEAD
    description: str = ""


class CVCMergeRequest(BaseModel):
    """Payload for the cvc_merge tool."""
    source_branch: str
    target_branch: str = "main"


class CVCRestoreRequest(BaseModel):
    """Payload for the cvc_restore (time-travel) tool."""
    commit_hash: str                        # Full or short hash


class CVCOperationResponse(BaseModel):
    """Unified response envelope for all CVC operations."""
    success: bool
    operation: str
    commit_hash: str | None = None
    branch: str | None = None
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Proxy pass-through models (OpenAI-compatible chat schema)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    """Subset of the OpenAI chat-completion request used by the proxy."""
    model: str = "claude-opus-4-6"
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    # CVC extension fields (ignored by upstream providers)
    cvc_branch: str | None = None
    cvc_auto_commit: bool = True


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[ChatCompletionChoice] = Field(default_factory=list)
    usage: UsageInfo = Field(default_factory=UsageInfo)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class CVCConfig(BaseModel):
    """Runtime configuration for the CVC system."""
    cvc_root: Path = Path(".cvc")
    db_path: Path = Path(".cvc/cvc.db")
    objects_dir: Path = Path(".cvc/objects")
    branches_dir: Path = Path(".cvc/branches")
    default_branch: str = "main"
    anchor_interval: int = 10               # Full snapshot every N commits
    agent_id: str = "sofia"
    mode: str = "cli"                       # Which service is running: "mcp", "proxy", or "cli"

    # Provider — supports: anthropic, openai, google, ollama
    provider: str = "anthropic"
    upstream_base_url: str = "https://api.anthropic.com"
    model: str = "claude-opus-4-6"
    api_key: str = ""

    # Proxy
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8000

    # Vector store
    vector_enabled: bool = True
    chroma_persist_dir: Path = Path(".cvc/chroma")

    def ensure_dirs(self) -> None:
        """Create all required directories (including vector store)."""
        for d in (self.cvc_root, self.objects_dir, self.branches_dir, self.chroma_persist_dir):
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_vector_enabled() -> bool:
        """Resolve vector store setting: env var override > default True."""
        env_val = os.getenv("CVC_VECTOR_ENABLED")
        if env_val is not None:
            return env_val.lower() == "true"
        return True  # ChromaDB is a core dependency

    @classmethod
    def for_project(cls, project_root: Path | None = None, **overrides: Any) -> "CVCConfig":
        """
        Build a config anchored to a specific project directory.

        Resolution order (highest priority first):
          1. Explicit ``overrides`` keyword arguments
          2. Environment variables (CVC_PROVIDER, CVC_MODEL, …)
          3. Global config (~/.config/cvc/config.json)
          4. Built-in defaults

        If *project_root* is ``None``, :func:`discover_cvc_root` is used to
        walk up from CWD.  If still not found, CWD is used.
        """
        # Discover project root
        if project_root is None:
            project_root = discover_cvc_root()
        if project_root is None:
            project_root = Path.cwd()

        root = project_root / ".cvc"

        # Global config as base defaults
        gc = GlobalConfig.load()

        # Provider resolution
        from cvc.adapters import PROVIDER_DEFAULTS  # Lazy to avoid circular import

        provider = overrides.pop("provider", None) or os.getenv("CVC_PROVIDER", gc.provider)
        defaults = PROVIDER_DEFAULTS.get(provider, {})

        # API key — resolution: env var → global config → empty
        api_key_env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": "",
        }
        api_key_env = api_key_env_map.get(provider, "")
        api_key = os.getenv(api_key_env, "") if api_key_env else ""
        if not api_key:
            api_key = gc.api_keys.get(provider, "")

        # Upstream URL
        upstream_url_map = {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com",
            "google": "https://generativelanguage.googleapis.com",
            "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        }

        return cls(
            cvc_root=root,
            db_path=root / "cvc.db",
            objects_dir=root / "objects",
            branches_dir=root / "branches",
            default_branch=os.getenv("CVC_DEFAULT_BRANCH", "main"),
            anchor_interval=int(os.getenv("CVC_ANCHOR_INTERVAL", "10")),
            agent_id=overrides.pop("agent_id", None) or os.getenv("CVC_AGENT_ID", gc.agent_id),
            provider=provider,
            upstream_base_url=os.getenv(
                "CVC_UPSTREAM_URL",
                upstream_url_map.get(provider, "https://api.anthropic.com"),
            ),
            model=overrides.pop("model", None) or os.getenv(
                "CVC_MODEL",
                defaults.get("model", gc.model),
            ),
            api_key=api_key,
            proxy_host=os.getenv("CVC_HOST", "127.0.0.1"),
            proxy_port=int(os.getenv("CVC_PORT", "8000")),
            vector_enabled=cls._resolve_vector_enabled(),
            chroma_persist_dir=root / "chroma",
            **overrides,
        )
