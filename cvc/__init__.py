"""
Cognitive Version Control (CVC) — Git for the AI Mind.

A state-based middleware system for managing AI agent context using
Merkle DAGs, delta compression, and provider-agnostic caching strategies.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tm-ai")
except PackageNotFoundError:
    __version__ = "0.0.0"  # fallback for editable/dev installs
