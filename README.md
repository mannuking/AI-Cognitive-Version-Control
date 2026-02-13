<p align="center">
  <img src="https://img.shields.io/badge/⏳_Time_Machine-for_AI_Agents-blueviolet?style=for-the-badge&logoColor=white" alt="Time Machine Badge"/>
</p>

<h1 align="center">⏳ Time Machine for AI Agents</h1>

<h3 align="center"><em>Cognitive Version Control (CVC)</em></h3>

<p align="center">
  <strong>Save. Branch. Rewind. Merge. — Your AI agent just got an undo button.</strong>
</p>

<br/>

<p align="center">
  <a href="#-get-started"><img src="https://img.shields.io/badge/Get_Started-▶-success?style=flat-square" alt="Get Started"/></a>
  <a href="#-contributing"><img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome"/></a>
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License"/></a>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Status-Alpha-orange?style=flat-square" alt="Status"/>
</p>

---

<br/>

<p align="center">
  <strong>Your AI coding agent is brilliant — for about 20 minutes.</strong><br/><br/>
  Then it forgets what it already fixed, contradicts its own plan,<br/>
  and loops on the same error for eternity.<br/><br/>
  <em>Sound familiar?</em>
</p>

<br/>

---

## 🧠 What Is This?

**Time Machine for AI Agents** is a local system that gives AI coding agents something they've never had: **memory management.**

Think of it as **Git, but for the AI's brain.** Instead of versioning source code, CVC versions the agent's *entire context* — every thought, every decision, every conversation turn — as an immutable, cryptographic Merkle DAG.

The agent can **save** its reasoning at any moment, **branch** into risky experiments without fear, **rewind** when it gets stuck, and **merge** only the insights that matter — not the noise.

<br/>

<table>
<tr>
<td align="center" width="25%">
<h3>💾 Save</h3>
Checkpoint the agent's brain at any stable moment. A cognitive save point it can always return to.
</td>
<td align="center" width="25%">
<h3>🌿 Branch</h3>
Let the agent explore risky ideas in isolation. If it fails? Main context stays clean.
</td>
<td align="center" width="25%">
<h3>🔀 Merge</h3>
When a branch works, merge the <em>learnings</em> back — not the raw logs. Semantic, not syntactic.
</td>
<td align="center" width="25%">
<h3>⏪ Rewind</h3>
Stuck in a loop? Time-travel back to a clean checkpoint. Instantly. No questions asked.
</td>
</tr>
</table>

<br/>

---

## 🔥 The Problem We're Solving

The industry keeps making context windows bigger — 4K → 32K → 128K → 1M+ tokens — and calling it progress. **It's not.**

Research shows that after **~60% context utilisation**, LLM reasoning quality **falls off a cliff**. One hallucination poisons everything that follows. Error cascades compound. The agent starts fighting itself.

> **A bigger window doesn't fix context rot. It just gives it more room to spread.**

The real issue? AI agents have **zero ability to manage their own cognitive state**. They can't save their work. They can't explore safely. They can't undo mistakes. They're solving a 500-piece puzzle while someone keeps removing pieces from the table.

### What the research says:

