 # CVC — Complete Tools & Capabilities Reference

> **Cognitive Version Control v1.4.71** — Time Machine for AI Agents
>
> This document is the authoritative reference for every command, tool, and capability in CVC.
> Use it to update the marketing website documentation.

---

## At a Glance

| Surface | Count |
|---------|-------|
| CLI Commands | **34** (30 commands + 4 sync sub-actions) |
| MCP Tools (for IDEs) | **20** |
| Built-in Agent Tools | **17** |
| Provider Adapters | **4** (Anthropic, OpenAI, Google, Ollama) |
| Supported Models | **16** |
| IDE Connection Guides | **14** |
| **Total Capabilities** | **71** |

---

## 1. CLI Commands (34 entry points)

### Tier 0 — Zero-Config / Entry Points

| Command | Description |
|---------|-------------|
| `cvc` | Runs the setup wizard on first run, then auto-launches the interactive AI agent |
| `cvc up` | One-command start — setup (if needed) + init (if needed) + serve. The fastest way to get started |
| `cvc agent` | Interactive AI coding agent with Time Machine. Think Claude Code, but with built-in version control for every conversation |
| `cvc launch <tool>` | Zero-config auto-launch any AI tool through CVC. Supports: Claude Code, Aider, Codex CLI, Gemini CLI, Kiro CLI, Cursor, VS Code, Windsurf — plus 11 aliases |
| `cvc setup` | Interactive first-time setup wizard — pick your LLM provider, model, and API key |

### Tier 1 — Core Version Control

These are the Git-like primitives, but for AI context instead of source code.

| Command | Description |
|---------|-------------|
| `cvc init` | Initialise a `.cvc/` directory in the current project |
| `cvc status` | Show active branch, HEAD commit, context size, and all branches |
| `cvc log` | View the commit history for the active branch |
| `cvc commit -m "..."` | Create a cognitive checkpoint — save the AI agent's full brain state (conversation, decisions, code context) |
| `cvc branch <name>` | Create and switch to a new exploration branch — try different approaches without losing context |
| `cvc merge <source>` | Semantic three-way merge — intelligently combines AI context from two branches |
| `cvc restore <hash>` | Time-travel: restore the agent's brain to any previous state |

### Tier 1.5 — Infrastructure & Connectivity

| Command | Description |
|---------|-------------|
| `cvc serve` | Start the Cognitive Proxy server (FastAPI, OpenAI-compatible API) — intercepts all LLM traffic for automatic context capture |
| `cvc mcp` | Start CVC as an MCP (Model Context Protocol) server — stdio or SSE transport for auth-based IDEs |
| `cvc connect [tool]` | Interactive connection wizard with tool-specific setup guides for 14 different AI coding tools |
| `cvc doctor` | Health check for Python, config, `.cvc/` directory, Git, API keys, and Ollama |

### Tier 2 — Power User

| Command | Description |
|---------|-------------|
| `cvc recall "query"` | Natural-language search across ALL past conversations — vector search + text search + deep content matching |
| `cvc context --show` | Display stored conversation content — summary or full messages |
| `cvc export --markdown` | Export any conversation as shareable Markdown — perfect for code reviews and knowledge sharing |
| `cvc inject <project>` | Cross-project context transfer — pull conversations and decisions from another project into the current one |
| `cvc diff <hash1> [hash2]` | Knowledge & decision diff between two cognitive commits — see what changed in the AI's understanding |
| `cvc stats` | Analytics dashboard: token usage, estimated costs, commit type distribution, peak productivity hours, top files discussed |
| `cvc compact --smart` | AI-powered context compression — intelligently reduces context size while preserving critical decisions and code |
| `cvc timeline` | ASCII timeline visualisation of all AI interactions across all branches |
| `cvc sessions` | View Time Machine session history from the proxy server |

### Tier 2.5 — VCS Bridge (Git ↔ CVC Sync)

| Command | Description |
|---------|-------------|
| `cvc install-hooks` | Install Git hooks so CVC and Git stay in sync automatically |
| `cvc capture-snapshot` | Capture CVC state linked to the current Git commit |
| `cvc restore-for-checkout` | Restore CVC state corresponding to a Git checkout (invoked by hooks) |

### Tier 3 — Enterprise & Team Collaboration

| Command | Description |
|---------|-------------|
| `cvc sync push <path>` | Push cognitive commits and blobs to a remote CVC repository — share AI knowledge with your team |
| `cvc sync pull <path>` | Pull cognitive commits from a remote — import team-shared AI context |
| `cvc sync status` | Show status of all configured sync remotes |
| `cvc sync remote <path>` | Register a named remote repository |
| `cvc audit` | Security audit trail — compliance-ready dashboard with risk levels (low/medium/high/critical), compliance scoring (0–100%), event filtering, and JSON/CSV export |

