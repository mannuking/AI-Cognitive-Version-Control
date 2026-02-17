# Cognitive Version Control (CVC) — Documentation

> **Git for the AI Mind.** Save, branch, rewind, and merge your AI agent's cognitive state.

---

## Table of Contents

- [Overview](#overview)
- [Key Concepts](#key-concepts)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Setting Your API Key](#setting-your-api-key)
- [CVC Agent](#cvc-agent)
  - [Launching the Agent](#launching-the-agent)
  - [Agent Options](#agent-options)
  - [Built-in Tools](#built-in-tools)
  - [Slash Commands](#slash-commands)
  - [Auto-Commit](#auto-commit)
- [CLI Reference](#cli-reference)
  - [Core Commands](#core-commands)
  - [Setup & Configuration](#setup--configuration)
  - [Time Machine Commands](#time-machine-commands)
  - [Utility Commands](#utility-commands)
- [Connecting AI Tools](#connecting-ai-tools)
  - [Proxy Mode (API-Based Tools)](#proxy-mode-api-based-tools)
  - [MCP Mode (Auth-Based IDEs)](#mcp-mode-auth-based-ides)
  - [IDE Connections](#ide-connections)
  - [CLI Tool Connections](#cli-tool-connections)
  - [Zero-Config Launch](#zero-config-launch)
- [Proxy Server](#proxy-server)
  - [Starting the Proxy](#starting-the-proxy)
  - [Endpoints](#endpoints)
  - [Auth Pass-Through](#auth-pass-through)
- [MCP Server](#mcp-server)
  - [Transports](#transports)
  - [IDE Configuration Examples](#ide-configuration-examples)
- [Time Machine Mode](#time-machine-mode)
  - [How It Works](#how-time-machine-works)
  - [Session Tracking](#session-tracking)
  - [Supported External Tools](#supported-external-tools)
- [Git Integration](#git-integration)
  - [Shadow Branches](#shadow-branches)
  - [Git Notes](#git-notes)
  - [Hooks](#hooks)
- [Supported Providers](#supported-providers)
  - [Anthropic](#anthropic)
  - [OpenAI](#openai)
  - [Google (Gemini)](#google-gemini)
  - [Ollama (Local)](#ollama-local)
- [Configuration Reference](#configuration-reference)
  - [Environment Variables](#environment-variables)
  - [Global Config](#global-config)
  - [Project Config](#project-config)
- [Architecture](#architecture)
  - [System Overview](#system-overview)
  - [Three-Tiered Storage](#three-tiered-storage)
  - [Directory Structure](#directory-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**Cognitive Version Control (CVC)** is a state-management middleware for AI coding agents. It gives AI agents capabilities they've never had — the ability to **save** their reasoning, **branch** into risky experiments, **rewind** when stuck, and **merge** only the insights that matter.

Instead of versioning source code (that's Git's job), CVC versions the agent's *entire context* — every thought, every decision, every conversation turn — as an immutable, cryptographic **Merkle DAG**.

### Why CVC Exists

AI agents are brilliant — for about 20 minutes. Then they forget what they already fixed, contradict their own plans, and loop on the same error. Research shows that after ~60% context utilisation, LLM reasoning quality falls off a cliff. A bigger context window doesn't fix context rot — it just gives it more room to spread.

CVC solves this by giving agents **cognitive state management**:

| Capability | Description |
|---|---|
| **Save** | Checkpoint the agent's brain at any stable moment |
| **Branch** | Explore risky ideas in isolation — main context stays clean |
| **Merge** | Merge *learnings* back — semantic, not syntactic |
| **Rewind** | Stuck in a loop? Time-travel back instantly |

### How CVC Operates

CVC works in **two modes**:

1. **Agent Mode** — A built-in AI coding assistant in your terminal (just type `cvc`)
2. **Proxy Mode** — A transparent middleware between your favourite AI tool and the LLM provider

All data is stored **locally** inside a `.cvc/` directory in your project. No cloud, no telemetry — your agent's thoughts are yours.

---

## Key Concepts

| Term | Meaning |
|---|---|
| **Cognitive Commit** | A snapshot of the AI agent's full context (conversation history, reasoning state) at a point in time |
| **Branch** | An isolated exploration path — lets the agent try risky approaches without polluting the main context |
| **Restore** | Time-travel — rewinds the agent's context to a previous commit |
| **Merge** | Combines insights from one branch into another (semantic, not raw log concatenation) |
| **Merkle DAG** | The cryptographic data structure that stores commits — content-addressable, immutable, deduplicated |
| **Anchor** | A full snapshot commit (every N commits); other commits are delta-compressed against anchors |
| **CAS Blobs** | Content-Addressable Storage — Zstandard-compressed context snapshots |
| **Time Machine** | Automatic checkpointing mode that saves every N assistant turns |

---

## Getting Started

### Prerequisites

- **Python 3.11** or higher
- **Git** (optional, required for VCS bridge features)
- An API key from one of the supported providers (or Ollama for local models)

### Installation

CVC is published on [PyPI](https://pypi.org/project/tm-ai/) as **`tm-ai`**.

```bash
pip install tm-ai
```

That's it. The `cvc` command is now available globally.

#### Additional Install Options

```bash
# With uv (faster)
uv pip install tm-ai

# As an isolated uv tool (always on PATH, no venv needed)
uv tool install tm-ai

# With provider-specific extras
pip install "tm-ai[anthropic]"     # Anthropic (Claude)
pip install "tm-ai[openai]"        # OpenAI (GPT)
pip install "tm-ai[google]"        # Google (Gemini)
pip install "tm-ai[all]"           # All providers + vector search

# For local development / contributors
git clone https://github.com/mannuking/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control
uv sync --extra dev           # or: pip install -e ".[dev]"
```

#### Dependencies

Core dependencies (installed automatically):

- `fastapi` + `uvicorn` — Proxy server
- `httpx` — HTTP client
- `pydantic` — Data models
- `click` + `rich` — CLI framework
- `zstandard` — Delta compression
- `aiosqlite` — Async SQLite
- `GitPython` — Git integration
- `langgraph` + `langchain-core` — State machine routing
- `prompt_toolkit` — Interactive terminal input

Optional dependencies:

- `anthropic` — Anthropic provider
- `openai` — OpenAI provider
- `google-genai` — Google Gemini provider
- `chromadb` + `sentence-transformers` — Semantic vector search

### Quick Start

**The simplest way — just type `cvc`:**

```bash
cvc
```

If it's your first time, CVC runs the interactive setup wizard (pick your provider, model, and API key), then launches the agent directly.

**Or step by step:**

```bash
cvc setup              # Pick your provider & model (interactive wizard)
cvc init               # Initialise .cvc/ in your project
cvc serve              # Start the proxy server for external AI tools
```

**Or all-in-one:**

```bash
cvc up                 # setup + init + serve in one command
```

### Setting Your API Key

You can set API keys in three ways:

1. **Via `cvc setup`** — The setup wizard prompts you and saves the key securely on your machine.
2. **Via environment variables** — Set the appropriate variable for your provider.
3. **Via `--api-key` flag** — Pass directly when launching the agent.

#### Environment Variable Reference

**Bash / Linux / macOS:**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."     # Anthropic
export OPENAI_API_KEY="sk-..."            # OpenAI
export GOOGLE_API_KEY="AIza..."           # Google
```

**PowerShell (Windows):**

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."     # Anthropic
$env:OPENAI_API_KEY = "sk-..."            # OpenAI
$env:GOOGLE_API_KEY = "AIza..."           # Google
```

**Ollama** requires no API key — it runs locally. Just ensure `ollama serve` is running.

#### Key Provider URLs

| Provider | Get Your Key |
|---|---|
| Anthropic | https://console.anthropic.com/settings/keys |
| OpenAI | https://platform.openai.com/api-keys |
| Google | https://aistudio.google.com/apikey |
| Ollama | No key needed — [ollama.com](https://ollama.com) |

---

## CVC Agent

CVC ships with a **full agentic coding assistant** directly in your terminal. Think of it as Claude Code, but with the ability to save, branch, rewind, and search through your entire conversation history.

### Launching the Agent

```bash
cvc                    # Launch agent (runs setup on first use)
cvc agent              # Same thing — explicit subcommand
```

### Agent Options

```bash
cvc agent --provider anthropic          # Force a specific provider
cvc agent --provider openai             # Use OpenAI instead
cvc agent --provider google             # Use Google Gemini
cvc agent --provider ollama             # Use local Ollama models

cvc agent --model claude-sonnet-4-5     # Override the model
cvc agent --api-key sk-ant-...          # Pass API key directly
```

### Built-in Tools

The agent has access to **17 built-in tools** that let it work directly on your codebase:

| Icon | Tool | Description |
|---|---|---|
| 📖 | `read_file` | Read files with optional line ranges for large files |
| ✏️ | `write_file` | Create or overwrite files, auto-creates directories |
| 🔧 | `edit_file` | Precise find-and-replace edits with uniqueness validation |
| 🩹 | `patch_file` | Apply unified diff patches (more robust than edit_file) |
| 🖥️ | `bash` | Run shell commands (PowerShell on Windows, bash on Unix) |
| 🔍 | `glob` | Find files by pattern (`**/*.py`, `src/**/*.ts`) |
| 📝 | `grep` | Search file contents with regex + include filters |
| 📁 | `list_dir` | List directory contents to explore project structure |
| 🌐 | `web_search` | Search the web for docs, APIs, and error solutions |
| 📊 | `cvc_status` | Show current branch, HEAD, and context state |
| 📜 | `cvc_log` | View commit history — snapshots of the conversation |
| 💾 | `cvc_commit` | Save a checkpoint of the current conversation state |
| 🌿 | `cvc_branch` | Create a branch to explore alternatives safely |
| ⏪ | `cvc_restore` | Time-travel back to any previous conversation state |
| 🔀 | `cvc_merge` | Merge insights from one branch into another |
| 🔎 | `cvc_search` | Search commit history for specific topics or discussions |
| 📋 | `cvc_diff` | Compare conversation states between commits |

### Slash Commands

While chatting with the agent, use these slash commands for quick actions:

| Command | Description |
|---|---|
| `/help` | Show all available slash commands |
| `/status` | View branch, HEAD, context size, provider & model |
| `/log` | Show last 20 conversation checkpoints |
| `/commit <msg>` | Save a manual checkpoint of the conversation |
| `/branch <name>` | Create and switch to a new conversation branch |
| `/restore <hash>` | Time-travel back to a specific checkpoint |
| `/search <query>` | Search all commits for a topic |
| `/undo` | Undo the last file modification (edit/write/patch) |
| `/web <query>` | Search the web for docs or solutions |
| `/image <path>` | Analyse an image file (for UI bugs/mocks) |
| `/paste` | Analyse an image from clipboard (screenshots) |
| `/git <cmd>` | Run git commands with context awareness |
| `/cost` | Show session token usage and cost |
| `/compact` | Compress the conversation history, keeping recent context |
| `/clear` | Clear conversation history (CVC state preserved) |
| `/model <name>` | Switch LLM model mid-conversation |
| `/exit` | Save final checkpoint and exit cleanly |

### Auto-Commit

The agent **automatically saves checkpoints** every 5 assistant turns (configurable via `CVC_AGENT_AUTO_COMMIT`). When you exit with `/exit`, a final checkpoint is saved. You never lose context.

```bash
# Customise the interval
CVC_AGENT_AUTO_COMMIT=3 cvc agent    # Commit every 3 turns
```

---

## CLI Reference

### Core Commands

| Command | Description |
|---|---|
| `cvc` | **Launch the CVC Agent** — interactive AI coding assistant. Runs setup on first use. |
| `cvc agent` | Same as above (explicit subcommand) |
| `cvc agent --provider <p>` | Agent with a specific provider (`anthropic`, `openai`, `google`, `ollama`) |
| `cvc agent --model <m>` | Agent with a model override |
| `cvc agent --api-key <k>` | Agent with a direct API key |

### Setup & Configuration

| Command | Description |
|---|---|
| `cvc setup` | Interactive setup wizard — pick your provider, model, and API key. Detects installed IDEs and auto-configures where possible. |
| `cvc setup --provider <p>` | Non-interactive provider selection |
| `cvc setup --model <m>` | Non-interactive model selection |
| `cvc setup --api-key <k>` | Non-interactive API key |
| `cvc init` | Initialise a `.cvc/` directory in the current project |
| `cvc init --path <dir>` | Initialise in a specific directory |
| `cvc up` | **One-command start** — runs setup (if needed) + init (if needed) + starts the proxy server |
| `cvc up --host <h>` | Bind proxy to a specific host (default: `127.0.0.1`) |
| `cvc up --port <p>` | Bind proxy to a specific port (default: `8000`) |
| `cvc up --no-time-machine` | Disable Time Machine auto-commit |
| `cvc connect` | Interactive tool connection wizard — shows tool-specific setup instructions |
| `cvc connect <tool>` | Show setup instructions for a specific tool (e.g., `cvc connect cursor`) |
| `cvc connect --all` | Show setup instructions for all supported tools |
| `cvc doctor` | Health check — verifies Python version, config, .cvc/ directory, Git, API keys, and Ollama |

#### Setup Wizard Options

When running `cvc setup` with an existing configuration, you're presented with five options:

1. **Start Fresh** — Reconfigure everything from scratch
2. **Change Provider** — Switch to a different LLM provider
3. **Change Model** — Keep provider, pick a different model
4. **Update API Key** — Replace or add an API key
5. **Reset Everything** — Delete all config and start over

### Time Machine Commands

| Command | Description |
|---|---|
| `cvc status` | Show current branch, HEAD commit, context size, provider, and all branches |
| `cvc log` | View commit history for the active branch (default: last 20 commits) |
| `cvc log -n <N>` | Show last N commits |
| `cvc commit -m "message"` | Create a cognitive checkpoint (save the agent's brain state) |
| `cvc commit -m "msg" -t analysis` | Commit with a specific type (`checkpoint`, `analysis`, `generation`) |
| `cvc commit -m "msg" --tag <t>` | Add tags to a commit (repeatable) |
| `cvc branch <name>` | Create and switch to a new exploration branch |
| `cvc branch <name> -d "description"` | Create a branch with a description |
| `cvc merge <source>` | Merge source branch into the active branch (semantic three-way merge) |
| `cvc merge <source> --target <branch>` | Merge into a specific target branch (default: `main`) |
| `cvc restore <hash>` | Time-travel — restore the agent's context to a previous commit |
| `cvc sessions` | View Time Machine session history (requires proxy to be running) |

### Utility Commands

| Command | Description |
|---|---|
| `cvc install-hooks` | Install Git hooks for CVC ↔ Git synchronisation (`post-commit` and `post-checkout`) |
| `cvc capture-snapshot` | Capture CVC state linked to the current Git commit |
| `cvc capture-snapshot --git-sha <sha>` | Link to a specific Git SHA |
| `cvc doctor` | Health check — verifies your entire CVC environment |
| `cvc --version` | Show the installed CVC version |
| `cvc -v <command>` | Run any command with verbose/debug logging |

---

## Connecting AI Tools

CVC supports two connection paradigms depending on how your AI tool handles authentication.

### Proxy Mode (API-Based Tools)

For tools that accept custom API base URLs and API keys, CVC runs as a **transparent proxy server** on `http://127.0.0.1:8000`.

CVC exposes:
- **OpenAI-compatible API** at `/v1/chat/completions`
- **Anthropic-native API** at `/v1/messages`

```bash
cvc serve              # Start the proxy server
```

Then point your tool's base URL to `http://127.0.0.1:8000/v1` and use `cvc` as the API key.

### MCP Mode (Auth-Based IDEs)

For IDEs that use login-based authentication (GitHub Login, Google Login, account auth) and can't redirect API endpoints, CVC runs as an **MCP (Model Context Protocol) server**.

```bash
cvc mcp                    # Start MCP server (stdio transport)
cvc mcp --transport sse    # Start MCP server (HTTP/SSE transport)
```

The IDE's built-in agent calls CVC tools (commit, branch, merge, restore, status, log) through the MCP protocol.

### IDE Connections

| Tool | Auth Type | How to Connect |
|---|---|---|
| **VS Code + Copilot** | GitHub Login | **BYOK:** `Ctrl+Shift+P` → `Manage Models` → `OpenAI Compatible` — Base URL: `http://127.0.0.1:8000/v1`, API Key: `cvc`. **MCP:** Add `cvc mcp` to `.vscode/mcp.json`. **Extensions:** Use Continue.dev or Cline. |
| **Antigravity** | Google Login | MCP only — add `cvc` in MCP settings with command `cvc mcp` |
| **Cursor** | API Key Override | Settings → Models → Override OpenAI Base URL → `http://127.0.0.1:8000/v1`, API Key → `cvc`. Or use MCP. |
| **Windsurf** | Account Login | MCP only — add `cvc` in Cascade MCP settings with command `cvc mcp` |
| **Firebase Studio** | Google Login | Install Continue.dev or Cline from Open VSX and configure with CVC proxy endpoint |

#### VS Code Copilot BYOK Setup

1. Open VS Code
2. Press `Ctrl+Shift+P` → **Chat: Manage Language Models**
3. Select **OpenAI Compatible** as provider
4. Set Base URL → `http://127.0.0.1:8000/v1`
5. Set API Key → `cvc` (any non-empty string)
6. Select your model

> **Note:** BYOK is available on Copilot Individual plans (Free, Pro, Pro+). For Business/Enterprise, use MCP or an extension instead.

#### Cursor Setup

1. Open Cursor → Settings (⚙️) → **Models**
2. Click **Add OpenAI API Key** → paste `cvc`
3. Enable **Override OpenAI Base URL** → set to `http://127.0.0.1:8000/v1`
4. Select your model and start coding

#### MCP Configuration for IDEs

Add CVC as an MCP server in your IDE's configuration:

**VS Code** (`.vscode/mcp.json` or `settings.json`):
```json
{
  "mcp": {
    "servers": {
      "cvc": {
        "command": "cvc",
        "args": ["mcp"]
      }
    }
  }
}
```

**Antigravity / Windsurf / Cursor** (MCP config):
```json
{
  "mcpServers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"]
    }
  }
}
```

### CLI Tool Connections

| Tool | How to Connect |
|---|---|
| **Claude Code CLI** | `export ANTHROPIC_BASE_URL=http://127.0.0.1:8000` — uses native `/v1/messages` endpoint. Your `ANTHROPIC_API_KEY` is passed through. |
| **OpenAI Codex CLI** | Set `model_provider = "cvc"` in `~/.codex/config.toml`, or set `OPENAI_API_BASE=http://127.0.0.1:8000/v1` |
| **Aider** | `export OPENAI_API_BASE=http://127.0.0.1:8000/v1` and `export OPENAI_API_KEY=cvc`, then `aider --model openai/<model>` |
| **Gemini CLI** | `export GEMINI_API_BASE_URL=http://127.0.0.1:8000/v1` |
| **Kiro CLI** | `export OPENAI_API_BASE=http://127.0.0.1:8000/v1` and `export OPENAI_API_KEY=cvc` |
| **Continue.dev / Cline** | Base URL → `http://127.0.0.1:8000/v1`, API Key → `cvc` |
| **Open WebUI** | Settings → Connections → Add Connection → URL: `http://127.0.0.1:8000/v1`, API Key: `cvc` |
| **LangChain / CrewAI / AutoGen** | Use CVC's function-calling tools (`GET /cvc/tools`) |

#### Claude Code CLI (Detailed)

**Linux / macOS:**
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
claude
```

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8000"
claude
```

Or add to `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8000"
  }
}
```

#### Codex CLI (Detailed)

**Option 1 — Environment variables:**
```bash
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=cvc
codex
```

**Option 2 — Config file** (`~/.codex/config.toml`):
```toml
model_provider = "cvc"

[model_providers.cvc]
name = "CVC Proxy"
base_url = "http://127.0.0.1:8000"
env_key = "OPENAI_API_KEY"
```

### Zero-Config Launch

CVC can **automatically launch any AI tool** through the proxy with zero manual configuration:

```bash
cvc launch claude          # Launch Claude Code CLI with CVC
cvc launch aider           # Launch Aider through CVC proxy
cvc launch codex           # Launch OpenAI Codex CLI through CVC
cvc launch gemini          # Launch Gemini CLI through CVC
cvc launch kiro            # Launch Kiro CLI through CVC
cvc launch cursor          # Open Cursor with CVC auto-configured
cvc launch code            # Open VS Code with Copilot BYOK configured
cvc launch windsurf        # Open Windsurf with MCP configured
```

What `cvc launch` does automatically:
1. Sets up configuration (if first run)
2. Initialises `.cvc/` in the current project (if needed)
3. Starts the proxy server in the background
4. Configures the tool's environment variables / config files
5. Launches the tool — every conversation is time-machined

**Options:**
```bash
cvc launch                         # Interactive tool picker
cvc launch claude --no-time-machine  # Disable auto-commit
cvc launch aider --port 9000       # Use a custom proxy port
```

---

## Proxy Server

The CVC proxy server is a **FastAPI application** that sits between your AI tool and the LLM provider. It intercepts every API call, applies cognitive versioning, and forwards to the upstream provider.

### Starting the Proxy

```bash
cvc serve                          # Start on 127.0.0.1:8000 (default)
cvc serve --host 0.0.0.0          # Bind to all interfaces
cvc serve --port 9000             # Use a custom port
cvc serve --reload                # Enable auto-reload for development
```

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Health check |
| `POST /v1/chat/completions` | OpenAI-compatible chat completions |
| `POST /v1/messages` | Anthropic-native Messages API |
| `GET /v1/models` | List available models |
| `GET /cvc/tools` | Get CVC function-calling tool definitions |
| `GET /cvc/sessions` | View Time Machine session history |

### Auth Pass-Through

When tools like Claude Code or Codex CLI send their own API key in the request, CVC **forwards it to the upstream provider**. You don't need to store API keys in CVC for these tools — they handle auth themselves.

---

## MCP Server

CVC implements the **Model Context Protocol (MCP)**, allowing authentication-based IDEs to use CVC's cognitive versioning without API endpoint redirection.

### Transports

| Transport | Command | Use Case |
|---|---|---|
| **stdio** | `cvc mcp` | IDE launches CVC as a subprocess (default, most common) |
| **SSE** | `cvc mcp --transport sse` | HTTP Server-Sent Events on `localhost:8001` |

```bash
cvc mcp                            # stdio transport (default)
cvc mcp --transport sse            # HTTP/SSE transport
cvc mcp --transport sse --port 8001  # Custom SSE port
```

### MCP Tools Exposed

When connected via MCP, the following CVC tools are available to the IDE's agent:

- `cvc_commit` — Save a cognitive checkpoint
- `cvc_branch` — Create a new exploration branch
- `cvc_merge` — Merge branches
- `cvc_restore` — Time-travel to a previous state
- `cvc_status` — Show current branch/HEAD/context
- `cvc_log` — View commit history

### IDE Configuration Examples

**VS Code** (`.vscode/mcp.json`):
```json
{
  "mcp": {
    "servers": {
      "cvc": {
        "command": "cvc",
        "args": ["mcp"]
      }
    }
  }
}
```

**Antigravity:**
1. Click `⋯` in the agent panel → **Manage MCP Servers**
2. Click **View raw config**
3. Add:
```json
{
  "mcpServers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"]
    }
  }
}
```

**Windsurf:**
1. Open Windsurf → click `⋯` in Cascade panel
2. Go to **MCP Settings** → **Configure**
3. Add the CVC MCP server (same JSON as Antigravity above)

**Cursor:**
Settings → MCP Servers → Add:
```json
{
  "cvc": {
    "command": "cvc",
    "args": ["mcp"]
  }
}
```

---

## Time Machine Mode

### How Time Machine Works

Time Machine is CVC's automatic checkpointing system. Every N assistant turns, CVC automatically creates a cognitive commit — a snapshot of the conversation state.

| Feature | Description |
|---|---|
| **Auto-commit** | Every 5 assistant turns (agent) or 3 turns (proxy), configurable |
| **Session tracking** | Detects which tool is connected, tracks start/end, message counts |
| **Smart messages** | Auto-commits include turn number and conversation summary |
| **Zero friction** | Just `cvc` and go — or `cvc launch claude` for external tools |
| **Session persistence** | Context restored from CVC on next launch |

### Configuration

```bash
# Agent auto-commit interval
CVC_AGENT_AUTO_COMMIT=3 cvc agent        # Commit every 3 turns

# Proxy auto-commit interval
CVC_TIME_MACHINE_INTERVAL=5 cvc up       # Commit every 5 turns

# Disable Time Machine for external tools
cvc launch claude --no-time-machine
```

### Session Tracking

View session history (requires the proxy to be running):

```bash
cvc sessions
```

This shows all agent sessions tracked by the CVC proxy, including which tool was used, message counts, and auto-commit stats.

### Supported External Tools

| Tool | Launch Command | How It Connects |
|---|---|---|
| Claude Code CLI | `cvc launch claude` | Sets `ANTHROPIC_BASE_URL` → native `/v1/messages` |
| Aider | `cvc launch aider` | Sets `OPENAI_API_BASE` + model flag |
| OpenAI Codex CLI | `cvc launch codex` | Sets `OPENAI_API_BASE` |
| Gemini CLI | `cvc launch gemini` | Sets `GEMINI_API_BASE_URL` |
| Kiro CLI | `cvc launch kiro` | Sets `OPENAI_API_BASE` |
| Cursor | `cvc launch cursor` | Writes `.cursor/mcp.json` + opens IDE |
| VS Code | `cvc launch code` | Writes `.vscode/mcp.json` + configures BYOK |
| Windsurf | `cvc launch windsurf` | Writes MCP config + opens IDE |

---

## Git Integration

CVC doesn't replace Git — it **bridges** with it.

### Shadow Branches

CVC state lives on shadow branches (e.g., `cvc/main`), keeping your main Git branch clean. The cognitive data never pollutes your source code history.

### Git Notes

Every `git commit` is annotated with the corresponding CVC hash. This answers the question: *"What was the AI thinking when it wrote this code?"*

### Hooks

CVC installs two Git hooks for seamless integration:

| Hook | What It Does |
|---|---|
| `post-commit` | Auto-captures CVC cognitive state after every `git commit` |
| `post-checkout` | Auto-restores the agent's context when you `git checkout` an old commit |

```bash
cvc install-hooks          # Install the hooks
cvc capture-snapshot       # Manually link current Git commit to CVC state
```

When you check out an old version of your code, CVC automatically restores the agent's context to what it was when that code was written — **true cognitive time-travel**.

---

## Supported Providers

CVC supports **four LLM providers** out of the box, with provider-specific prompt caching optimisations.

### Anthropic

| Model | Description | Tier |
|---|---|---|
| `claude-opus-4-6` | Most intelligent — agents & coding | $5/$25 per MTok |
| `claude-opus-4-5` | Previous flagship — excellent reasoning | $5/$25 per MTok |
| `claude-sonnet-4-5` | Best speed / intelligence balance | $3/$15 per MTok |
| `claude-haiku-4-5` | Fastest & cheapest | $1/$5 per MTok |

**Caching:** Uses Anthropic's native `cache_control` for prompt caching.

```bash
pip install "tm-ai[anthropic]"
export ANTHROPIC_API_KEY="sk-ant-..."
cvc agent --provider anthropic
```

### OpenAI

| Model | Description | Tier |
|---|---|---|
| `gpt-5.2` | Best for coding & agentic tasks | Frontier |
| `gpt-5.2-codex` | Optimized for agentic coding | Frontier |
| `gpt-5-mini` | Fast & cost-efficient | Mid-tier |
| `gpt-4.1` | Smartest non-reasoning model | Mid-tier |

**Caching:** Automatic prefix caching.

```bash
pip install "tm-ai[openai]"
export OPENAI_API_KEY="sk-..."
cvc agent --provider openai
```

### Google (Gemini)

| Model | Description | Tier |
|---|---|---|
| `gemini-3-pro-preview` | Newest multimodal & agentic | Premium |
| `gemini-3-flash-preview` | Fast Gemini 3 | Standard |
| `gemini-2.5-pro` | Advanced thinking model (GA) | Premium |
| `gemini-2.5-flash` | Best price-performance (GA) | Standard |

**Caching:** Multimodal agent with native thought reasoning.

```bash
pip install "tm-ai[google]"
export GOOGLE_API_KEY="AIza..."
cvc agent --provider google
```

### Ollama (Local)

| Model | Description | Size |
|---|---|---|
| `qwen2.5-coder:7b` | Best coding model — 11M+ pulls | ~4 GB |
| `qwen3-coder:30b` | Latest agentic coding model | ~18 GB |
| `devstral:24b` | Mistral's best open-source coding agent | ~14 GB |
| `deepseek-r1:8b` | Open reasoning model (chain-of-thought) | ~5 GB |

**100% local** — no API key needed, no data leaves your machine.

```bash
ollama serve
ollama pull qwen2.5-coder:7b
cvc agent --provider ollama
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CVC_AGENT_ID` | `sofia` | Agent identifier |
| `CVC_DEFAULT_BRANCH` | `main` | Default branch name |
| `CVC_ANCHOR_INTERVAL` | `10` | Full snapshot every N commits (others are delta-compressed) |
| `CVC_PROVIDER` | `anthropic` | LLM provider |
| `CVC_MODEL` | *auto* | Model name (auto-detected per provider) |
| `CVC_AGENT_AUTO_COMMIT` | `5` | Agent auto-checkpoint interval (assistant turns) |
| `CVC_TIME_MACHINE_INTERVAL` | `3` | Proxy auto-commit interval (assistant turns) |
| `CVC_HOST` | `127.0.0.1` | Proxy host |
| `CVC_PORT` | `8000` | Proxy port |
| `CVC_VECTOR_ENABLED` | `false` | Enable semantic search (requires Chroma) |
| `ANTHROPIC_API_KEY` | — | Required for `anthropic` provider |
| `OPENAI_API_KEY` | — | Required for `openai` provider |
| `GOOGLE_API_KEY` | — | Required for `google` provider |

### Global Config

CVC stores global configuration in a platform-appropriate location:

| OS | Path |
|---|---|
| Windows | `%LOCALAPPDATA%\cvc\config.json` |
| macOS | `~/Library/Application Support/cvc/config.json` |
| Linux | `~/.config/cvc/config.json` |

The global config stores:
- Selected provider
- Selected model
- API keys (per provider)

Manage with: `cvc setup`

### Project Config

Project-level data is stored in `.cvc/` inside your project directory:

```
.cvc/
├── cvc.db         # SQLite database (commit graph, branch pointers, metadata)
├── objects/       # CAS blobs (Zstandard-compressed context snapshots)
└── chroma/        # Semantic embeddings (optional, if vector search enabled)
```

Initialise with: `cvc init`

---

## Architecture

### System Overview

CVC operates as either a **standalone agent** or a **proxy middleware**:

```
┌─────────────────────────────────────────────────────────┐
│                    YOUR MACHINE                          │
│                                                          │
│   ┌──────────────────────┐   ┌────────────────────────┐ │
│   │    CVC Agent (cvc)    │   │  CVC Proxy (:8000)     │ │
│   │  17 tools · 4 provs   │   │  LangGraph Router      │ │
│   │  Terminal REPL         │   │  ├→ Cognitive Engine   │ │
│   │                        │   │  └→ Forward to LLM    │ │
│   └──────────┬─────────────┘   └──────────┬─────────────┘ │
│              │                             │              │
│              ▼                             ▼              │
│   ┌──────────────────────────────────────────────────────┐ │
│   │              .cvc/ Storage                            │ │
│   │  🗄️ SQLite  │  📦 CAS Blobs  │  🔍 Chroma (opt)     │ │
│   └──────────────────────────────────────────────────────┘ │
│              │                             │              │
└──────────────┼─────────────────────────────┼──────────────┘
               ▼                             ▼
       ☁️ LLM Provider (Claude / GPT / Gemini / Ollama)
```

### Three-Tiered Storage

All data is stored locally in `.cvc/`:

| Tier | What | Why |
|---|---|---|
| **SQLite** | Commit graph, branch pointers, metadata | Fast traversal, zero-config, works everywhere |
| **CAS Blobs** | Compressed context snapshots (Zstandard) | Content-addressable, deduplicated, efficient |
| **Chroma** | Semantic embeddings *(optional)* | "Have I solved this before?" — search by meaning |

### Directory Structure

```
cvc/
├── __init__.py            # Package root, version
├── __main__.py            # python -m cvc entry point
├── cli.py                 # Click CLI — all commands, setup wizard
├── proxy.py               # FastAPI proxy — intercepts LLM API calls
├── launcher.py            # Zero-config auto-launch for AI tools
├── mcp_server.py          # Model Context Protocol server
│
├── agent/                 # Built-in AI coding agent
│   ├── __init__.py        # Exports run_agent()
│   ├── chat.py            # AgentSession REPL loop, slash commands, auto-commit
│   ├── llm.py             # Unified LLM client — tool calling for all 4 providers
│   ├── tools.py           # 17 tool definitions in OpenAI function-calling schema
│   ├── executor.py        # Tool execution engine — file ops, shell, CVC operations
│   ├── system_prompt.py   # Dynamic system prompt builder
│   ├── renderer.py        # Rich terminal rendering
│   ├── cost_tracker.py    # Token usage and cost tracking
│   ├── memory.py          # Agent memory management
│   ├── auto_context.py    # Automatic context management
│   ├── git_integration.py # Git-aware context for the agent
│   └── web_search.py      # Web search functionality
│
├── adapters/              # Provider-specific prompt formatting
│   ├── base.py            # Abstract BaseAdapter
│   ├── anthropic.py       # Anthropic adapter (prompt caching)
│   ├── openai.py          # OpenAI adapter
│   ├── google.py          # Google adapter
│   └── ollama.py          # Ollama adapter
│
├── core/                  # Data layer
│   ├── models.py          # Pydantic schemas, config, Merkle DAG
│   └── database.py        # SQLite + CAS + Chroma storage
│
├── operations/            # CVC engine
│   ├── engine.py          # Commit, branch, merge, restore
│   └── state_machine.py   # LangGraph command routing
│
└── vcs/                   # Git bridge
    └── bridge.py          # Shadow branches, Git notes, hooks
```

---

## Troubleshooting

### Common Issues

**"No provider configured"**
Run `cvc setup` to configure your LLM provider and API key.

**"No API key for <provider>"**
Either set the environment variable (e.g., `ANTHROPIC_API_KEY`), run `cvc setup` to save a key, or pass `--api-key` directly.

**"CVC proxy is not running"**
Start the proxy with `cvc serve` or `cvc up` before using `cvc sessions` or connecting external tools.

**"Not a Git repo"**
Some features (Git hooks, shadow branches, capture-snapshot) require a Git repository. Run `git init` first.

**Ollama not responding**
Make sure `ollama serve` is running and you've pulled a model: `ollama pull qwen2.5-coder:7b`.

### Diagnostics

Run the built-in health check:

```bash
cvc doctor
```

This verifies:
- Python version (3.11+ required)
- Global configuration
- Project `.cvc/` directory
- Git repository presence
- API keys for all providers
- Ollama connectivity

### Getting Help

```bash
cvc --help                 # Show all commands
cvc <command> --help       # Show help for a specific command
cvc connect                # Interactive tool connection wizard
```

---

## Contributing

This project is open source and welcomes contributions.

### Dev Setup

```bash
git clone https://github.com/mannuking/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control
uv sync --extra dev       # or: pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Areas Where Help Is Needed

| Area | Difficulty |
|---|---|
| Additional Provider Adapters (Mistral, Cohere, etc.) | Medium |
| Tests & edge cases | Easy–Medium |
| VS Code Extension (commit graph visualisation) | Hard |
| Metrics & observability dashboard | Medium |
| Security audit | Medium–Hard |

### Workflow

**Fork** → **Branch** → **Commit** → **Push** → **PR**

---

## License

**MIT** — see [LICENSE](LICENSE).

---

> **CVC — Because AI agents deserve an undo button.**
>
> [GitHub Repository](https://github.com/mannuking/AI-Cognitive-Version-Control) · [PyPI Package](https://pypi.org/project/tm-ai/) · [Report Issues](https://github.com/mannuking/AI-Cognitive-Version-Control/issues)
