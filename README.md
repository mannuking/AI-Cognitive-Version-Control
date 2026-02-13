<div align="center">

# ⏳ Time Machine for AI Agents

### *Cognitive Version Control (CVC)*

**Save. Branch. Rewind. Merge. — Your AI agent just got an undo button.**

---

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Alpha-orange?style=for-the-badge)](https://github.com/mannuking/AI-Cognitive-Version-Control)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](http://makeapullrequest.com)

[![GitHub Stars](https://img.shields.io/github/stars/mannuking/AI-Cognitive-Version-Control?style=social)](https://github.com/mannuking/AI-Cognitive-Version-Control/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/mannuking/AI-Cognitive-Version-Control?style=social)](https://github.com/mannuking/AI-Cognitive-Version-Control/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/mannuking/AI-Cognitive-Version-Control?style=social)](https://github.com/mannuking/AI-Cognitive-Version-Control/issues)

[✨ Features](#-the-problem-were-solving) • [🚀 Quick Start](#-get-started) • [📖 Documentation](#-cli) • [🤝 Contributing](#-contributing) • [💬 Community](#-contributing)

---

</div>

<br>

<div align="center">

### Your AI coding agent is brilliant — for about 20 minutes.

Then it forgets what it already fixed, contradicts its own plan,  
and loops on the same error for eternity.

***Sound familiar?***

</div>

<br>

---

## 🧠 What Is This?

**Time Machine for AI Agents** gives AI coding agents something they've never had: **memory management** that actually works.

> **Git, but for the AI's brain.**  
> Instead of versioning source code, CVC versions the agent's *entire context* — every thought, every decision, every conversation turn — as an immutable, cryptographic Merkle DAG.

The agent can **checkpoint** its reasoning, **branch** into risky experiments, **rewind** when stuck, and **merge** only the insights that matter.

<br>

<div align="center">

<table>
<thead>
<tr>
<th align="center">💾 Save</th>
<th align="center">🌿 Branch</th>
<th align="center">🔀 Merge</th>
<th align="center">⏪ Rewind</th>
</tr>
</thead>
<tbody>
<tr>
<td align="center">Checkpoint the agent's brain at any stable moment.</td>
<td align="center">Explore risky ideas in isolation. Main context stays clean.</td>
<td align="center">Merge <em>learnings</em> back — not raw logs. Semantic, not syntactic.</td>
<td align="center">Stuck in a loop? Time-travel back instantly.</td>
</tr>
</tbody>
</table>

</div>

<br>

---

## 🔥 The Problem We're Solving

<div align="center">

### The industry keeps making context windows bigger — 4K → 32K → 128K → 1M+ tokens  
### ***It's not progress.***

</div>

Research shows that after **~60% context utilisation**, LLM reasoning quality **falls off a cliff**. One hallucination poisons everything that follows. Error cascades compound. The agent starts fighting itself.

<div align="center">

> **A bigger window doesn't fix context rot.**  
> **It just gives it more room to spread.**

</div>

### The Real Issue

AI agents have **zero ability to manage their own cognitive state**. They can't save their work. They can't explore safely. They can't undo mistakes. They're solving a 500-piece puzzle while someone keeps removing pieces from the table.

<br>

### 📊 What the Research Shows

<table>
<tr>
<td align="center"><strong>58.1%</strong><br>Context reduction via branching</td>
<td align="center"><strong>3.5×</strong><br>Success rate improvement with rollback</td>
<td align="center"><strong>~90%</strong><br>Cost reduction through caching</td>
<td align="center"><strong>~85%</strong><br>Latency reduction</td>
</tr>
<tr>
<td align="center"><sub><a href="https://arxiv.org/abs/2512.13914">ContextBranch paper</a></sub></td>
<td align="center"><sub><a href="https://arxiv.org/abs/2508.00031">GCC paper</a></sub></td>
<td align="center"><sub>Prompt caching</sub></td>
<td align="center"><sub>Cached tokens skip processing</sub></td>
</tr>
</table>

<br>

---

## ⚙️ How It Works

CVC runs as a **local proxy** between your agent and the LLM provider.  
The agent talks to CVC like any normal API. Behind the scenes, CVC manages everything.

<br>

<div align="center">

```
┌──────────────────────────────────────────────────────────────┐
│                      YOUR MACHINE                            │
│                                                              │
│  ┌──────────┐        ┌──────────────────┐                   │
│  │  Agent   │  HTTP  │   CVC Proxy       │   HTTPS          │
│  │ (Cursor, │ ─────▶ │   localhost:8000  │ ────────▶  ☁    │
│  │ VS Code, │ ◀───── │                   │ ◀────────       │
│  │  Custom) │        │  ┌────────────┐   │  Claude /       │
│  └──────────┘        │  │ LangGraph  │   │  GPT-5.2 /      │
│                      │  │ Router     │   │  Gemini /       │
│                      │  │            │   │  Ollama         │
│                      │  └──────┬─────┘   │                  │
│                      └─────────┼─────────┘                  │
│                                │                            │
│                   ┌────────────┼────────────┐               │
│                   │            │            │               │
│              ┌────▼────┐ ┌────▼────┐ ┌─────▼────┐         │
│              │ SQLite  │ │  CAS    │ │  Chroma  │         │
│              │ (Index) │ │ (Blobs) │ │ (Vectors)│         │
│              └─────────┘ └─────────┘ └──────────┘         │
│                                                             │
│                      .cvc/ directory                        │
│              (lives in your project, like .git)             │
└──────────────────────────────────────────────────────────────┘
```

</div>

<br>

### 🎯 Three-Tiered Storage (All Local)

<table>
<thead>
<tr>
<th width="20%">Tier</th>
<th width="30%">What</th>
<th width="50%">Why</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>🗄️ SQLite</strong></td>
<td>Commit graph, branch pointers, metadata</td>
<td>Fast traversal, zero-config, works everywhere</td>
</tr>
<tr>
<td><strong>📦 CAS Blobs</strong></td>
<td>Compressed context snapshots (Zstandard)</td>
<td>Content-addressable, deduplicated, efficient</td>
</tr>
<tr>
<td><strong>🔍 Chroma</strong></td>
<td>Semantic embeddings <em>(optional)</em></td>
<td>"Have I solved this before?" — search by meaning</td>
</tr>
</tbody>
</table>

<br>

<div align="center">

✨ Everything stays in `.cvc/` inside your project  
🔒 No cloud • No telemetry • Your agent's thoughts are **yours**

</div>

<br>

---

## 🚀 Get Started

<br>

<div align="center">

### Prerequisites

Python 3.11+ • uv *(recommended)* or pip • Git *(for VCS bridge features)*

</div>

<br>

### 📦 Install

```bash
git clone https://github.com/mannuking/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control

# Using uv (recommended — installs in seconds)
uv sync --extra dev

# Or using pip
pip install -e ".[dev]"
```

### ▶️ Run

```bash
# Interactive guided setup (picks provider, shows models, initialises .cvc/)
cvc setup

# — OR — manual setup:
cvc init
```

### 🔑 Set Your API Key

<table>
<thead>
<tr><th>Provider</th><th>Bash / Linux / macOS</th><th>PowerShell</th></tr>
</thead>
<tbody>
<tr>
<td><strong>Anthropic</strong></td>
<td><code>export ANTHROPIC_API_KEY="sk-ant-..."</code></td>
<td><code>$env:ANTHROPIC_API_KEY = "sk-ant-..."</code></td>
</tr>
<tr>
<td><strong>OpenAI</strong></td>
<td><code>export OPENAI_API_KEY="sk-..."</code></td>
<td><code>$env:OPENAI_API_KEY = "sk-..."</code></td>
</tr>
<tr>
<td><strong>Google</strong></td>
<td><code>export GOOGLE_API_KEY="AIza..."</code></td>
<td><code>$env:GOOGLE_API_KEY = "AIza..."</code></td>
</tr>
<tr>
<td><strong>Ollama</strong></td>
<td colspan="2">No key needed — just run <code>ollama serve</code> and <code>ollama pull qwen2.5-coder:7b</code></td>
</tr>
</tbody>
</table>

```bash
# Start the proxy with your chosen provider
CVC_PROVIDER=anthropic cvc serve    # or: openai, google, ollama

# (Optional) Install Git hooks for automatic sync
cvc install-hooks
```

### 🔌 Connect Your Agent

Point your AI agent's API base URL to **`http://127.0.0.1:8000`**

CVC exposes an **OpenAI-compatible** `/v1/chat/completions` endpoint — any tool that speaks OpenAI format works out of the box.

<br>

<div align="center">

<table>
<thead>
<tr>
<th width="30%">Tool</th>
<th width="70%">How to Connect</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>🎯 Cursor</strong></td>
<td>Set CVC as the API base URL in settings</td>
</tr>
<tr>
<td><strong>💻 VS Code + Copilot</strong></td>
<td>Route through CVC proxy</td>
</tr>
<tr>
<td><strong>🔧 Custom Agents</strong></td>
<td>Standard OpenAI SDK, point to <code>localhost:8000</code></td>
</tr>
<tr>
<td><strong>🦜 LangChain / CrewAI / AutoGen</strong></td>
<td>Use CVC's 4 function-calling tools (<code>GET /cvc/tools</code>)</td>
</tr>
</tbody>
</table>

</div>

<br>

---

## 📟 CLI Reference

<br>

<div align="center">

<table>
<thead>
<tr>
<th width="40%">Command</th>
<th width="60%">Description</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>cvc setup</code></td>
<td>Interactive first-time setup (choose provider &amp; model)</td>
</tr>
<tr>
<td><code>cvc init</code></td>
<td>Initialize <code>.cvc/</code> in your project</td>
</tr>
<tr>
<td><code>cvc serve</code></td>
<td>Start the Cognitive Proxy</td>
</tr>
<tr>
<td><code>cvc status</code></td>
<td>Show branch, HEAD, context size</td>
</tr>
<tr>
<td><code>cvc log</code></td>
<td>View commit history</td>
</tr>
<tr>
<td><code>cvc commit -m "message"</code></td>
<td>Create a cognitive checkpoint</td>
</tr>
<tr>
<td><code>cvc branch &lt;name&gt;</code></td>
<td>Create an exploration branch</td>
</tr>
<tr>
<td><code>cvc merge &lt;branch&gt;</code></td>
<td>Semantic merge into active branch</td>
</tr>
<tr>
<td><code>cvc restore &lt;hash&gt;</code></td>
<td>Time-travel to a previous state</td>
</tr>
<tr>
<td><code>cvc install-hooks</code></td>
<td>Install Git ↔ CVC sync hooks</td>
</tr>
<tr>
<td><code>cvc capture-snapshot</code></td>
<td>Link current Git commit to CVC state</td>
</tr>
</tbody>
</table>

</div>

<br>

---

## 🔗 Git Integration

<div align="center">

### CVC doesn't replace Git — it **bridges** with it.

</div>

<br>

<table>
<thead>
<tr>
<th width="30%">Feature</th>
<th width="70%">What It Does</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>🌲 Shadow Branches</strong></td>
<td>CVC state lives on <code>cvc/main</code>, keeping your main branch clean</td>
</tr>
<tr>
<td><strong>📝 Git Notes</strong></td>
<td>Every <code>git commit</code> is annotated with the CVC hash — <em>"What was the AI thinking when it wrote this?"</em></td>
</tr>
<tr>
<td><strong>🔄 post-commit hook</strong></td>
<td>Auto-captures cognitive state after every <code>git commit</code></td>
</tr>
<tr>
<td><strong>⏰ post-checkout hook</strong></td>
<td>Auto-restores the agent's brain when you <code>git checkout</code> an old commit</td>
</tr>
</tbody>
</table>

<br>

<div align="center">

📜 When you check out an old version of your code, CVC **automatically restores**  
the agent's context to what it was when that code was written.

✨ **True cognitive time-travel.**

</div>

<br>

---

## ⚡ Why It's Cheap

<div align="center">

CVC structures prompts so committed history becomes a **cacheable prefix**.  
When you rewind to a checkpoint, the model doesn't reprocess anything it's already seen.

</div>

<br>

<table>
<thead>
<tr>
<th width="30%">Metric</th>
<th align="center" width="35%">❌ Without CVC</th>
<th align="center" width="35%">✅ With CVC</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>💰 Cost per restore</strong></td>
<td align="center">Full price</td>
<td align="center"><strong>~90% cheaper</strong></td>
</tr>
<tr>
<td><strong>⚡ Latency per restore</strong></td>
<td align="center">Full processing</td>
<td align="center"><strong>~85% faster</strong></td>
</tr>
<tr>
<td><strong>🔄 Checkpoint frequency</strong></td>
<td align="center">Impractical</td>
<td align="center"><strong>Economically viable</strong></td>
</tr>
</tbody>
</table>

<br>

<div align="center">

🔥 Works today with **Anthropic**, **OpenAI**, **Google Gemini**, and **Ollama**  
💡 Prompt caching optimised per provider

</div>

<br>

---

## 🤖 Supported Providers

<div align="center">

### Pick your provider. CVC handles the rest.

</div>

<br>

<table>
<thead>
<tr>
<th width="15%">Provider</th>
<th width="30%">Default Model</th>
<th width="30%">Alternatives</th>
<th width="25%">Notes</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Anthropic</strong></td>
<td><code>claude-opus-4-6</code></td>
<td><code>claude-sonnet-4-5</code>, <code>claude-haiku-4-5</code></td>
<td>Prompt caching with <code>cache_control</code></td>
</tr>
<tr>
<td><strong>OpenAI</strong></td>
<td><code>gpt-5.2</code></td>
<td><code>gpt-5.2-codex</code>, <code>gpt-5-mini</code>, <code>gpt-4.1</code></td>
<td>Automatic prefix caching</td>
</tr>
<tr>
<td><strong>Google</strong></td>
<td><code>gemini-3-pro</code></td>
<td><code>gemini-3-flash</code>, <code>gemini-2.5-flash</code>, <code>gemini-2.5-pro</code></td>
<td>OpenAI-compatible endpoint</td>
</tr>
<tr>
<td><strong>Ollama</strong></td>
<td><code>qwen2.5-coder:7b</code></td>
<td><code>qwen3-coder:30b</code>, <code>devstral:24b</code>, <code>deepseek-r1:8b</code></td>
<td>100% local, no API key needed</td>
</tr>
</tbody>
</table>

<br>

---

## ⚙️ Configuration

<div align="center">

### All via **environment variables** — no config files to manage

</div>

<br>

<table>
<thead>
<tr>
<th width="30%">Variable</th>
<th width="20%">Default</th>
<th width="50%">What It Does</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>CVC_AGENT_ID</code></td>
<td><code>sofia</code></td>
<td>Agent identifier</td>
</tr>
<tr>
<td><code>CVC_DEFAULT_BRANCH</code></td>
<td><code>main</code></td>
<td>Default branch</td>
</tr>
<tr>
<td><code>CVC_ANCHOR_INTERVAL</code></td>
<td><code>10</code></td>
<td>Full snapshot every N commits (others are delta-compressed)</td>
</tr>
<tr>
<td><code>CVC_PROVIDER</code></td>
<td><code>anthropic</code></td>
<td>LLM provider</td>
</tr>
<tr>
<td><code>CVC_MODEL</code></td>
<td><em>auto</em></td>
<td>Model name (auto-detected per provider)</td>
</tr>
<tr>
<td><code>ANTHROPIC_API_KEY</code></td>
<td>—</td>
<td>Required for <code>anthropic</code> provider</td>
</tr>
<tr>
<td><code>OPENAI_API_KEY</code></td>
<td>—</td>
<td>Required for <code>openai</code> provider</td>
</tr>
<tr>
<td><code>GOOGLE_API_KEY</code></td>
<td>—</td>
<td>Required for <code>google</code> provider</td>
</tr>
<tr>
<td><code>CVC_HOST</code></td>
<td><code>127.0.0.1</code></td>
<td>Proxy host</td>
</tr>
<tr>
<td><code>CVC_PORT</code></td>
<td><code>8000</code></td>
<td>Proxy port</td>
</tr>
<tr>
<td><code>CVC_VECTOR_ENABLED</code></td>
<td><code>false</code></td>
<td>Enable semantic search (Chroma)</td>
</tr>
</tbody>
</table>

<br>

---

## 🎯 Who Is This For?

<br>

<table>
<thead>
<tr>
<th width="33%" align="center">👤 Solo Developers</th>
<th width="34%" align="center">🏢 Teams & Organizations</th>
<th width="33%" align="center">🌐 Open Source</th>
</tr>
</thead>
<tbody>
<tr>
<td valign="top">
<br>
Your AI stops losing context mid-session. Explore multiple approaches. Undo mistakes. Never re-explain the same thing twice.
<br><br>
</td>
<td valign="top">
<br>
Review the AI's <em>reasoning</em>, not just its output. Cryptographic audit trails. Shared cognitive state across team members. Compliance-ready.
<br><br>
</td>
<td valign="top">
<br>
See <em>how</em> an AI-generated PR was produced. Inspect for hallucination patterns. Build project knowledge bases from commit embeddings.
<br><br>
</td>
</tr>
</tbody>
</table>

<br>

---

## 🗺️ Roadmap

<br>

<table>
<thead>
<tr>
<th width="50%">Feature</th>
<th width="50%">Description</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>✅ OpenAI Adapter</strong></td>
<td>GPT-5.2 / GPT-5.2-Codex / GPT-5-mini</td>
</tr>
<tr>
<td><strong>✅ Google Gemini Adapter</strong></td>
<td>Gemini 3 Pro / Flash / 2.5 Flash</td>
</tr>
<tr>
<td><strong>✅ Ollama (Local)</strong></td>
<td>Qwen 2.5 Coder / Qwen 3 Coder / DeepSeek-R1 / Devstral</td>
</tr>
<tr>
<td><strong>🎨 VS Code Extension</strong></td>
<td>Visual commit graph and time-travel slider</td>
</tr>
<tr>
<td><strong>🌐 MCP Server</strong></td>
<td>Native Model Context Protocol integration</td>
</tr>
<tr>
<td><strong>👥 Multi-agent support</strong></td>
<td>Shared CVC database with conflict resolution</td>
</tr>
<tr>
<td><strong>☁️ Cloud sync</strong></td>
<td>S3/MinIO for team collaboration</td>
</tr>
<tr>
<td><strong>📊 Metrics dashboard</strong></td>
<td>Cache hit rates, context utilisation, branch success rates</td>
</tr>
</tbody>
</table>

<br>

---

## 🤝 Contributing

<div align="center">

### **This repo is public and open to collaboration.**

Whether you're fixing a typo or building an entirely new provider adapter — contributions are welcome.

<br>

**Fork** → **Branch** → **Commit** → **Push** → **PR**

</div>

<br>

### 🎯 Areas Where Help Is Needed

<table>
<thead>
<tr>
<th width="60%">Area</th>
<th width="40%" align="center">Difficulty</th>
</tr>
</thead>
<tbody>
<tr>
<td>🔌 Additional Provider Adapters (Mistral, Cohere, etc.)</td>
<td align="center">🟡 Medium</td>
</tr>
<tr>
<td>🧪 Tests & edge cases</td>
<td align="center">🟢 Easy–Medium</td>
</tr>
<tr>
<td>🖥️ VS Code Extension</td>
<td align="center">🔴 Hard</td>
</tr>
<tr>
<td>🌐 MCP Server</td>
<td align="center">🟡 Medium</td>
</tr>
<tr>
<td>🔒 Security audit</td>
<td align="center">🟠 Medium–Hard</td>
</tr>
</tbody>
</table>

<br>

### 🛠️ Dev Setup

```bash
git clone https://github.com/YOUR_USERNAME/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control
uv sync --extra dev
```

<br>

---

## 📚 Research

<div align="center">

### CVC is grounded in published research

</div>

<br>

<table>
<thead>
<tr>
<th width="35%">Paper</th>
<th width="65%">Key Finding</th>
</tr>
</thead>
<tbody>
<tr>
<td><a href="https://arxiv.org/abs/2512.13914"><strong>ContextBranch</strong></a></td>
<td>58.1% context reduction via branching</td>
</tr>
<tr>
<td><a href="https://arxiv.org/abs/2508.00031"><strong>GCC</strong></a></td>
<td>11.7% → 40.7% success with rollback</td>
</tr>
<tr>
<td><a href="https://research.protocol.ai/publications/merkle-crdts-merkle-dags-meet-crdts/psaras2020.pdf"><strong>Merkle-CRDTs</strong></a></td>
<td>Structural deduplication for DAGs</td>
</tr>
<tr>
<td><a href="https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models"><strong>Prompt Caching</strong></a></td>
<td>Anthropic/OpenAI/Google token reuse</td>
</tr>
</tbody>
</table>

<br>

---

## 📜 License

<div align="center">

**MIT** — see [LICENSE](LICENSE)

</div>

<br>
<br>

---

<br>

<div align="center">

### ✨ Because AI agents deserve an undo button. ✨

<br>

**[⭐ Star this repo](https://github.com/mannuking/AI-Cognitive-Version-Control)** if you believe in giving AI agents memory that actually works.

<br>

[![GitHub Stars](https://img.shields.io/github/stars/mannuking/AI-Cognitive-Version-Control?style=social)](https://github.com/mannuking/AI-Cognitive-Version-Control/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/mannuking/AI-Cognitive-Version-Control?style=social)](https://github.com/mannuking/AI-Cognitive-Version-Control/network/members)
[![GitHub Watchers](https://img.shields.io/github/watchers/mannuking/AI-Cognitive-Version-Control?style=social)](https://github.com/mannuking/AI-Cognitive-Version-Control/watchers)

<br>

Made with ❤️ by developers who got tired of AI agents forgetting what they just did.

<br>

<p align="center">
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control">⭐ Star</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/issues">🐛 Bug</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/issues">💡 Feature</a> · 
  <a href="https://github.com/mannuking/AI-Cognitive-Version-Control/pulls">🔀 PR</a>
</p>