---

## 2. MCP Tools — For IDE Integration (20 tools)

These tools are exposed via the Model Context Protocol, allowing any MCP-compatible IDE (VS Code + Copilot, Cursor, Windsurf, Claude Desktop, etc.) to use CVC natively.

### Core Operations

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cvc_status` | Show active branch, HEAD, context size, all branches | — |
| `cvc_commit` | Create a cognitive checkpoint | `message` (required), `commit_type` |
| `cvc_branch` | Create a new branch and switch to it | `name` (required), `description` |
| `cvc_merge` | Semantic three-way merge between branches | `source_branch` (required), `target_branch` |
| `cvc_restore` | Time-travel to a previous commit | `commit_hash` (required) |
| `cvc_log` | Show commit history | `limit` |

### Context Management (MCP-Specific)

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cvc_set_workspace` | Set the workspace directory (multi-workspace support) | `path` (required) |
| `cvc_capture_context` | Manually capture conversation messages into CVC — essential for IDEs that don't auto-capture (e.g., GitHub Copilot) | `messages` (required), `commit_message` |
| `cvc_get_context` | Read saved context from HEAD or a specific commit | `commit_hash`, `limit`, `full` |

### Power User

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cvc_recall` | Natural-language search across all past conversations | `query` (required), `limit`, `deep` |
| `cvc_export` | Export a commit's conversation as shareable Markdown | `commit_hash`, `output_path` |
| `cvc_inject` | Cross-project context transfer | `source_project` (required), `query` (required), `limit` |
| `cvc_diff` | Knowledge/decision diff between two commits | `hash_a` (required), `hash_b` |
| `cvc_stats` | Aggregated analytics — tokens, costs, patterns, top files | — |
| `cvc_compact` | AI-powered context compression | `smart`, `keep_recent`, `target_ratio` |
| `cvc_timeline` | Timeline of all cognitive commits across branches | `limit` |

### Enterprise & Team

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cvc_sync_push` | Push cognitive commits and blobs to a remote | `remote_path` (required), `remote_name`, `branch` |
| `cvc_sync_pull` | Pull cognitive commits from a remote | `remote_path` (required), `remote_name`, `branch` |
| `cvc_sync_status` | Show configured sync remotes | `remote_name` |
| `cvc_audit` | Security audit trail with compliance scoring and export | `event_type`, `risk_level`, `since_days`, `limit`, `export_format` |

---

## 3. Built-in Agent Tools (17 tools)

The `cvc agent` interactive AI coding agent comes with 17 built-in tools that the LLM can call autonomously.

### File Operations

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `read_file` | Read file contents with optional line ranges | `path` (required), `start_line`, `end_line` |
| `write_file` | Create or overwrite a file (auto-creates parent directories) | `path` (required), `content` (required) |
| `edit_file` | Find-and-replace with fuzzy matching fallback (60% similarity threshold) | `path` (required), `old_string` (required), `new_string` (required) |
| `patch_file` | Apply unified diff patches (multi-hunk support) | `path` (required), `diff` (required) |

### Shell Execution

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `bash` | Execute shell commands (PowerShell on Windows, bash on Linux/macOS) | `command` (required), `timeout` |

### Search & Discovery

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `glob` | Find files matching a glob pattern | `pattern` (required), `path` |
| `grep` | Search for text/regex patterns across files | `pattern` (required), `path`, `include` |
| `list_dir` | List directory contents | `path` |

### Web

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `web_search` | Search the web via DuckDuckGo (no API key required) | `query` (required), `max_results` |