- **58.1%** context reduction when agents can branch ([ContextBranch, arXiv:2512.13914](https://arxiv.org/abs/2512.13914))
- **11.7% → 40.7%** success rate improvement just by adding rollback ([GCC, arXiv:2508.00031](https://arxiv.org/abs/2508.00031))
- **~90%** cost reduction through intelligent prompt caching
- **~85%** latency reduction — cached tokens skip reprocessing entirely

<br/>

---

## ⚙️ How It Works

CVC runs as a **local proxy** between your agent and the LLM provider. The agent talks to CVC like it's talking to any normal API. Behind the scenes, CVC manages everything.

```
┌─────────────────────────────────────────────────────────────┐
│                      YOUR MACHINE                           │
│                                                             │
│  ┌──────────┐         ┌──────────────────┐                  │
│  │  Agent   │  HTTP   │   CVC Proxy      │   HTTPS          │
│  │ (Cursor, │ ──────▶ │   localhost:8000  │ ──────────▶  ☁  │
│  │ VS Code, │ ◀────── │                  │ ◀──────────     │
│  │  Custom) │         │  ┌────────────┐  │   Claude /      │
│  └──────────┘         │  │ LangGraph  │  │   GPT /         │
│                       │  │ Router     │  │   Gemini        │
│                       │  └──────┬─────┘  │                  │
│                       └─────────┼────────┘                  │
│                                 │                           │
│                    ┌────────────┼────────────┐              │
│                    │            │            │              │
│               ┌────▼────┐ ┌────▼────┐ ┌─────▼────┐        │
│               │ SQLite  │ │  CAS    │ │  Chroma  │        │
│               │ (Index) │ │ (Blobs) │ │ (Vectors)│        │
│               └─────────┘ └─────────┘ └──────────┘        │
│                                                             │
│                       .cvc/ directory                       │
│               (lives in your project, like .git)            │
└─────────────────────────────────────────────────────────────┘
```

**Three-tiered storage, all local:**

| | What | Why |
|---|------|-----|
| **SQLite** | Commit graph, branch pointers, metadata | Fast traversal, zero-config |
| **CAS Blobs** | Compressed context snapshots (Zstandard) | Content-addressable, deduplicated |
| **Chroma** | Semantic embeddings *(optional)* | "Have I solved this before?" |

Everything stays in `.cvc/` inside your project. No cloud. No telemetry. Your agent's thought process is **yours**.

<br/>

---

## 🚀 Get Started

### Prerequisites

- **Python 3.11+**
- **uv** *(recommended)* or pip
- **Git** *(for VCS bridge features)*

### Install

```bash
git clone https://github.com/mannuking/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control

# Using uv (recommended — installs in seconds)
uv sync --extra dev

# Or using pip
pip install -e ".[dev]"
```

### Run

```bash
# Initialise CVC in your project
cvc init

# Set your API key
# PowerShell:
$env:ANTHROPIC_API_KEY = "sk-ant-..."
# Bash:
export ANTHROPIC_API_KEY="sk-ant-..."

# Start the proxy
cvc serve

# (Optional) Install Git hooks for automatic sync
cvc install-hooks
```

### Connect Your Agent

Point your AI agent's API base URL to `http://127.0.0.1:8000`. CVC exposes an **OpenAI-compatible** `/v1/chat/completions` endpoint — any tool that speaks OpenAI format works out of the box.

| Works With | How |
|-----------|-----|
| **Cursor** | Set CVC as the API base URL in settings |
| **VS Code + Copilot** | Route through CVC proxy |
| **Custom agents** | Standard OpenAI SDK, point to `localhost:8000` |
| **LangChain / CrewAI / AutoGen** | Use CVC's 4 function-calling tools (`GET /cvc/tools`) |

<br/>

---

## 📟 CLI

```
cvc init                    Initialise .cvc/ in your project
cvc serve                   Start the Cognitive Proxy
cvc status                  Show branch, HEAD, context size
cvc log                     View commit history
cvc commit -m "message"     Create a cognitive checkpoint
cvc branch <name>           Create an exploration branch
cvc merge <branch>          Semantic merge into active branch
cvc restore <hash>          Time-travel to a previous state
cvc install-hooks           Install Git ↔ CVC sync hooks
cvc capture-snapshot        Link current Git commit to CVC state
```

<br/>

---

## 🔗 Git Integration

CVC doesn't replace Git — it **bridges** with it.

| Feature | What It Does |
|---------|-------------|
| **Shadow Branches** | CVC state lives on `cvc/main`, keeping your main branch clean |
| **Git Notes** | Every `git commit` is annotated with the CVC hash — *"What was the AI thinking when it wrote this?"* |
| **post-commit hook** | Auto-captures cognitive state after every `git commit` |
| **post-checkout hook** | Auto-restores the agent's brain when you `git checkout` an old commit |

When you check out an old version of your code, CVC **automatically restores** the agent's context to what it was when that code was written. True cognitive time-travel.

<br/>

---

## ⚡ Why It's Cheap

CVC structures prompts so committed history becomes a **cacheable prefix**. When you rewind to a checkpoint, the model doesn't reprocess anything it's already seen.

| Metric | Without CVC | With CVC |
|--------|-------------|----------|
| **Cost per restore** | Full price | **~90% cheaper** |
| **Latency per restore** | Full processing | **~85% faster** |
| **Checkpoint frequency** | Impractical | **Economically viable** |

This works today with **Anthropic prompt caching**, with OpenAI and Google adapters on the roadmap.

<br/>

---

## ⚙️ Configuration

All via **environment variables** — no config files to manage:

| Variable | Default | What It Does |
|----------|---------|-------------|
| `CVC_AGENT_ID` | `sofia` | Agent identifier |
| `CVC_DEFAULT_BRANCH` | `main` | Default branch |
| `CVC_ANCHOR_INTERVAL` | `10` | Full snapshot every N commits (others are delta-compressed) |
| `CVC_PROVIDER` | `anthropic` | LLM provider |
| `CVC_MODEL` | `claude-sonnet-4-20250514` | Model |
| `ANTHROPIC_API_KEY` | — | Your API key |
| `CVC_HOST` | `127.0.0.1` | Proxy host |
| `CVC_PORT` | `8000` | Proxy port |
| `CVC_VECTOR_ENABLED` | `false` | Enable semantic search (Chroma) |

<br/>

---

## 🎯 Who Is This For?

<table>
<tr>
<td width="33%" valign="top">

### Solo Developers
Your AI stops losing context mid-session. Explore multiple approaches. Undo mistakes. Never re-explain the same thing twice.

</td>
<td width="33%" valign="top">

### Teams & Organizations
Review the AI's *reasoning*, not just its output. Cryptographic audit trails. Shared cognitive state across team members. Compliance-ready.

</td>
<td width="33%" valign="top">

### Open Source
See *how* an AI-generated PR was produced. Inspect for hallucination patterns. Build project knowledge bases from commit embeddings.

</td>
</tr>
</table>

<br/>

---

## 🗺️ Roadmap

- [ ] **OpenAI Adapter** — prefix caching for GPT-4o
- [ ] **Google/Gemini Adapter** — `cachedContent.create` with TTL
- [ ] **Local Inference** — KV Cache serialisation for vLLM / Ollama
- [ ] **VS Code Extension** — visual commit graph and time-travel slider
- [ ] **MCP Server** — native Model Context Protocol integration
- [ ] **Multi-agent support** — shared CVC database with conflict resolution
- [ ] **Cloud sync** — S3/MinIO for team collaboration
- [ ] **Metrics dashboard** — cache hit rates, context utilisation, branch success rates

<br/>

---

## 🤝 Contributing

**This repo is public and open to collaboration.** Whether you're fixing a typo or building an entirely new provider adapter — contributions are welcome.

1. **Fork** the repo
2. **Branch** (`git checkout -b feature/your-idea`)
3. **Commit** and **Push**
4. **Open a Pull Request**

### Areas where help is needed:

| Area | Difficulty |
|------|-----------|
| 🔌 Provider Adapters (OpenAI, Gemini, Ollama) | Medium |
| 🧪 Tests & edge cases | Easy–Medium |
| 🖥️ VS Code Extension | Hard |
| 🌐 MCP Server | Medium |
| 🔒 Security audit | Medium–Hard |

### Dev setup:

```bash
git clone https://github.com/YOUR_USERNAME/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control
uv sync --extra dev
```

<br/>

---

## 📚 Research

CVC is grounded in published research:

- [ContextBranch](https://arxiv.org/abs/2512.13914) — 58.1% context reduction via branching
- [GCC](https://arxiv.org/abs/2508.00031) — 11.7% → 40.7% success with rollback
- [Merkle-CRDTs](https://research.protocol.ai/publications/merkle-crdts-merkle-dags-meet-crdts/psaras2020.pdf) — structural deduplication for DAGs
- [Prompt Caching](https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models) — Anthropic/OpenAI/Google token reuse

<br/>

---

## 📜 License

MIT — see [LICENSE](LICENSE).

---

<br/>

<p align="center">
  <strong>Because AI agents deserve an undo button.</strong>
</p>

<p align="center">
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control">⭐ Star</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/issues">🐛 Bug</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/issues">💡 Feature</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/pulls">🔀 PR</a>
</p>
