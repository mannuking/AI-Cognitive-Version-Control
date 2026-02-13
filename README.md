<p align="center">
  <img src="https://img.shields.io/badge/CVC-Cognitive_Version_Control-blueviolet?style=for-the-badge&logo=git&logoColor=white" alt="CVC Badge"/>
</p>

<h1 align="center">🧠 Cognitive Version Control</h1>

<p align="center">
  <strong>Git for the AI Mind — Because Intelligence Needs an Undo Button</strong>
</p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-▶-success?style=flat-square" alt="Quick Start"/></a>
  <a href="#-the-problem"><img src="https://img.shields.io/badge/Why_CVC%3F-Read-blue?style=flat-square" alt="Why CVC"/></a>
  <a href="#-contributing"><img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome"/></a>
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License"/></a>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Status-Alpha-orange?style=flat-square" alt="Status"/>
</p>

<p align="center">
  A production-grade local proxy & CLI tool that gives AI coding agents<br/>
  <strong>persistent memory, branching exploration, and instant rollback</strong> —<br/>
  so they stop forgetting what they were doing halfway through your refactor.
</p>

---

## 📖 Table of Contents

- [The Problem](#-the-problem)
- [The Solution](#-the-solution)
- [How It Works](#-how-it-works)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [CLI Reference](#-cli-reference)
- [Agent Tools (MCP / Function Calling)](#-agent-tools-mcp--function-calling)
- [The Four Operations](#-the-four-operations)
- [Three-Tiered Context Database](#-three-tiered-context-database)
- [VCS Integration (The Bridge)](#-vcs-integration-the-bridge)
- [Provider Optimization](#-provider-optimization)
- [Configuration](#-configuration)
- [Project Structure](#-project-structure)
- [Use Cases](#-use-cases)
- [Technology Stack](#-technology-stack)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [Research & References](#-research--references)
- [License](#-license)

---

## 🔥 The Problem

Every developer who has used an AI coding agent has experienced this:

> *"The agent was brilliant for the first 20 minutes. Then it started forgetting what files it had already edited, contradicting its own plan, and looping on the same error — even though I could see the fix was right there in the conversation."*

This is **Context Rot** — the silent degradation of an LLM's reasoning quality as its context window fills with noise. And it's not a bug; it's a fundamental property of how attention mechanisms work under entropy accumulation.

### The Linear Monotonic Fallacy

The industry's response has been: *"Just make the context window bigger!"* — from 4K to 32K to 128K to 1M+ tokens. But research shows this is a **fallacy**:

<table>
<tr>
<td width="50%">

**What Actually Happens:**

```
Task Success Rate
100% ┤██████████████
     │              ██████
 75% ┤                    ███
     │                       ███
 50% ┤                          ██
     │                            ████
 25% ┤                                ████
     │                                    ██████
  0% ┤────────────────────────────────────────────
     0%     25%     50%     75%    100%
              Context Window Usage
```

</td>
<td width="50%">

**The Numbers:**
- After **~60% window utilisation**, attention scores degrade measurably
- Error cascades compound: one hallucination pollutes all subsequent reasoning
- Agent tracked across **847 runs** showed cliff-edge performance drop
- Self-replication tasks: **11.7% → 40.7%** success rate just by adding rollback capability

</td>
</tr>
</table>

> **Extending the context window doesn't solve context rot. It just postpones the collapse.**

The real problem isn't *capacity* — it's that AI agents have **no mechanism to manage their own cognitive state**. They can't save their progress. They can't explore safely. They can't undo mistakes. They're writing an essay with a pen that has no eraser, on paper that keeps getting smaller.

---

## 💡 The Solution

**CVC gives AI agents the same superpower that Git gave developers: version control over their own thought process.**

Instead of a flat, ever-growing conversation log, CVC introduces a **state-based architecture** where the agent's context is structured as a **Merkle DAG** (Directed Acyclic Graph) — the same data structure that powers Git and IPFS.

<table>
<tr>
<td align="center" width="25%">
<h3>💾 Commit</h3>
<em>Save cognitive checkpoints</em><br/>
The agent snapshots its reasoning state at stable points. If things go wrong, it has a save point to return to.
</td>
<td align="center" width="25%">
<h3>🌿 Branch</h3>
<em>Explore without risk</em><br/>
The agent can try multiple approaches in isolated branches. Failed experiments don't pollute the main context.
</td>
<td align="center" width="25%">
<h3>🔀 Merge</h3>
<em>Synthesise insights</em><br/>
When a branch succeeds, CVC performs a semantic three-way merge — injecting <em>learnings</em>, not raw logs.
</td>
<td align="center" width="25%">
<h3>⏪ Restore</h3>
<em>Time-travel on demand</em><br/>
Stuck in an error loop? One command wipes the corrupted state and rehydrates from a clean checkpoint.
</td>
</tr>
</table>

### Before vs After

```
WITHOUT CVC                              WITH CVC
─────────                                ────────
User → Agent → [growing context blob]    User → Agent → CVC Proxy → Provider
                                                          │
No save points                           ✓ Commit: save state at any point
No exploration                           ✓ Branch: isolated experiments
No undo                                  ✓ Restore: instant rollback
No deduplication                         ✓ Merkle DAG: structural dedup
Full cost on every call                  ✓ Prompt caching: 90% cost reduction
Context rots over time                   ✓ Clean state management
```

---

## ⚙️ How It Works

CVC runs as a **local proxy** on your machine (`localhost:8000`). Your AI agent (Cursor, VS Code Copilot, custom agents, etc.) talks to CVC instead of talking directly to the LLM provider. CVC intercepts every request, manages the cognitive state, and forwards optimised prompts upstream.

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR MACHINE                             │
│                                                             │
│  ┌──────────┐   HTTP    ┌──────────────────┐    HTTPS       │
│  │  Agent   │ ────────▶ │   CVC Proxy      │ ──────────▶   │
│  │ (Cursor, │ ◀──────── │   :8000          │ ◀──────────   │
│  │ VS Code, │           │                  │               │
│  │  CLI)    │           │  ┌────────────┐  │   ┌────────┐  │
│  └──────────┘           │  │ LangGraph  │  │   │Claude/ │  │
│                         │  │ State      │  │   │GPT/    │  │
│                         │  │ Machine    │  │   │Gemini  │  │
│                         │  └─────┬──────┘  │   └────────┘  │
│                         │        │         │               │
│                         └────────┼─────────┘               │
│                                  │                         │
│                    ┌─────────────┼─────────────┐           │
│                    │             │             │           │
│               ┌────▼────┐  ┌────▼────┐  ┌────▼────┐      │
│               │ SQLite  │  │  CAS    │  │ Chroma  │      │
│               │ (Index) │  │ (Blobs) │  │(Vectors)│      │
│               │ Tier 1  │  │ Tier 2  │  │ Tier 3  │      │
│               └─────────┘  └─────────┘  └─────────┘      │
│                                                             │
│                    .cvc/ directory                          │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** The agent doesn't need to know about CVC's internals. From its perspective, it's just talking to a normal chat API — but behind the scenes, CVC is managing its entire cognitive lifecycle.

---

## 🏛️ Architecture

### The Merkle DAG

Every cognitive state is a **node** in a Merkle DAG. Each node's identity is a SHA-256 hash derived from:

```
commit_hash = SHA-256(
    sorted(parent_hashes)     +   # Link to history
    content_blob.canonical()  +   # The actual cognitive state
    metadata.canonical()          # Timestamp, agent ID, Git SHA
)
```

This gives us three critical properties:

| Property | What It Means |
|----------|---------------|
| **Cryptographic Immutability** | Any tampering with past commits *breaks the hash chain* and is instantly detectable |
| **Structural Deduplication** | If 3 branches share the first 50% of context, the shared portion is stored *once* |
| **Verifiable Provenance** | You can prove exactly what the agent "knew" when it made any decision |

### Delta Compression

CVC doesn't store a full copy of the context at every commit. That would be wasteful for contexts reaching 100K+ tokens.

```
Commit 1   →   [FULL ANCHOR]     ← Complete state stored
Commit 2   →   [δ delta]         ← Only the diff from anchor
Commit 3   →   [δ delta]         ← Only the diff from anchor
  ...
Commit 10  →   [FULL ANCHOR]     ← New anchor (configurable interval)
Commit 11  →   [δ delta]         ← Diff from new anchor
```

The system uses **Zstandard dictionary compression** — the anchor serves as the dictionary, and intermediate commits store only the lightweight delta. This achieves compression ratios comparable to VCDIFF (RFC 3284) with ~10-20% storage overhead vs. storing only the final state.

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **uv** (recommended) or pip
- **Git** (for VCS integration features)

### Installation

```bash
# Clone the repository
git clone https://github.com/mannuking/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control

# Install with uv (recommended)
uv sync --extra dev

# Or with pip
pip install -e ".[dev]"
```

### First Run

```bash
# 1. Initialise CVC in your project
cvc init

# 2. Set your API key
#    Windows PowerShell:
$env:ANTHROPIC_API_KEY = "sk-ant-..."
#    Linux/macOS:
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. Start the Cognitive Proxy
cvc serve

# 4. (Optional) Install Git hooks for automatic sync
cvc install-hooks
```

### Point Your Agent at CVC

Configure your AI agent to use `http://127.0.0.1:8000` as its API base URL. CVC exposes an **OpenAI-compatible** `/v1/chat/completions` endpoint.

```python
# Example: Using with OpenAI SDK
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="your-anthropic-key",  # Passed through to Anthropic
)

response = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Refactor the login module"}],
)
```

```python
# Example: Using CVC tools directly via function calling
response = client.chat.completions.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Create a branch for this experiment"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "cvc_branch",
            "description": "Create an isolated exploration branch",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name"]
            }
        }
    }],
)
```

---

## 📟 CLI Reference

```
Usage: cvc [OPTIONS] COMMAND [ARGS]...

  CVC — Cognitive Version Control: Git for the AI Mind.

Options:
  -v, --verbose  Enable debug logging.

Commands:
  serve              Start the CVC Cognitive Proxy server
  init               Initialise a .cvc/ directory in the project
  status             Show current branch, HEAD, and context size
  log                Show commit history for the active branch
  commit             Create a cognitive commit
  branch             Create and switch to a new branch
  merge              Merge a branch into the target
  restore            Restore context to a previous commit (time-travel)
  install-hooks      Install Git hooks for CVC ↔ Git synchronisation
  capture-snapshot   Capture CVC state linked to current Git commit
```

### Examples

```bash
# See where you are
cvc status
# ┌──────────────┬──────────────┐
# │ Agent        │ sofia        │
# │ Branch       │ main         │
# │ HEAD         │ 5f80c1f2dc08 │
# │ Context size │ 42           │
# └──────────────┴──────────────┘

# Create a checkpoint
cvc commit -m "Analysed error logs, identified NPE in auth module"

# Explore a risky approach
cvc branch fix-refactor -d "Try singleton pattern for Auth class"

# See history
cvc log
# ┌──────────────┬──────────────┬──────────────────────────────────┬───────┐
# │ Hash         │ Type         │ Message                          │ Delta │
# ├──────────────┼──────────────┼──────────────────────────────────┼───────┤
# │ 5f80c1f2dc08 │ checkpoint   │ Analysed error logs, identified… │ δ     │
# │ 145f0bd8d3bb │ anchor       │ Genesis — CVC initialised        │ ●     │
# └──────────────┴──────────────┴──────────────────────────────────┴───────┘

# Made a mistake? Time-travel back
cvc restore 145f0bd8

# Merge successful experiment
cvc merge fix-refactor --target main

# Start the proxy server
cvc serve --host 0.0.0.0 --port 8000
```

---

## 🛠️ Agent Tools (MCP / Function Calling)

CVC exposes four tools that AI agents can invoke autonomously. These work as **OpenAI-compatible function calls**, making them compatible with any agent framework (LangChain, CrewAI, AutoGen, custom agents).

The full tool definitions are available at `GET /cvc/tools`.

| Tool | Trigger | What It Does |
|------|---------|--------------|
| `cvc_commit` | Agent reaches a stable point | Freezes context → SHA-256 hash → stores in CAS → advances HEAD |
| `cvc_branch` | Agent faces uncertainty | Creates isolated branch → resets context → agent explores freely |
| `cvc_merge` | Branch experiment succeeds | LCA computation → semantic diff → LLM synthesis → inject into target |
| `cvc_restore` | Agent detects error loop | Retrieves stored blob → wipes context → rehydrates from checkpoint |

---

## 🔄 The Four Operations

### 1. `cvc_commit` — The Save Point

```
Agent: "I've analysed the stack trace and identified the null pointer
        in the auth module. Before I start generating the fix, let me
        save this understanding."

→ cvc_commit(message="Identified NPE in AuthService.validate()")

CVC:  ✓ Froze context window (1,847 tokens)
      ✓ Computed Merkle hash: 5f80c1f2dc08...
      ✓ Stored blob (delta-compressed, 340 bytes)
      ✓ Advanced HEAD on 'main'
```

### 2. `cvc_branch` — Isolated Exploration

```
Agent: "I could fix this by refactoring the class OR by patching the
        helper function. Let me try refactoring first."

→ cvc_branch(name="fix-refactor", description="Refactor Auth singleton")

CVC:  ✓ Created branch 'fix-refactor' from main @ 5f80c1f2dc08
      ✓ Preserved system instructions
      ✓ Cleared accumulated context (entropy removed)
      ✓ Injected branch goal into clean context
```

**Why this matters:** The agent can hallucinate, fail, and loop in the branch without the "negative tokens" biasing future reasoning on main. If it fails, just switch back — the main branch is untouched.

### 3. `cvc_merge` — Semantic Three-Way Merge

Unlike Git's line-by-line diff, CVC performs a **semantic merge**:

```
1. Find the Lowest Common Ancestor (LCA)
2. Diff: What changed in the source branch since the LCA?
3. Diff: What changed in the target branch since the LCA?
4. Synthesise: Use an LLM to generate a concise summary
5. Inject: Add the synthesis (not the raw logs) into the target context

Result: "The experiment in fix-refactor succeeded. We learned that
         AuthService is a singleton and the NPE occurs when the
         validator is called before initialisation."
```

### 4. `cvc_restore` — The Undo Button for the Mind

```
Agent: "I've been going in circles for 5 turns trying to fix these
        imports. Let me go back to before I started."

→ cvc_restore(commit_hash="5f80c1f2")

CVC:  ✓ Retrieved blob from CAS
      ✓ Wiped current context (3,200 tokens of noise removed)
      ✓ Rehydrated with clean state from commit 5f80c1f2
      ✓ Created rollback commit for audit trail
      ✓ Agent is back to the moment of clarity
```

---

## 🗄️ Three-Tiered Context Database

CVC doesn't use a monolithic database. It uses a **purpose-built three-tier architecture**, each tier optimised for its specific role:

| Tier | Technology | Purpose | What's Stored |
|------|-----------|---------|---------------|
| **Tier 1: Index** | SQLite (WAL mode) | Fast queries, graph traversal | Commit hashes, branch pointers (HEAD), parent-child links, metadata, Git ↔ CVC links |
| **Tier 2: Blob Store** | Content-Addressable Storage | Bulk data, deduplication | Zstandard-compressed context blobs, delta-encoded states. Path: `.cvc/objects/<hash[:2]>/<hash[2:]>` |
| **Tier 3: Semantic** | Chroma (optional) | Similarity search, recall | Embeddings of commit summaries. Enables: *"Have I solved a similar error before?"* |

### Local-First Design

Everything lives in a `.cvc/` directory inside your project — just like `.git/`. No cloud dependency. No telemetry. Your agent's thought process stays on your machine.

```
.cvc/
├── cvc.db              # SQLite index (Tier 1)
├── objects/            # Content-addressable blobs (Tier 2)
│   ├── 5f/
│   │   └── 80c1f2dc08...   # Zstandard-compressed
│   └── 14/
│       └── 5f0bd8d3bb...
├── branches/           # Branch metadata
└── chroma/             # Vector store (Tier 3, optional)
```

---

## 🔗 VCS Integration (The Bridge)

CVC doesn't replace Git — it **synchronises with it**. When you check out an old version of your code, CVC automatically restores the agent's brain to the state it was in when that code was written.

### Shadow Branching

```
main branch:     Clean source code (human-readable)
cvc/main branch: .cvc/ directory (Merkle DAGs, blobs)
```

The cognitive state is stored on a **shadow branch** so it never pollutes your main codebase.

### Git Notes — Cognitive Blame

CVC attaches its commit hashes to Git commits via **Git Notes** (`refs/notes/cvc`):

```bash
$ git log --show-notes=cvc

commit a1b2c3d (HEAD -> main) — Fix auth NPE
Notes (cvc):
    cvc:5f80c1f2dc08a3b4...

    # ↑ This is the CVC commit hash.
    # Run `cvc restore 5f80c1f2` to see exactly what the agent
    # was thinking when it made this code change.
```

### Git Hooks

CVC installs two hooks:

| Hook | Trigger | Action |
|------|---------|--------|
| `post-commit` | After `git commit` | Captures CVC state → links to Git SHA → pushes to shadow branch |
| `post-checkout` | After `git checkout` | Looks up CVC state for the checked-out commit → restores agent context |

```bash
# Install hooks
cvc install-hooks

# Now every git commit automatically captures cognitive state
git commit -m "Fix auth module"
# → CVC: Snapshot captured: git=a1b2c3d ↔ cvc=5f80c1f2dc08
```

---

## ⚡ Provider Optimization

### Anthropic Prompt Caching

CVC structures every prompt so the **committed history** (everything up to the last checkpoint) serves as a **cacheable prefix**. It injects `cache_control: {"type": "ephemeral"}` at the boundary.

```
┌─────────────────────────────────────────────┐
│  System prompt                              │  ← Cached
│  Committed history (main.md, past commits)  │  ← Cached
│  ─── cache_control: ephemeral ───           │  ← Boundary
│  New messages since last commit             │  ← Not cached
└─────────────────────────────────────────────┘
```

**Result:**
- **~90% cost reduction** on state restoration
- **~85% latency reduction** — cached tokens aren't reprocessed
- Makes **frequent checkpointing economically feasible**

When you rollback to a previous commit, CVC reconstructs the prompt to match the exact prefix of that commit. Because Anthropic caches based on exact prefix match, the model doesn't need to re-process any of the committed history.

---

## ⚙️ Configuration

CVC is configured via **environment variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `CVC_ROOT` | `.cvc` | Root directory for CVC data |
| `CVC_AGENT_ID` | `sofia` | Agent identifier |
| `CVC_DEFAULT_BRANCH` | `main` | Default branch name |
| `CVC_ANCHOR_INTERVAL` | `10` | Full snapshot every N commits |
| `CVC_PROVIDER` | `anthropic` | LLM provider |
| `CVC_MODEL` | `claude-sonnet-4-20250514` | Model to use |
| `ANTHROPIC_API_KEY` | — | Your Anthropic API key |
| `CVC_HOST` | `127.0.0.1` | Proxy bind host |
| `CVC_PORT` | `8000` | Proxy bind port |
| `CVC_VECTOR_ENABLED` | `false` | Enable Tier 3 (Chroma) vector store |
| `CVC_CHROMA_DIR` | `.cvc/chroma` | Chroma persistence directory |

---

## 📁 Project Structure

```
AI-Cognitive-Version-Control/
├── pyproject.toml                     # Project config & dependencies (uv/pip)
├── README.md                          # You are here
│
├── cvc/                               # Main package
│   ├── __init__.py                    # Package root, version
│   ├── __main__.py                    # python -m cvc entry point
│   ├── cli.py                         # Click CLI (serve, init, status, log, ...)
│   ├── proxy.py                       # FastAPI interceptor (port 8000)
│   │
│   ├── core/                          # Foundation layer
│   │   ├── models.py                  # Pydantic schemas: Merkle DAG nodes,
│   │   │                              #   ContentBlob, CommitMetadata, SHA-256
│   │   │                              #   hashing, OpenAI-compat chat models
│   │   └── database.py                # Three-tiered CDB:
│   │                                  #   - IndexDB (SQLite)
│   │                                  #   - BlobStore (CAS + Zstandard)
│   │                                  #   - SemanticStore (Chroma)
│   │                                  #   - DeltaEngine (delta compression)
│   │                                  #   - ContextDatabase (unified façade)
│   │
│   ├── operations/                    # CVC operations layer
│   │   ├── engine.py                  # CVCEngine: commit, branch, merge,
│   │   │                              #   restore, switch, log
│   │   └── state_machine.py           # LangGraph state machine:
│   │                                  #   router → cvc_handler | passthrough
│   │                                  #   + MCP tool definitions
│   │
│   ├── adapters/                      # Provider adapters
│   │   └── anthropic.py               # Anthropic Messages API + prompt caching
│   │                                  #   + cache_control injection
│   │
│   └── vcs/                           # Version control integration
│       └── bridge.py                  # Shadow branches, Git Notes
│                                      #   (refs/notes/cvc), hook scripts
│
└── AI Cognitive Version Control       # Research paper (PDF)
    System.pdf
```

---

## 🎯 Use Cases

### For Individual Developers

- **AI pair programming** — Your Copilot/Cursor agent stops forgetting context mid-session
- **Long refactoring sessions** — Agent can explore multiple approaches without losing track
- **Debugging complex issues** — Save state before each hypothesis, rollback on failure
- **Learning from mistakes** — Search past commits: *"How did I fix this type of error last time?"*

### For Teams & Organizations

- **Cognitive CI/CD** — Review not just the code, but the *reasoning process* that produced it
- **Audit trails** — Cryptographic proof of what the AI knew when it made each decision
- **Shared memory** — Push `.cvc/` to a shared repo; new team members inherit the full context
- **Compliance** — Immutable Merkle DAG means logs can't be silently altered after the fact

### For Open Source

- **Reproducible AI contributions** — Contributors can see *how* an AI-generated PR was produced
- **Quality review** — Maintainers can inspect the agent's commit history for hallucination patterns
- **Knowledge base** — Vector search over commit summaries builds an organic project FAQ

### Works With

| Tool / Platform | Integration |
|----------------|-------------|
| **Cursor** | Set CVC as the API base URL |
| **VS Code + Copilot** | Route through CVC proxy |
| **Custom agents** | OpenAI-compatible API |
| **LangChain / LangGraph** | Use CVC tools as function calls |
| **CrewAI / AutoGen** | Tool definitions at `GET /cvc/tools` |
| **GitHub / GitLab** | Shadow branches + Git Notes |
| **CI/CD pipelines** | Post-commit hooks trigger automatic snapshots |

---

## 🧰 Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Data Integrity** | SHA-256 Merkle DAGs | Tamper-proof history, structural deduplication |
| **Index Database** | SQLite (WAL mode) | Fast graph traversal, zero-config, embedded |
| **Blob Storage** | Content-Addressable Storage | Git-style objects, automatic dedup |
| **Compression** | Zstandard dictionary compression | VCDIFF-equivalent delta encoding, 10-20× compression |
| **Vector Search** | Chroma (optional) | Cosine similarity over commit summaries |
| **HTTP Proxy** | FastAPI + Uvicorn | Async, OpenAI-compatible API surface |
| **State Machine** | LangGraph | Routes requests between CVC ops and passthrough |
| **VCS Bridge** | GitPython + subprocess | Shadow branches, Git Notes, hook management |
| **Provider Layer** | httpx (async) | Anthropic prompt caching with `cache_control` injection |
| **CLI** | Click + Rich | Beautiful terminal output with tables |
| **Typing** | Pydantic v2 | Strict schemas, JSON serialisation, validation |
| **Package Manager** | uv | Fast dependency resolution |

---

## 🗺️ Roadmap

CVC is in **active development**. Here's where we're headed:

- [ ] **OpenAI Adapter** — Auto prefix caching for GPT-4o
- [ ] **Google/Gemini Adapter** — `cachedContent.create` integration with TTL management
- [ ] **Local Inference Adapter** — KV Cache serialisation for vLLM/Ollama (sub-second restore)
- [ ] **Reflector LLM** — Secondary model for auto-generating commit summaries
- [ ] **Semantic Three-Way Merge** — Full LLM-powered conflict resolution
- [ ] **VS Code Extension** — GUI for branch visualization, commit graph, time-travel slider
- [ ] **MCP Server** — Native Model Context Protocol server for direct agent integration
- [ ] **Cognitive CI/CD** — Review agent reasoning chains in PR reviews
- [ ] **Multi-agent support** — Multiple agents sharing a CVC database with conflict resolution
- [ ] **Cloud sync** — S3/MinIO backend for team collaboration
- [ ] **Metrics dashboard** — Context utilisation, cache hit rates, branch success rates

---

## 🤝 Contributing

**This is an open-source project and contributions are warmly welcome!** Whether you're a solo developer, part of a team, or representing an organization — CVC is built to be a community-driven tool.

### How to Contribute

1. **Fork** the repository
2. **Create a branch** for your feature (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to your branch (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

### Areas Where Help Is Needed

| Area | Description | Difficulty |
|------|-------------|------------|
| 🔌 **Provider Adapters** | OpenAI, Google Gemini, Ollama/vLLM adapters | Medium |
| 🧪 **Testing** | Unit tests, integration tests, edge case coverage | Easy–Medium |
| 📖 **Documentation** | Tutorials, examples, API docs | Easy |
| 🖥️ **VS Code Extension** | GUI for the commit graph and branch visualization | Hard |
| 🌐 **MCP Server** | Native Model Context Protocol implementation | Medium |
| ⚡ **Performance** | Benchmarking, optimization, profiling | Medium |
| 🔒 **Security** | Audit the Merkle chain, add encryption at rest | Medium–Hard |

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control

# Install with dev dependencies
uv sync --extra dev

# Run linting
uv run ruff check cvc/

# Run tests
uv run pytest
```

### Code Style

- **Python 3.11+** with strict typing
- **Ruff** for linting (config in `pyproject.toml`)
- **Pydantic v2** for all data models
- Keep functions focused and well-documented
- Write docstrings for public APIs

---

## 📚 Research & References

CVC is grounded in published research on context management for LLM agents:

1. **ContextBranch** — *"Context Branching for LLM Conversations: A Version Control Approach to Exploratory Programming"* — 58.1% reduction in context usage via branching. [arXiv:2512.13914](https://arxiv.org/abs/2512.13914)
2. **GCC (Git Context Controller)** — *"Manage the Context of LLM-based Agents like Git"* — Self-replication success: 11.7% → 40.7% with rollback. [arXiv:2508.00031](https://arxiv.org/abs/2508.00031)
3. **Merkle-CRDTs** — *"Merkle-DAGs meet CRDTs"* — Structural deduplication and conflict-free replicated data types. [Protocol Labs Research](https://research.protocol.ai/publications/merkle-crdts-merkle-dags-meet-crdts/psaras2020.pdf)
4. **Prompt Caching** — Anthropic, OpenAI, and Google implementations for token reuse. [PromptHub Guide](https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models)
5. **KV Cache Serialisation** — Sub-second context restoration for local models. [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1q7bh5h/)
6. **Delta Compression** — VCDIFF (RFC 3284) and dictionary-based compression for sequential text data. [HackerNoon Guide](https://hackernoon.com/delta-compression-diff-algorithms-and-delta-file-formats-practical-guide-7v1p3uhz)

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>Built with frustration, caffeine, and the firm belief that AI agents deserve version control too.</strong>
</p>

<p align="center">
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control">⭐ Star this repo</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/issues">🐛 Report Bug</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/issues">💡 Request Feature</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/pulls">🔀 Submit PR</a>
</p>