### Time Machine (CVC)

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cvc_status` | Show branch, HEAD, context size | — |
| `cvc_log` | Show commit history | `limit` |
| `cvc_commit` | Create a cognitive checkpoint | `message` (required) |
| `cvc_branch` | Create and switch to a new branch | `name` (required), `description` |
| `cvc_restore` | Time-travel to a previous commit | `commit_hash` (required) |
| `cvc_merge` | Semantic three-way merge | `source_branch` (required), `target_branch` |
| `cvc_search` | Search commit history by keyword | `query` (required), `limit` |
| `cvc_diff` | Diff current context vs a commit, or between two commits | `commit_a` (required), `commit_b` |

---

## 4. Agent Capabilities & Features

Beyond the 17 callable tools, the `cvc agent` has deep built-in intelligence:

### Conversational AI

- **Token-by-token streaming** — real-time response display
- **Multi-turn context management** — maintains full conversation history
- **Parallel tool execution** — executes multiple tool calls per turn for speed
- **Auto-commit** at configurable intervals (default: every 2 turns) — your work is always saved
- **Session resume** — picks up exactly where you left off from the last CVC commit
- **Error recovery** — automatic retry loop (up to 2 retries) on failures
- **Safety limits** — max 25 tool iterations per turn to prevent runaway loops

### Interactive Features

| Slash Command | Description |
|---------------|-------------|
| `/help` | Show available commands |
| `/undo` | Undo the last file change |
| `/web` | Search the web for docs, APIs, or error solutions |
| `/git` | Show Git status and recent commits |
| `/model` | Switch LLM model mid-conversation |
| `/cost` | Show session cost breakdown |
| `/memory` | View persistent cross-session memory |
| `/status` | Show CVC Time Machine status |
| `/quit` | Exit the agent |

### Auto-Context Intelligence

On startup, the agent automatically:
- **Indexes the file tree** (up to 4 levels deep, 200 files)
- **Reads project manifests**: `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `Makefile`, `CMakeLists.txt`, `requirements.txt`, `setup.py`, `composer.json`, `Gemfile`, and more (14 formats)
- **Extracts files from error tracebacks** — automatically reads referenced files from Python, Node.js, and Rust errors
- **Respects `.cvcignore`** — custom file exclusion patterns (similar to `.gitignore`)

### Persistent Memory

- **Cross-session memory** stored in `~/.cvc/memory.md` + `memory_index.json`
- Automatically summarises each session: topics discussed, workspace, model used, cost
- **Workspace-aware recall** — prioritises memories from the same project
- Injects relevant memory context into the system prompt for continuity
- Stores up to 50 memory entries

### Cost Tracking

- **Per-turn and per-session** cost calculation
- **Cache-aware pricing** — cache-read tokens priced at 10% of input cost
- Supports pricing for all 16 models
- Real-time cost display via `/cost` slash command

---

## 5. Provider Adapters (4)

CVC works with any major LLM provider:

| Provider | Models | Pricing |
|----------|--------|---------|
| **Anthropic** | Claude Opus 4.6, Opus 4.5, Sonnet 4.5, Haiku 4.5 | $0.80–$75/MTok |
| **OpenAI** | GPT-5.2, GPT-5.2-Codex, GPT-5-mini, GPT-4.1 | Frontier pricing |
| **Google** | Gemini 3 Pro, Gemini 3 Flash, Gemini 2.5 Pro, Gemini 2.5 Flash | Standard–Premium |
| **Ollama** | Qwen 2.5 Coder 7B, Qwen 3 Coder 30B, Devstral 24B, DeepSeek R1 8B | **Free** (local) |

---

## 6. Supported Models (16)

| Provider | Model | Tier | Input/Output Cost |
|----------|-------|------|-------------------|
| Anthropic | `claude-opus-4-6` | Frontier | $15 / $75 per MTok |
| Anthropic | `claude-opus-4-5` | Frontier | $15 / $75 per MTok |
| Anthropic | `claude-sonnet-4-5` | Standard | $3 / $15 per MTok |
| Anthropic | `claude-haiku-4-5` | Budget | $0.80 / $4 per MTok |
| OpenAI | `gpt-5.2` | Frontier | Provider pricing |
| OpenAI | `gpt-5.2-codex` | Frontier | Provider pricing |
| OpenAI | `gpt-5-mini` | Mid-tier | Provider pricing |
| OpenAI | `gpt-4.1` | Mid-tier | Provider pricing |
| Google | `gemini-3-pro-preview` | Premium | Provider pricing |
| Google | `gemini-3-flash-preview` | Standard | Provider pricing |
| Google | `gemini-2.5-pro` | Premium | Provider pricing |
| Google | `gemini-2.5-flash` | Standard | Provider pricing |
| Ollama | `qwen2.5-coder:7b` | Local (~4 GB) | **Free** |
| Ollama | `qwen3-coder:30b` | Local (~18 GB) | **Free** |
| Ollama | `devstral:24b` | Local (~14 GB) | **Free** |
| Ollama | `deepseek-r1:8b` | Local (~5 GB) | **Free** |

---

## 7. IDE & Tool Connection Guides (14 tools)

CVC provides one-command setup guides for connecting to:

| # | Tool | Connection Method |
|---|------|-------------------|
| 1 | **VS Code** | MCP server via GitHub Copilot |
| 2 | **Antigravity** | MCP server |
| 3 | **Cursor** | MCP server (`mcp.json`) |
| 4 | **Windsurf** | MCP server (`mcp_config.json`) |
| 5 | **Continue.dev** | MCP server (`config.yaml`) |
| 6 | **Cline / Roo** | MCP server (VS Code extension settings) |
| 7 | **GitHub Copilot (BYOK)** | Cognitive Proxy (API key mode) |
| 8 | **Claude Code CLI** | Cognitive Proxy (Anthropic Messages API) |
| 9 | **Gemini CLI** | MCP server |
| 10 | **Kiro CLI** | MCP server |
| 11 | **Aider** | Cognitive Proxy (OpenAI-compatible API) |
| 12 | **Open WebUI** | Cognitive Proxy (OpenAI-compatible API) |
| 13 | **Firebase Studio** | MCP server |
| 14 | **Codex CLI** | Cognitive Proxy (OpenAI-compatible API) |

