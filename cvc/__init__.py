"""
Cognitive Version Control (CVC) — Git for the AI Mind.

A state-based middleware system for managing AI agent context using
Merkle DAGs, delta compression, and provider-agnostic caching strategies.
"""

from pathlib import Path
import tomllib
from importlib.metadata import version, PackageNotFoundError

def _resolve_version() -> str:
    """Resolve CVC version.

    Priority:
    1) Local source checkout version from pyproject.toml (if present)
    2) Installed package metadata (tm-ai)
    3) Safe fallback
    """
    try:
        root = Path(__file__).resolve().parent.parent
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            proj = data.get("project", {})
            ver = proj.get("version")
            if isinstance(ver, str) and ver.strip():
                return ver.strip()
    except Exception:
        pass

    try:
        return version("tm-ai")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _resolve_version()
