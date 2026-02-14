# Cognitive Version Control (CVC) — Documentation

> **The Time Machine for AI Agents.** Save, branch, rewind, and merge your AI agent's cognitive state — no matter what tool you use.

---

## Table of Contents

- [Why a Time Machine?](#why-a-time-machine)
  - [The Problem with AI Agents Today](#the-problem-with-ai-agents-today)
  - [What the Time Machine Does](#what-the-time-machine-does)
  - [How It Works Under the Hood](#how-it-works-under-the-hood)
- [Use CVC with Your Existing AI Tools](#use-cvc-with-your-existing-ai-tools)
  - [Supported Tools at a Glance](#supported-tools-at-a-glance)
  - [Zero-Config Launch (Fastest Way)](#zero-config-launch-fastest-way)
  - [IDEs](#ides)
  - [CLI Agents](#cli-agents)
  - [Web UIs & Frameworks](#web-uis--frameworks)
- [Connection Methods](#connection-methods)
  - [Proxy Server (API-Based Tools)](#proxy-server-api-based-tools)
  - [MCP Server (Auth-Based IDEs)](#mcp-server-auth-based-ides)
  - [Auth Pass-Through](#auth-pass-through)
- [The CVC CLI](#the-cvc-cli)
  - [What Is the CVC CLI?](#what-is-the-cvc-cli)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [The Built-in Agent](#the-built-in-agent)
  - [Agent Tools (17 Built-in)](#agent-tools-17-built-in)
  - [Slash Commands](#slash-commands)
  - [Full Command Reference](#full-command-reference)
- [Time Machine In Depth](#time-machine-in-depth)
  - [Auto-Commit](#auto-commit)
  - [Session Tracking](#session-tracking)
  - [Branching & Merging](#branching--merging)
  - [Restoring (Time-Travel)](#restoring-time-travel)
- [Git Integration](#git-integration)
  - [Shadow Branches](#shadow-branches)
  - [Git Notes](#git-notes)
  - [Hooks](#hooks)
- [Supported Providers](#supported-providers)
- [Configuration Reference](#configuration-reference)
  - [Environment Variables](#environment-variables)
  - [Global Config](#global-config)
  - [Project Config](#project-config)
- [Architecture](#architecture)
  - [System Overview](#system-overview)
  - [Three-Tiered Storage](#three-tiered-storage)
  - [Source Directory Structure](#source-directory-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Why a Time Machine?

### The Problem with AI Agents Today

Every AI coding agent — Claude Code, Cursor, Aider, Codex, Copilot — shares the same fundamental flaw: **zero memory management**.

Your agent is brilliant for the first 20 minutes. Then:

- It **forgets** what it already fixed and re-introduces bugs.
- It **contradicts** its own plan from 10 messages ago.
- It hits an error, tries the same failing approach in a loop, and **never recovers**.
- It fills the context window with noise, and reasoning quality **falls off a cliff**.

The industry response has been to make context windows bigger — 4K → 32K → 128K → 1M+ tokens. But research shows that after ~60% context utilisation, LLM accuracy drops dramatically. One hallucination poisons everything that follows. Error cascades compound.

**A bigger window doesn't fix context rot. It just gives it more room to spread.**

The real issue is that AI agents have no ability to manage their own cognitive state. They can't save their work. They can't explore safely. They can't undo mistakes. They are solving a 500-piece puzzle while someone keeps removing pieces from the table.

### What the Time Machine Does

CVC gives every AI agent an **undo button** — and much more. Think of it as Git, but instead of versioning source code, it versions the agent's *entire context*: every thought, every decision, every conversation turn.

| Capability | What It Means |
|---|---|
| **Save** | Checkpoint the agent's brain at any stable moment. If something breaks later, you can come back here. |
| **Branch** | Explore a risky approach in isolation. The main conversation stays untouched. If the experiment fails, just discard the branch. |
| **Rewind** | Stuck in a loop? Time-travel back to the last good state instantly. The agent picks up right where things were working. |
| **Merge** | Tried two different approaches on two branches? Merge the *learnings* — not the raw logs — back into your main context. Semantic, not syntactic. |
| **Search** | "Have I solved this before?" Search across all commits by meaning, not just keywords. |

This works **automatically**. Every few assistant turns, CVC silently creates a checkpoint. You never have to think about it — but when you need to go back, the history is there.

### How It Works Under the Hood

CVC stores every checkpoint as an immutable node in a cryptographic **Merkle DAG** — the same data structure behind Git and blockchain. Each commit is content-addressed (its hash *is* its content), deduplicated, and delta-compressed using Zstandard.

The result:

| Metric | Without CVC | With CVC |
|---|---|---|
| **Cost per restore** | Full price (reprocess everything) | **~90% cheaper** (cached prefix) |
| **Latency per restore** | Full processing time | **~85% faster** |
| **Checkpoint frequency** | Impractical (too expensive) | **Economically viable** |
| **Context reduction** | None | **Up to 58%** via branching |
| **Recovery from loops** | Manual or impossible | **3.5x higher success rate** |

All data stays **local** — inside a `.cvc/` directory in your project. No cloud. No telemetry. Your agent's thoughts are yours.

---

## Use CVC with Your Existing AI Tools

CVC is not a replacement for your AI tool — it's a **layer underneath it**. You keep using Claude Code, Cursor, Aider, VS Code Copilot, or whatever you prefer. CVC sits between your tool and the LLM provider, silently versioning every conversation.

### Supported Tools at a Glance

| Category | Tool | Connection Method |
|---|---|---|
| **IDEs** | VS Code + Copilot | BYOK / MCP / Extensions |
| | Cursor | API Override / MCP |
| | Windsurf | MCP |
| | Antigravity (Google) | MCP |
| | Firebase Studio | Extensions |
| **CLI Agents** | Claude Code CLI | Proxy (native Anthropic API) |
| | OpenAI Codex CLI | Proxy / Config file |
| | Aider | Proxy (env vars) |
| | Gemini CLI | Proxy (env vars) |
| | Kiro CLI (Amazon) | Proxy (env vars) |
| **Web UIs** | Open WebUI | Proxy (connection settings) |
| **Frameworks** | LangChain / CrewAI / AutoGen | Proxy + function-calling tools |
| **Extensions** | Continue.dev / Cline / Roo | Proxy (base URL + API key) |

### Zero-Config Launch (Fastest Way)

The **fastest way** to use CVC with any tool is `cvc launch`. One command — CVC handles setup, initialisation, proxy start, environment configuration, and tool launch automatically:

```bash
cvc launch claude          # Launch Claude Code CLI through CVC
cvc launch aider           # Launch Aider through CVC
cvc launch codex           # Launch OpenAI Codex CLI through CVC
cvc launch gemini          # Launch Gemini CLI through CVC
cvc launch kiro            # Launch Kiro CLI through CVC
cvc launch cursor          # Open Cursor with CVC auto-configured
cvc launch code            # Open VS Code with Copilot BYOK configured
cvc launch windsurf        # Open Windsurf with MCP configured
```

What happens behind the scenes:

1. Runs setup if it's your first time (provider, model, API key)
2. Initialises `.cvc/` in the current project if needed
3. Starts the proxy server in the background
4. Configures the tool's environment variables or config files
5. Launches the tool — every conversation is automatically time-machined

```bash
cvc launch                             # Interactive tool picker (shows all options)
cvc launch claude --no-time-machine    # Disable auto-commit
cvc launch aider --port 9000           # Use a custom proxy port
```

### IDEs

#### VS Code + GitHub Copilot

VS Code supports **three ways** to connect:

**Option 1 — Copilot BYOK (Bring Your Own Key):**

1. Press `Ctrl+Shift+P` → **Chat: Manage Language Models**
2. Select **OpenAI Compatible** as provider
3. Base URL → `http://127.0.0.1:8000/v1`
4. API Key → `cvc` (any non-empty string)
5. Select your model

> BYOK is available on Copilot Individual plans (Free, Pro, Pro+). Not available on Business/Enterprise.

**Option 2 — MCP Server (works with native Copilot):**

Add to `.vscode/mcp.json`:
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

CVC tools (commit, branch, merge, restore, status, log) become available inside Copilot agent mode.

**Option 3 — VS Code Extensions (Continue.dev / Cline):**

Install from the Marketplace, then configure:
- Base URL → `http://127.0.0.1:8000/v1`
- API Key → `cvc`

#### Cursor

1. Open Cursor → Settings (⚙️) → **Models**
2. Click **Add OpenAI API Key** → paste `cvc`
3. Enable **Override OpenAI Base URL** → `http://127.0.0.1:8000/v1`
4. Select your model and start coding

**Alternative — MCP:**
Settings → MCP Servers → Add:
```json
{
  "cvc": {
    "command": "cvc",
    "args": ["mcp"]
  }
}
```

#### Windsurf

Windsurf uses account-based authentication — you cannot override the API endpoint directly. Use MCP:

1. Open Windsurf → click `⋯` in Cascade panel
2. Go to **MCP Settings** → **Configure**
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

#### Antigravity (Google)

Antigravity uses Google account authentication. Use MCP:

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

**Alternative:** Install Continue.dev from Open VSX and configure with the proxy endpoint.

#### Firebase Studio

Firebase Studio is Google's cloud IDE built on Code OSS. It supports Open VSX extensions:

1. Start CVC with `--host 0.0.0.0` (or use a tunnel)
2. Install **Continue.dev** or **Cline** from Open VSX
3. Configure: Base URL → `http://127.0.0.1:8000/v1`, API Key → `cvc`

### CLI Agents

#### Claude Code CLI

CVC serves the native Anthropic Messages API at `/v1/messages`, so Claude Code works without any format translation.

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

Or add permanently to `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8000"
  }
}
```

> **Auth pass-through:** Your `ANTHROPIC_API_KEY` is forwarded to Anthropic automatically. No need to store it in CVC.

#### OpenAI Codex CLI

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

#### Aider

**Linux / macOS:**
```bash
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=cvc
aider --model openai/<your-model>
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "cvc"
aider --model openai/<your-model>
```

#### Gemini CLI

**Linux / macOS:**
```bash
export GEMINI_API_BASE_URL="http://127.0.0.1:8000/v1"
export GEMINI_API_KEY="your-key"
gemini
```

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_BASE_URL = "http://127.0.0.1:8000/v1"
$env:GEMINI_API_KEY = "your-key"
gemini
```

#### Kiro CLI (Amazon)

**Linux / macOS:**
```bash
export OPENAI_API_BASE="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="cvc"
kiro
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "cvc"
kiro
```

### Web UIs & Frameworks

#### Open WebUI

1. Open WebUI → **Settings → Connections**
2. Click **+ Add Connection**
3. URL → `http://127.0.0.1:8000/v1`
4. API Key → `cvc` (any non-empty string)
5. Save — the CVC model appears in the model dropdown

#### Continue.dev / Cline / Roo

These VS Code extensions work with any OpenAI-compatible endpoint:

- Base URL → `http://127.0.0.1:8000/v1`
- API Key → `cvc`
- Model → your configured model name

#### LangChain / CrewAI / AutoGen

Use CVC's function-calling tool definitions:

```
GET http://127.0.0.1:8000/cvc/tools
```

Point your framework's LLM client at the CVC proxy endpoint as a standard OpenAI-compatible API.

---

## Connection Methods

CVC connects to your AI tools through two server modes, depending on how the tool handles authentication.

### Proxy Server (API-Based Tools)

The CVC **Cognitive Proxy** is a FastAPI server that exposes both OpenAI-compatible and Anthropic-native APIs. It sits between your tool and the LLM provider, intercepting every conversation for cognitive versioning.

**Start the proxy:**

```bash
cvc serve                          # Start on 127.0.0.1:8000 (default)
cvc serve --host 0.0.0.0          # Bind to all interfaces
cvc serve --port 9000             # Custom port
cvc serve --reload                # Auto-reload for development
```

**Exposed endpoints:**

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible chat completions |
| `POST /v1/messages` | Anthropic-native Messages API |
| `GET /v1/models` | List available models |
| `GET /cvc/tools` | CVC function-calling tool definitions |
| `GET /cvc/sessions` | Time Machine session history |
| `GET /` | Health check |

**Universal connection info for any OpenAI-compatible tool:**

| Setting | Value |
|---|---|
| Base URL | `http://127.0.0.1:8000/v1` |
| API Key | `cvc` (any non-empty string) |
| Model | Your configured model name |

Run `cvc connect` for an interactive wizard that shows tool-specific setup instructions, or `cvc connect <tool>` for a specific tool (e.g., `cvc connect cursor`).

### MCP Server (Auth-Based IDEs)

For IDEs that use login-based authentication (GitHub Login, Google Login, account auth) and cannot redirect API endpoints, CVC runs as a **Model Context Protocol (MCP)** server.

**Transports:**

| Transport | Command | Use Case |
|---|---|---|
| **stdio** | `cvc mcp` | IDE launches CVC as a subprocess (default, most common) |
| **SSE** | `cvc mcp --transport sse` | HTTP Server-Sent Events on `localhost:8001` |

```bash
cvc mcp                                # stdio (default)
cvc mcp --transport sse                # HTTP/SSE
cvc mcp --transport sse --port 8001    # Custom SSE port
```

**MCP tools available to the IDE's agent:**

| Tool | Description |
|---|---|
| `cvc_commit` | Save a cognitive checkpoint |
| `cvc_branch` | Create a new exploration branch |
| `cvc_merge` | Merge branches |
| `cvc_restore` | Time-travel to a previous state |
| `cvc_status` | Show current branch/HEAD/context |
| `cvc_log` | View commit history |

**IDE configuration:**

VS Code (`.vscode/mcp.json` or `settings.json`):
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

Antigravity / Windsurf / Cursor (MCP config):
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

### Auth Pass-Through

When tools like Claude Code or Codex CLI send their own API key in the request, CVC **forwards it directly to the upstream provider**. You don't need to store API keys in CVC for these tools — they handle auth themselves. CVC only intercepts the conversation for versioning; the credentials flow through untouched.

---

## The CVC CLI

### What Is the CVC CLI?

Everything described above — the Time Machine, the proxy server, the MCP server, the zero-config launcher, the tool connections — is bundled into a **single Python CLI** called `cvc`.

It is a comprehensive command-line tool that integrates:

- A **full agentic coding assistant** (built-in terminal agent with 17 tools and 4 provider backends)
- A **transparent proxy server** (OpenAI + Anthropic API compatible)
- An **MCP server** (for auth-based IDEs)
- A **zero-config launcher** (auto-launch any AI tool through CVC)
- A **Time Machine engine** (commit, branch, merge, restore, search)
- A **Git bridge** (shadow branches, notes, auto-hooks)
- An **interactive setup wizard** (IDE detection, auto-configuration)

One `pip install`, one command, and you have all of it.

### Installation

CVC is published on [PyPI](https://pypi.org/project/tm-ai/) as **`tm-ai`**.

```bash
pip install tm-ai
```

The `cvc` command is now available globally.

#### More Install Options

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

# For contributors / local development
git clone https://github.com/mannuking/AI-Cognitive-Version-Control.git
cd AI-Cognitive-Version-Control
uv sync --extra dev           # or: pip install -e ".[dev]"
```

**Prerequisites:** Python 3.11+ and Git (optional, for VCS bridge features).

**Core dependencies** (installed automatically): `fastapi`, `uvicorn`, `httpx`, `pydantic`, `click`, `rich`, `zstandard`, `aiosqlite`, `GitPython`, `langgraph`, `langchain-core`, `prompt_toolkit`.

**Optional dependencies:** `anthropic`, `openai`, `google-genai`, `chromadb`, `sentence-transformers`.

### Quick Start

**Just type `cvc`:**

```bash
cvc
```

If it's your first time, CVC runs the setup wizard (pick your provider, model, API key), then drops you straight into the built-in agent.

**Or step by step:**

```bash
cvc setup              # Interactive wizard: provider, model, API key
cvc init               # Initialise .cvc/ in your project
cvc serve              # Start the proxy for external AI tools
```

**Or all-in-one:**

```bash
cvc up                 # setup + init + serve in one command
```

#### Setting Your API Key

Three ways:

1. **`cvc setup`** — The wizard prompts and saves the key securely on your machine.
2. **Environment variables:**

   ```bash
   # Bash / Linux / macOS
   export ANTHROPIC_API_KEY="sk-ant-..."     # Anthropic
   export OPENAI_API_KEY="sk-..."            # OpenAI
   export GOOGLE_API_KEY="AIza..."           # Google

   # PowerShell (Windows)
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   $env:OPENAI_API_KEY = "sk-..."
   $env:GOOGLE_API_KEY = "AIza..."
   ```

3. **`--api-key` flag** — Pass directly: `cvc agent --api-key sk-ant-...`

Ollama requires no API key (runs locally).

| Provider | Get Your Key |
|---|---|
| Anthropic | https://console.anthropic.com/settings/keys |
| OpenAI | https://platform.openai.com/api-keys |
| Google | https://aistudio.google.com/apikey |
| Ollama | No key needed — [ollama.com](https://ollama.com) |

### The Built-in Agent

CVC ships with a **full agentic coding assistant** in your terminal. It has 17 tools, supports 4 LLM providers, and comes with Time Machine built in — every conversation is automatically checkpointed, branchable, and searchable.

```bash
cvc                                     # Launch the agent
cvc agent                               # Same thing (explicit subcommand)
cvc agent --provider anthropic          # Force a provider
cvc agent --provider openai
cvc agent --provider google
cvc agent --provider ollama
cvc agent --model claude-sonnet-4-5     # Override the model
cvc agent --api-key sk-ant-...          # Pass API key directly
```

What makes it different from other terminal agents:

| Other Agents | CVC Agent |
|---|---|
| No memory across sessions | **Time-travel** to any previous point |
| Linear session history | **Branch** conversations into parallel explorations |
| Context lost on crash | **Auto-checkpoint** every 5 turns |
| Can't search past conversations | **Search** across all history by meaning |
| Single provider only | **4 providers** supported (switch mid-conversation) |
| No rollback | **Undo** file edits, **restore** conversation states |

### Agent Tools (17 Built-in)

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

While chatting with the agent, use these for quick actions:

| Command | Description |
|---|---|
| `/help` | Show all available slash commands |
| `/status` | View branch, HEAD, context size, provider & model |
| `/log` | Show last 20 conversation checkpoints |
| `/commit <msg>` | Save a manual checkpoint |
| `/branch <name>` | Create and switch to a new branch |
| `/restore <hash>` | Time-travel back to a checkpoint |
| `/search <query>` | Search all commits for a topic |
| `/undo` | Undo the last file modification (edit/write/patch) |
| `/web <query>` | Search the web for docs or solutions |
| `/image <path>` | Analyse an image file (for UI bugs/mocks) |
| `/paste` | Analyse an image from clipboard (screenshots) |
| `/git <cmd>` | Run git commands with context awareness |
| `/cost` | Show session token usage and cost |
| `/compact` | Compress conversation history, keeping recent context |
| `/clear` | Clear conversation history (CVC state preserved) |
| `/model <name>` | Switch LLM model mid-conversation |
| `/exit` | Save final checkpoint and exit cleanly |

### Full Command Reference

#### Agent

| Command | Description |
|---|---|
| `cvc` | Launch the CVC Agent (runs setup on first use) |
| `cvc agent` | Same as above (explicit subcommand) |
| `cvc agent --provider <p>` | Agent with a specific provider (`anthropic`, `openai`, `google`, `ollama`) |
| `cvc agent --model <m>` | Agent with a model override |
| `cvc agent --api-key <k>` | Agent with a direct API key |

#### Launch External Tools

| Command | Description |
|---|---|
| `cvc launch <tool>` | Zero-config auto-launch any AI tool through CVC |
| `cvc launch` | Interactive tool picker |
| `cvc up` | One-command start: setup + init + serve proxy |
| `cvc up --host <h> --port <p>` | Customise proxy bind address |
| `cvc up --no-time-machine` | Disable auto-commit |

#### Setup & Configuration

| Command | Description |
|---|---|
| `cvc setup` | Interactive setup wizard (provider, model, API key, IDE detection) |
| `cvc setup --provider <p>` | Non-interactive provider selection |
| `cvc setup --model <m>` | Non-interactive model selection |
| `cvc setup --api-key <k>` | Non-interactive API key |
| `cvc init` | Initialise `.cvc/` in the current project |
| `cvc init --path <dir>` | Initialise in a specific directory |
| `cvc connect` | Interactive tool connection wizard |
| `cvc connect <tool>` | Show setup for a specific tool (e.g., `cvc connect cursor`) |
| `cvc connect --all` | Show setup instructions for all tools |

When `cvc setup` detects an existing configuration, it offers five options:

1. **Start Fresh** — Reconfigure everything
2. **Change Provider** — Switch LLM provider
3. **Change Model** — Keep provider, pick a different model
4. **Update API Key** — Replace or add a key
5. **Reset Everything** — Delete all config and start over

#### Proxy & MCP Servers

| Command | Description |
|---|---|
| `cvc serve` | Start the Cognitive Proxy on `127.0.0.1:8000` |
| `cvc serve --host <h>` | Bind to a specific host |
| `cvc serve --port <p>` | Bind to a specific port |
| `cvc serve --reload` | Enable auto-reload (development) |
| `cvc mcp` | Start MCP server (stdio transport) |
| `cvc mcp --transport sse` | Start MCP server (HTTP/SSE transport) |
| `cvc mcp --host <h> --port <p>` | Customise SSE bind address |

#### Time Machine

| Command | Description |
|---|---|
| `cvc status` | Show branch, HEAD, context size, provider, all branches |
| `cvc log` | View commit history (default: last 20) |
| `cvc log -n <N>` | Show last N commits |
| `cvc commit -m "message"` | Create a cognitive checkpoint |
| `cvc commit -m "msg" -t analysis` | Commit with type (`checkpoint`, `analysis`, `generation`) |
| `cvc commit -m "msg" --tag <t>` | Add tags (repeatable) |
| `cvc branch <name>` | Create and switch to a new branch |
| `cvc branch <name> -d "desc"` | Create with a description |
| `cvc merge <source>` | Merge source branch into active branch |
| `cvc merge <source> --target <branch>` | Merge into a specific target (default: `main`) |
| `cvc restore <hash>` | Time-travel to a previous commit |
| `cvc sessions` | View session history (requires proxy running) |

#### Utilities

| Command | Description |
|---|---|
| `cvc install-hooks` | Install Git ↔ CVC sync hooks (`post-commit`, `post-checkout`) |
| `cvc capture-snapshot` | Link current Git commit to CVC state |
| `cvc capture-snapshot --git-sha <sha>` | Link to a specific Git SHA |
| `cvc doctor` | Health check (Python, config, .cvc/, Git, API keys, Ollama) |
| `cvc --version` | Show installed version |
| `cvc -v <command>` | Run with verbose/debug logging |

---

## Time Machine In Depth

### Auto-Commit

The Time Machine **automatically creates checkpoints** at regular intervals — you never need to think about saving.

| Mode | Default Interval | Environment Variable |
|---|---|---|
| Built-in Agent | Every 5 assistant turns | `CVC_AGENT_AUTO_COMMIT` |
| Proxy (external tools) | Every 3 assistant turns | `CVC_TIME_MACHINE_INTERVAL` |

```bash
CVC_AGENT_AUTO_COMMIT=3 cvc agent          # Commit every 3 turns
CVC_TIME_MACHINE_INTERVAL=5 cvc up         # Proxy: every 5 turns
cvc launch claude --no-time-machine        # Disable entirely
```

When you exit the agent with `/exit`, a final checkpoint is always saved.

### Session Tracking

CVC tracks every agent session — which tool was used, when it started, how many messages were exchanged, and how many auto-commits were made.

```bash
cvc sessions           # View session history (proxy must be running)
```

### Branching & Merging

Branches let the agent explore alternative approaches without polluting the main conversation:

```bash
cvc branch experiment          # Create and switch to "experiment"
# ... try a risky approach ...
cvc commit -m "tried approach A"

# If it worked:
cvc merge experiment           # Merge insights back into main

# If it didn't:
cvc restore <hash>             # Just go back to before the branch
```

Merging is **semantic** — CVC extracts the learnings from the branch, not the raw logs. The result is a clean context that incorporates what was discovered.

### Restoring (Time-Travel)

Restore rewinds the agent's entire context to a previous checkpoint:

```bash
cvc log                        # Find the commit hash you want
cvc restore abc123def456       # Time-travel to that state
```

Both full and short (12-character) hashes work. After a restore, the agent picks up exactly where it was at that checkpoint — same conversation, same reasoning, same context.

Because CVC structures prompts so that committed history becomes a **cacheable prefix**, restoring is ~90% cheaper and ~85% faster than reprocessing the entire conversation from scratch.

---

## Git Integration

CVC doesn't replace Git — it **bridges** with it. Your source code stays in Git. Your AI's cognitive state stays in CVC. They're linked together.

### Shadow Branches

CVC state lives on its own Git branches (e.g., `cvc/main`), keeping your main branch clean. The cognitive data never pollutes your source code history.

### Git Notes

Every `git commit` is annotated with the corresponding CVC hash. This answers the question: *"What was the AI thinking when it wrote this code?"*

### Hooks

CVC installs two Git hooks:

| Hook | What It Does |
|---|---|
| `post-commit` | Auto-captures CVC state after every `git commit` |
| `post-checkout` | Auto-restores the agent's context when you `git checkout` an old commit |

```bash
cvc install-hooks          # Install the hooks
cvc capture-snapshot       # Manually link current Git commit to CVC state
```

When you check out an old version of your code, CVC **automatically restores** the agent's context to what it was when that code was written — true cognitive time-travel.

---

## Supported Providers

CVC supports **four LLM providers**, each with provider-specific prompt caching optimisations.

### Anthropic

| Model | Description | Tier |
|---|---|---|
| `claude-opus-4-6` | Most intelligent — agents & coding | $5/$25 per MTok |
| `claude-opus-4-5` | Previous flagship — excellent reasoning | $5/$25 per MTok |
| `claude-sonnet-4-5` | Best speed / intelligence balance | $3/$15 per MTok |
| `claude-haiku-4-5` | Fastest & cheapest | $1/$5 per MTok |

Caching: Anthropic's native `cache_control`.

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

Caching: Automatic prefix caching.

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

Caching: Multimodal with native thought reasoning.

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

100% local — no API key, no data leaves your machine.

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
| `CVC_AGENT_AUTO_COMMIT` | `5` | Agent auto-checkpoint interval (turns) |
| `CVC_TIME_MACHINE_INTERVAL` | `3` | Proxy auto-commit interval (turns) |
| `CVC_HOST` | `127.0.0.1` | Proxy host |
| `CVC_PORT` | `8000` | Proxy port |
| `CVC_VECTOR_ENABLED` | `false` | Enable semantic search (Chroma) |
| `ANTHROPIC_API_KEY` | — | Required for `anthropic` provider |
| `OPENAI_API_KEY` | — | Required for `openai` provider |
| `GOOGLE_API_KEY` | — | Required for `google` provider |

### Global Config

Stored in a platform-appropriate location:

| OS | Path |
|---|---|
| Windows | `%LOCALAPPDATA%\cvc\config.json` |
| macOS | `~/Library/Application Support/cvc/config.json` |
| Linux | `~/.config/cvc/config.json` |

Contains: selected provider, model, and API keys. Manage with `cvc setup`.

### Project Config

Stored in `.cvc/` inside your project:

```
.cvc/
├── cvc.db         # SQLite (commit graph, branches, metadata)
├── objects/       # CAS blobs (Zstandard-compressed snapshots)
└── chroma/        # Semantic embeddings (optional)
```

Initialise with `cvc init`.

---

## Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        YOUR MACHINE                          │
│                                                              │
│  ┌────────────────────┐      ┌─────────────────────────────┐ │
│  │   CVC Agent (cvc)  │      │   CVC Proxy (:8000)         │ │
│  │  17 tools           │      │   LangGraph Router          │ │
│  │  4 providers        │      │   ├→ Cognitive Engine       │ │
│  │  Terminal REPL      │      │   └→ Forward to LLM         │ │
│  └────────┬────────────┘      └──────────┬──────────────────┘ │
│           │                              │                    │
│           ▼                              ▼                    │
│  ┌────────────────────────────────────────────────────────┐   │
│  │                   .cvc/ Storage                        │   │
│  │  🗄️ SQLite  │  📦 CAS Blobs (Zstd)  │  🔍 Chroma     │   │
│  └────────────────────────────────────────────────────────┘   │
│           │                              │                    │
└───────────┼──────────────────────────────┼────────────────────┘
            ▼                              ▼
    ☁️ LLM Provider (Claude / GPT / Gemini / Ollama)
```

### Three-Tiered Storage

All data is local, inside `.cvc/`:

| Tier | What | Why |
|---|---|---|
| **SQLite** | Commit graph, branch pointers, metadata | Fast traversal, zero-config |
| **CAS Blobs** | Zstandard-compressed context snapshots | Content-addressable, deduplicated |
| **Chroma** | Semantic embeddings *(optional)* | Search by meaning across history |

### Source Directory Structure

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
│   ├── chat.py            # AgentSession REPL, slash commands, auto-commit
│   ├── llm.py             # Unified LLM client — tool calling, 4 providers
│   ├── tools.py           # 17 tool definitions (OpenAI function-calling schema)
│   ├── executor.py        # Tool execution — file ops, shell, CVC operations
│   ├── system_prompt.py   # Dynamic system prompt builder
│   ├── renderer.py        # Rich terminal rendering
│   ├── cost_tracker.py    # Token usage and cost tracking
│   ├── memory.py          # Agent memory management
│   ├── auto_context.py    # Automatic context management
│   ├── git_integration.py # Git-aware context
│   └── web_search.py      # Web search
│
├── adapters/              # Provider-specific prompt formatting
│   ├── base.py            # Abstract BaseAdapter
│   ├── anthropic.py       # Anthropic (prompt caching)
│   ├── openai.py          # OpenAI
│   ├── google.py          # Google Gemini
│   └── ollama.py          # Ollama (local)
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
→ Run `cvc setup` to configure your LLM provider and API key.

**"No API key for \<provider\>"**
→ Set the environment variable (e.g., `ANTHROPIC_API_KEY`), run `cvc setup`, or pass `--api-key`.

**"CVC proxy is not running"**
→ Start it with `cvc serve` or `cvc up` before using `cvc sessions` or connecting external tools.

**"Not a Git repo"**
→ Git hooks and shadow branches require a Git repository. Run `git init` first.

**Ollama not responding**
→ Ensure `ollama serve` is running and you've pulled a model: `ollama pull qwen2.5-coder:7b`.

### Diagnostics

```bash
cvc doctor             # Full health check
```

Verifies: Python version (3.11+), global config, `.cvc/` directory, Git, API keys, Ollama.

### Getting Help

```bash
cvc --help             # All commands
cvc <command> --help   # Help for a specific command
cvc connect            # Interactive tool connection wizard
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
