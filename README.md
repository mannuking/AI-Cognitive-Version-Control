# CVC — Cognitive Version Control

**Git for the AI Mind.** A state-based middleware system for managing AI agent context using Merkle DAGs, delta compression, and provider-agnostic caching strategies.

## The Problem

The **Linear Monotonic Fallacy** assumes that extending an LLM's context window solves context degradation. It doesn't — it merely postpones the inevitable collapse of reasoning under accumulated entropy. After ~60% context utilisation, task success rates drop precipitously.

## The Solution

CVC transitions agents from a **stream-based** to a **state-based** architecture by providing:

- **Cognitive Commits** — SHA-256 Merkle DAG nodes that snapshot the agent's full reasoning state
- **Branching** — Isolated exploration without polluting the main context with negative tokens
- **Semantic Merge** — LLM-synthesised three-way merges that inject *insights*, not raw logs
- **Time Travel** — Instant rollback to any previous cognitive state, breaking error cascades

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Agent/IDE   │────▶│  CVC Proxy :8000 │────▶│  Claude API  │
│ (Cursor/VS)  │◀────│   (FastAPI)      │◀────│  (Anthropic) │
└──────────────┘     └────────┬─────────┘     └──────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  LangGraph State   │
                    │     Machine        │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼───┐  ┌───────▼──────┐  ┌─────▼──────┐
     │ Tier 1     │  │ Tier 2       │  │ Tier 3     │
     │ SQLite     │  │ CAS Blobs    │  │ Chroma     │
     │ (Index)    │  │ (.cvc/obj)   │  │ (Vectors)  │
     └────────────┘  └──────────────┘  └────────────┘
```

## Quick Start

```bash
# Install
pip install -e ".[all]"

# Initialise CVC in your project
cvc init

# Start the Cognitive Proxy
export ANTHROPIC_API_KEY="sk-ant-..."
cvc serve

# Install Git hooks for automatic synchronisation
cvc install-hooks
```

## CVC Tools (Agent-Callable)

| Tool | Description |
|------|-------------|
| `cvc_commit` | Freeze context → Merkle hash → store in CAS |
| `cvc_branch` | Create isolated exploration branch, reset context |
| `cvc_merge` | Semantic three-way merge with LLM synthesis |
| `cvc_restore` | Time-travel: wipe context and rehydrate from stored state |

## CLI Commands

```bash
cvc status          # Show branch, HEAD, context size
cvc log             # Commit history with delta indicators
cvc commit -m "…"   # Manual cognitive checkpoint
cvc branch <name>   # Create exploration branch
cvc merge <branch>  # Semantic merge into active branch
cvc restore <hash>  # Rollback to previous state
```

## Technology Stack

- **Database:** SQLite (Index) + Disk CAS (Blobs) + Chroma (Vectors)
- **Integrity:** SHA-256 Merkle DAGs
- **Compression:** Zstandard dictionary compression (VCDIFF-equivalent)
- **Proxy:** FastAPI + Uvicorn
- **State Machine:** LangGraph
- **VCS Integration:** Git Hooks + Shadow Branches + Git Notes
- **Provider:** Anthropic Prompt Caching (`cache_control: ephemeral`)