---

## 8. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CVC Architecture                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐   │
│  │ cvc agent │    │ cvc serve    │    │ cvc mcp                  │   │
│  │ (REPL)   │    │ (Proxy)      │    │ (MCP Server)             │   │
│  └────┬─────┘    └──────┬───────┘    └────────────┬─────────────┘   │
│       │                 │                          │                  │
│       ▼                 ▼                          ▼                  │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                   CVCEngine (operations/engine.py)           │    │
│  │  commit · branch · merge · restore · recall · inject        │    │
│  │  diff · stats · compact · timeline · sync · audit           │    │
│  └──────────────────────────┬───────────────────────────────────┘    │
│                             │                                        │
│  ┌──────────────────────────▼───────────────────────────────────┐    │
│  │              Three-Tiered Context Database                   │    │
│  │                                                              │    │
│  │  Tier 1: IndexDB (SQLite)        — commits, branches, refs  │    │
│  │  Tier 2: BlobStore (CAS + Zstd)  — content-addressable      │    │
│  │  Tier 3: SemanticStore (Chroma)   — vector search (optional) │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              Provider Adapters                               │    │
│  │  Anthropic · OpenAI · Google · Ollama                        │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

- **Content-Addressable Storage (CAS)**: Every piece of context is SHA-256 hashed and Zstandard-compressed. Identical content is stored only once.
- **Merkle DAG**: Commits form a directed acyclic graph, just like Git. Each commit references its parent and a content blob.
- **Three-Way Semantic Merge**: Branch merges use LLM-powered semantic deduplication, not textual diff.
- **Automatic Audit Trail**: Every commit, merge, restore, and sync operation is logged with risk levels, provider info, and compliance metadata.
- **Zero-Config Philosophy**: `cvc` with no arguments gets you from zero to a working AI coding agent in under 30 seconds.

---

## 9. Competitive Comparison

| Feature | CVC | Claude Code | Codex CLI | Gemini CLI | Copilot CLI |
|---------|-----|-------------|-----------|------------|-------------|
| Version control for AI context | ✅ Full Git-like VCS | ❌ | ❌ | ❌ | ❌ |
| Branching & merging AI sessions | ✅ | ❌ | ❌ | ❌ | ❌ |
| Time-travel / restore | ✅ | ❌ | ❌ | ❌ | ❌ |
| Cross-project context transfer | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-provider support | ✅ 4 providers, 16 models | Anthropic only | OpenAI only | Google only | OpenAI only |
| Local/free models (Ollama) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Team sync (push/pull) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Security audit trail | ✅ Compliance-ready | ❌ | ❌ | ❌ | ❌ |
| Analytics dashboard | ✅ Tokens, costs, patterns | ❌ | ❌ | ❌ | ❌ |
| AI-powered compression | ✅ | ❌ | ❌ | ❌ | ❌ |
| IDE connections | ✅ 14 tools | 1 | 1 | 1 | 1 |
| MCP server | ✅ | ❌ | ❌ | ❌ | ❌ |
| Web search | ✅ Built-in | ❌ | ✅ | ✅ | ❌ |
| Persistent memory | ✅ Cross-session | ❌ | ❌ | ❌ | ❌ |
| Git integration | ✅ Bidirectional hooks | ❌ | ✅ | ❌ | ❌ |
| Cost tracking | ✅ Real-time | ❌ | ❌ | ❌ | ❌ |
| Knowledge diff | ✅ | ❌ | ❌ | ❌ | ❌ |
| Zero-config launch | ✅ `cvc launch <tool>` | Manual | Manual | Manual | Manual |
| Open source | ✅ | ✅ | ✅ | ❌ | ❌ |

---

## 10. Installation

```bash
# Install from PyPI
pip install tm-ai

# Or with uv (recommended)
uv pip install tm-ai

# Verify
cvc --help
```

### Quickstart

```bash
# Option A: Interactive agent (fastest)
cvc agent

# Option B: Launch your favourite tool through CVC
cvc launch claude
cvc launch aider
cvc launch codex
cvc launch gemini

# Option C: Step by step
cvc setup          # Pick provider & model
cvc init           # Initialise .cvc/
cvc serve          # Start proxy
cvc connect        # Wire up your IDE
```

---

*Generated for CVC v1.4.71 — February 2026*
