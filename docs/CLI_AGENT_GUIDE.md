# CVC CLI Agent - Complete Guide

## Table of Contents

- [Overview](#overview)
- [What's New in v1.4.3](#whats-new-in-v143)
- [Installation & Setup](#installation--setup)
- [Quick Start](#quick-start)
- [Automatic Features](#automatic-features)
- [Slash Commands](#slash-commands)
- [Time Machine Features](#time-machine-features)  
- [Tool Capabilities](#tool-capabilities)
- [Multi-Modal Support](#multi-modal-support)
- [Git Integration](#git-integration)
- [Memory & Persistence](#memory--persistence)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Overview

The **CVC CLI Agent** is an interactive AI coding assistant that runs in your terminal with built-in **Time Machine capabilities**. Think Claude Code or Cursor, but with git-like version control for your entire conversation history.

### Key Features

✅ **Automatic Persistence** - Every message saved, every 2 turns auto-committed  
✅ **Auto-Restore** - Resume your last conversation on startup  
✅ **Token Streaming** - Real-time responses as the AI thinks  
✅ **Multi-File Context** - Automatically loads relevant project files  
✅ **Tool Execution** - Read files, run commands, search web, edit code  
✅ **Visual Support** - Paste screenshots, analyze images  
✅ **Git Integration** - See status, stage changes, commit from chat  
✅ **Time Travel** - Rewind to any previous conversation state  
✅ **Branch Experiments** - Try risky changes without losing your main conversation  
✅ **Cost Tracking** - Per-session and per-turn token/cost monitoring

---

## What's New in v1.4.3

### 🚨 Critical Fixes

**Fixed**: `AttributeError: 'CVCConfig' object has no attribute 'cvc_dir'`  
- Persistent cache now works correctly in CLI mode
- No more crash warnings every turn

### 🎯 New Automatic Features

1. **Auto-Restore on Startup**
   - CLI now automatically loads your last conversation
   - No manual `/restore` needed
   - Seamless continuation from where you left off

2. **Aggressive Auto-Commit**
   - Changed from every 5 turns to every 2 turns
   - Minimal data loss risk on crashes
   - Configurable via `CVC_AGENT_AUTO_COMMIT` env var

3. **Persistent Cache**
   - Every message saved to `.cvc/context_cache.json`
   - Survives force-quits and crashes
   - Automatic recovery on next startup

### 🔧 Optimization Changes

- **Auto-commit interval**: 5 → 2 assistant turns
- **Auto-restore**: Now runs automatically on CLI startup
- **Cache saves**: Happens on every `push_message()` call
- **Session exits**: Always commits before closing

---

## Installation & Setup

### Prerequisites

- **Python 3.11+** (Python 3.12 or 3.13 recommended)
- **API Key** for your chosen provider (Anthropic, OpenAI, Google, or Ollama)

### Install CVC

```bash
# Using pip
pip install tm-ai

# Using uv (recommended - faster)
uv pip install tm-ai

# Verify installation
cvc --version
```

### Initial Configuration

```bash
# Interactive setup wizard
cvc setup

# Or manually set API key
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export OPENAI_API_KEY="sk-..."
# or
export GOOGLE_API_KEY="..."
```

### Supported Providers

| Provider | Models | API Key Required |
|----------|--------|------------------|
| **Anthropic** | claude-3.5-sonnet, opus, haiku | ✅ ANTHROPIC_API_KEY |
| **OpenAI** | gpt-4, gpt-4-turbo, gpt-3.5-turbo | ✅ OPENAI_API_KEY |
| **Google** | gemini-2.0-flash, gemini-1.5-pro | ✅ GOOGLE_API_KEY |
| **Ollama** | Any local model | ❌ (local) |

---

## Quick Start

### Launch the Agent

```bash
# Start with default provider (from setup)
cvc

# Or explicitly:
cvc agent

# With specific provider
cvc agent --provider anthropic

# With specific model
cvc agent --model claude-3.5-sonnet

# Ollama (local)
cvc agent --provider ollama --model llama3
```

### Your First Conversation

```
╭─ CVC@main (turn 1)
╰─▸ Help me understand this codebase

  ⟫ Thinking…
╭─ Agent ─────────────────────────────────────────╮
│ I'll analyze your project structure.            │
│                                                  │
│ [Automatically reads files, explains structure] │
╰──────────────────────────────────────────────────╯

╭─ CVC@main (turn 2)
╰─▸ Create a new function to handle user auth
```

The agent will:
1. ✅ Automatically read relevant files from your project
2. ✅ Execute tools (file reads, edits, terminal commands)
3. ✅ Save every message to persistent cache
4. ✅ Auto-commit every 2 assistant responses
5. ✅ Show token usage and costs per turn

---

## Automatic Features

### 1. Auto-Restore (NEW in v1.4.3)

**What it does**: Automatically loads your last conversation when you start the CLI.

**How it works**:
1. CLI starts up
2. Checks for last commit on current branch
3. Loads messages from that commit
4. Falls back to persistent cache if no commits
5. Asks if you want to resume or start fresh

**Example**:
```
╭──────────────────────────────────────────────────╮
│ Found existing session with 15 messages.        │
│                                                  │
│ Resume or start fresh?                          │
│   • [R]esume - Continue the conversation        │
│   • [F]resh - Clear and start new               │
╰──────────────────────────────────────────────────╯

→ Resuming session with 15 messages of context.
```

### 2. Auto-Commit

**What it does**: Automatically creates checkpoints every 2 assistant turns.

**Frequency**: Every 2 turns (configurable)

**Configuration**:
```bash
# Default (every 2 turns)
cvc

# Custom interval (every 5 turns)
export CVC_AGENT_AUTO_COMMIT=5
cvc
```

**Visual Feedback**:
```
╭─ Agent ──────────────────────────────────────╮
│ [Response here]                              │
╰──────────────────────────────────────────────╯

  ✓ Auto-checkpoint at turn 4 → a1b2c3d4
```

### 3. Persistent Cache

**What it does**: Saves every message to `.cvc/context_cache.json`.

**When it saves**:
- Every time you send a message
- Every time the agent responds
- On every tool execution
- Before exit

**Recovery**:
- If you force-quit (Ctrl+C repeatedly)
- If the process crashes
- If your machine loses power
- Next startup loads from cache

**Location**: `<your_project>/.cvc/context_cache.json`

### 4. Auto-Context

**What it does**: Automatically loads relevant files when starting a new session.

**Smart detection**:
- Looks for `README.md`, `pyproject.toml`, `package.json`
- Scans file mentions in error messages
- Monitors which files you're discussing
- Adds them to context automatically

**Example**:
```
  [Auto-context] Loaded: README.md (1245 chars)
  [Auto-context] Loaded: src/main.py (3821 chars)
```

### 5. Final Commit on Exit

**What it does**: Saves uncommitted work when you exit.

**Triggered by**:
- `/exit`, `/quit`, `/q` commands
- Normal Ctrl+C exit

**Example**:
```
╭─ CVC@main (turn 7)
╰─▸ /exit

  ✓ Session end at turn 7 → f0a0f8a9
  Goodbye! 👋
```

---

## Slash Commands

All commands start with `/` and are executed immediately.

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/help` | Show all available commands | `/help` |
| `/exit`, `/quit`, `/q` | Save and exit the agent | `/exit` |
| `/clear` | Clear the terminal screen | `/clear` |

### CVC Time Machine Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/commit <message>` | Save current conversation as checkpoint | `/commit Working auth system` |
| `/branch <name>` | Create new branch from current state | `/branch experimental-refactor` |
| `/merge <branch>` | Merge another branch into current | `/merge experimental-refactor` |
| `/restore <hash>` | Time-travel to a previous commit | `/restore a1b2c3d4` |
| `/log` | View commit history | `/log` |
| `/status` | Show current branch, HEAD, context size | `/status` |

### Git Integration Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/git status` | Show Git working tree status | `/git status` |
| `/git diff` | Show Git changes | `/git diff` |
| `/git add <files>` | Stage files for commit | `/git add src/auth.py` |
| `/git commit <msg>` | Create Git commit | `/git commit "Add auth"` |
| `/git log` | View Git commit history | `/git log` |

### File & System Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/read <file>` | Read file contents | `/read src/main.py` |
| `/ls [path]` | List directory contents | `/ls src/` |
| `/pwd` | Show current working directory | `/pwd` |
| `/env` | Show environment variables | `/env` |
| `/undo` | Undo last file change (if any) | `/undo` |

### Advanced Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/web <query>` | Search the web (if configured) | `/web python async best practices` |
| `/image <path>` | Attach image to next message | `/image screenshot.png` |
| `/clipboard` | Attach clipboard image | `/clipboard` |
| `/cost` | Show session cost summary | `/cost` |
| `/memory` | Show remembered facts from past sessions | `/memory` |

---

## Time Machine Features

### Commits (Checkpoints)

**Manual Commit**:
```
╭─ CVC@main (turn 5)
╰─▸ /commit Implemented user authentication with JWT tokens

  ✓ Committed a1b2c3d4: Implemented user authentication with JWT tokens
```

**Auto-Commit** (every 2 turns):
```
╭─ Agent ──────────────────────────────────────╮
│ [Response with code implementation]          │
╰──────────────────────────────────────────────╯

  ✓ Auto-checkpoint at turn 6 → b2c3d4e5
```

**View History**:
```
╭─ CVC@main (turn 7)
╰─▸ /log

╭─ Commit History ─────────────────────────────────╮
│ b2c3d4e5  Auto-checkpoint at turn 6              │
│ a1b2c3d4  Implemented user authentication...     │
│ 9a8b7c6d  Initial project setup                  │
│ 00000000  Genesis — CVC initialised              │
╰──────────────────────────────────────────────────╯
```

### Branches (Experiments)

**Create Branch** (try risky changes):
```
╭─ CVC@main (turn 8)
╰─▸ /branch experimental-async-refactor

  ✓ Created branch 'experimental-async-refactor' → b2c3d4e5
  Switched to branch: experimental-async-refactor
```

**Work on Branch**:
```
╭─ CVC@experimental-async-refactor (turn 9)
╰─▸ Refactor all database calls to use asyncio

  [Agent makes experimental changes]
```

**Merge Success Back to Main**:
```
╭─ CVC@experimental-async-refactor (turn 15)
╰─▸ /merge main

  ✓ Merged 'main' into 'experimental-async-refactor'
```

**Or Switch Back Without Merging**:
```
╭─ CVC@experimental-async-refactor (turn 15)
╰─▸ /restore a1b2c3d4

  ✓ Restored to a1b2c3d4 (before experimental changes)
  Switched to branch: main
```

### Time Travel (Restore)

**Rewind to Previous State**:
```
╭─ CVC@main (turn 20)
╰─▸ /restore a1b2c3d4

  ✓ Restored to a1b2c3d4: Implemented user authentication...
  ↺ Rolled back 12 messages
```

**Undo Mistakes**:
```
╭─ CVC@main (turn 25)
╰─▸ The last 5 turns went completely wrong, go back to the working version

  [Agent calls restore tool automatically]
  ✓ Restored to commit b2c3d4e5 (before the errors)
```

---

## Tool Capabilities

The agent can execute these tools automatically during conversation:

### File Operations

| Tool | What It Does | Auto-Triggered By |
|------|--------------|-------------------|
| **read_file** | Read file contents | "Show me X.py", "What's in the README?" |
| **write_file** | Create/overwrite file | "Create a new module for auth" |
| **edit_file** | Apply diff-based edits | "Change the login function to use async" |
| **list_files** | List directory contents | "What files are in src/?" |
| **search_files** | Grep search across files | "Find all uses of 'database'" |
| **get_cwd** | Get current directory | "Where are we?" |

### Terminal Commands

| Tool | What It Does | Auto-Triggered By |
|------|--------------|-------------------|
| **run_terminal_command** | Execute shell commands | "Install pytest", "Run the tests" |
| **git_*_operations** | Git status/add/commit/diff | "Show me what changed", "Commit these changes" |

### Web & Research

| Tool | What It Does | Auto-Triggered By |
|------|--------------|-------------------|
| **web_search** | Search DuckDuckGo | "Look up Python async patterns" |
| **fetch_url** | Download web content | "Get the docs from that URL" |

### CVC Operations

| Tool | What It Does | Auto-Triggered By |
|------|--------------|-------------------|
| **cvc_commit** | Save checkpoint | "Save this conversation" |
| **cvc_branch** | Create branch | "Try this in a separate branch" |
| **cvc_merge** | Merge branches | "Bring those experimental changes back" |
| **cvc_restore** | Time-travel | "Go back to the working version" |
| **cvc_log** | View history | "Show me the commit history" |

---

## Multi-Modal Support

### Images & Screenshots

**Paste from Clipboard** (Windows):
```
╭─ CVC@main (turn 1)
╰─▸ /clipboard
Explain this error message

  [Agent analyzes screenshot from clipboard]
```

**Attach Image File**:
```
╭─ CVC@main (turn 1)
╰─▸ /image error_screenshot.png
What's wrong here?

  [Agent analyzes image file]
```

**Supported Formats**:
- PNG, JPEG, GIF, BMP
- Base64 encoded images
- Clipboard screenshots (Windows)

**Providers**:
- ✅ Anthropic (Claude 3+ models)
- ✅ OpenAI (GPT-4 Vision/Turbo)
- ✅ Google (Gemini Pro Vision)
- ❌ Ollama (model-dependent)

---

## Git Integration

The CLI agent has deep Git integration for tracking both conversation AND code changes.

### Automatic Git Status

On startup, you see:
```
● Git: main  (clean)
```

Or with changes:
```
● Git: main ± (M:3, A:1, D:0)
```

### Git Commands

**View Status**:
```
╭─ CVC@main (turn 5)
╰─▸ /git status

  Modified:   src/auth.py
  Modified:   src/database.py  
  Untracked:  tests/test_auth.py
```

**Stage Changes**:
```
╭─ CVC@main (turn 6)
╰─▸ /git add src/auth.py tests/test_auth.py

  ✓ Staged 2 files
```

**Commit**:
```
╭─ CVC@main (turn 7)
╰─▸ /git commit "Add JWT authentication"

  ✓ Created Git commit: a1b2c3d4
```

**View Diff**:
```
╭─ CVC@main (turn 8)
╰─▸ /git diff

  diff --git a/src/auth.py b/src/auth.py
  [Shows colorized diff]
```

### Dual Version Control

You have TWO independent version control systems:

1. **Git** - Tracks code changes (files)
2. **CVC** - Tracks conversation changes (context)

**Example workflow**:
```bash
# Make code changes via agent conversation
You: "Implement JWT authentication"
Agent: [Creates/edits files]

# CVC auto-commits the conversation
✓ Auto-checkpoint at turn 4 → cvc:b2c3d4

# You manually commit code to Git
/git add src/auth.py
/git commit "Add JWT authentication"
✓ Created Git commit: git:a1b2c3d4

# Now you have:
# - CVC commit: b2c3d4 (conversation about auth)
# - Git commit: a1b2c3d4 (actual auth code)
```

---

## Memory & Persistence

### Session Memory

**What's remembered**:
- Previous conversation topics
- Files you worked on
- Commands you ran
- Decisions you made
- API patterns you discussed

**How it works**:
- Stored in `.cvc/memory.json`
- Recalls relevant memories on startup
- Updates after each session
- Limited to last 3 sessions by default

**Example startup**:
```
  ℹ️  Last session: 2026-02-14T01:42
     Started with: "Help me understand the authentication system"
```

### Multi-Session Continuity

**Scenario**: You work on a project over multiple days.

**Day 1** (11 AM):
```
╭─ CVC@main (turn 1)
╰─▸ Help me build a user authentication system

  [Long conversation, many file edits]

╭─ CVC@main (turn 25)
╰─▸ /exit

  ✓ Auto-checkpoint at turn 25 → a1b2c3d4
  ✓ Session end at turn 25 → a1b2c3d4
```

**Day 2** (9 AM):
```
$ cvc

  ● Git: main (clean)
  ℹ️  Last session: 2026-02-14T11:23
     Started with: "Help me build a user authentication system"
  
  ✅ Auto-restored 25 messages from last commit a1b2c3d4

╭─ CVC@main (turn 1)
╰─▸ Continue where we left off - add password hashing

  [Agent remembers full context from yesterday]
```

### Persistent Cache Recovery

**Scenario**: Your laptop crashes during a conversation.

**Before crash**:
```
╭─ CVC@main (turn 8)
╰─▸ Implement the database migration system

  [Power outage - laptop dies]
```

**After reboot**:
```
$ cvc

  ⚠️  Found persistent cache (crash recovery)
  ✅ Restored 8 messages from cache

╭─ CVC@main (turn 1)
╰─▸ [Your conversation is still here!]
```

The cache is saved:
- On every message push
- Every 2 turns (auto-commit)
- Before exit

Location: `.cvc/context_cache.json`

---

## Configuration

### Environment Variables

```bash
# Provider selection
export CVC_PROVIDER="anthropic"  # or: openai, google, ollama

# Model selection
export CVC_MODEL="claude-3.5-sonnet"

# API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."

# Auto-commit interval (CLI only)
export CVC_AGENT_AUTO_COMMIT="2"  # commits every N assistant turns

# Ollama host
export OLLAMA_HOST="http://localhost:11434"

# Web search (optional)
export BRAVE_API_KEY="..."  # or SERPER_API_KEY, TAVILY_API_KEY
```

### Global Config File

**Location**: `~/.config/cvc/config.json`

**Structure**:
```json
{
  "provider": "anthropic",
  "model": "claude-3.5-sonnet",
  "api_keys": {
    "anthropic": "sk-ant-...",
    "openai": "sk-...",
    "google": "..."
  }
}
```

**Edit via**:
```bash
cvc setup
```

### Project-Specific Config

**Location**: `<your_project>/.cvc/config.json`

**Auto-created** when you first run `cvc` in a directory.

**Contains**:
- Project root path
- Active branch
- Provider/model overrides
- Custom prompt additions

---

## Troubleshooting

### Issue: "No API key found for anthropic"

**Cause**: API key not configured.

**Solutions**:
```bash
# Option 1: Environment variable
export ANTHROPIC_API_KEY="sk-ant-..."

# Option 2: Setup wizard
cvc setup

# Option 3: Edit config
nano ~/.config/cvc/config.json
```

---

### Issue: "Failed to save persistent cache: 'CVCConfig' object has no attribute 'cvc_dir'"

**Cause**: Bug in CVC <= 1.4.2

**Solution**: Update to v1.4.3+
```bash
pip install --upgrade tm-ai
```

---

### Issue: "Auto-restore failed"

**Cause**: Corrupted database or cache file.

**Solutions**:
```bash
# Check for database
ls .cvc/cvc.db

# Check for cache
ls .cvc/context_cache.json

# Start fresh (backup first!)
mv .cvc .cvc.backup
cvc
```

---

### Issue: Context not persisting across restarts

**Symptoms**:
- CLI starts with empty context every time
- No "Resume session" prompt

**Diagnosis**:
```bash
# Check if commits exist
ls .cvc/objects/

# Check if cache exists
cat .cvc/context_cache.json

# Check auto-commit interval
echo $CVC_AGENT_AUTO_COMMIT
```

**Solution**:
```bash
# Ensure auto-commit is enabled (default: 2)
export CVC_AGENT_AUTO_COMMIT=2

# Manually commit important work
/commit Important checkpoint before testing
```

---

### Issue: "Too many tokens" error

**Cause**: Context window too large for the model.

**Solutions**:
```bash
# Create a new branch (starts fresh)
/branch new-topic

# Or restore to earlier commit
/log
/restore <earlier_commit_hash>

# Or start completely fresh
/exit
cvc
# Choose "Fresh" when prompted
```

---

## Advanced Usage

### Custom System Prompts

Add custom instructions to every session:

**Location**: `.cvc/system_prompt_additions.md`

**Example**:
```markdown
# Project Guidelines

- Always use type hints in Python
- Prefer async/await over threading
- Write tests for every new function
- Use Black for formatting
```

The agent will incorporate these rules into every response.

---

### Multi-Branch Workflows

**Scenario**: You want to try 3 different refactoring approaches.

```bash
╭─ CVC@main (turn 10)
╰─▸ /commit Working baseline before experiments

# Try approach 1
/branch refactor-approach-1
# [Work on approach 1]
/commit Approach 1: Complete async refactor

# Back to main, try approach 2
/restore <main_commit>
/branch refactor-approach-2  
# [Work on approach 2]
/commit Approach 2: Hybrid sync/async

# Back to main, try approach 3
/restore <main_commit>
/branch refactor-approach-3
# [Work on approach 3]
/commit Approach 3: Keep sync, optimize queries

# Compare all three
/log  # See all branch commits

# Merge the best one
/merge refactor-approach-2
/commit Merged approach 2 - best performance
```

---

### Parallel Development

**Scenario**: Working on frontend and backend simultaneously.

```bash
# Main work on backend API
cvc
╭─ CVC@backend-api (turn 1)
╰─▸ Build the REST API for user management

# In another terminal, work on frontend
cd ../frontend
cvc  
╭─ CVC@frontend-ui (turn 1)
╰─▸ Build the React components for user management
```

Each project gets its own `.cvc/` database - completely independent!

---

### Cost Optimization

**View costs**:
```
╭─ CVC@main (turn 25)
╰─▸ /cost

╭─ Session Cost Summary ──────────────────╮
│ Total:        $0.1234                    │
│ Input:        45,123 tokens ($0.0987)    │
│ Output:       8,921 tokens ($0.0247)     │
│ Turns:        25                         │
│ Avg/turn:     $0.0049                    │
╰─ ──────────────────────────────────────╯
```

**Optimize costs**:
- Use cheaper models for simple tasks (`gpt-3.5-turbo`, `claude-haiku`)
- Clear context when switching topics (`/branch new-topic`)
- Avoid pasting huge files (agent will search on demand)
- Use Ollama for free local inference

---

### Integration with Other Tools

**VS Code**:
```bash
# Open files the agent edited
code src/auth.py

# Or use CVC Proxy for VS Code extensions
cvc serve  # In separate terminal
# Then configure Continue.dev/Cline
```

**Claude Desktop** (via MCP):
```bash
# Use MCP mode instead
cvc mcp
# Configure Claude Desktop to use CVC MCP server
```

**Cursor/Windsurf**:
```bash
# Use proxy mode
cvc serve
# Point IDE to http://127.0.0.1:8000
```

---

## Best Practices

### 1. Commit Often

✅ **DO**:
```
# Commit at logical milestones
/commit Completed user authentication module
/commit Fixed database connection issues  
/commit Refactored API endpoints for clarity
```

❌ **DON'T**:
```
# Wait until end of day to commit
[100 turns of work]
/commit Stuff from today
```

---

### 2. Use Branches for Experiments

✅ **DO**:
```
# Risky refactor? Branch first!
/branch experimental-rewrite
# Try experimental changes
# If it works: /merge main
# If it fails: /restore <safe_commit>
```

❌ **DON'T**:
```
# Just YOLO it on main
You: "Rewrite the entire database layer using raw SQL"
# [10 turns later - everything broken]
You: "How do I undo this?"
```

---

### 3. Use Descriptive Commit Messages

✅ **DO**:
```
/commit Implemented JWT authentication with refresh tokens and rate limiting
/commit Fixed memory leak in WebSocket connection handler
/commit Added comprehensive error handling to file upload service
```

❌ **DON'T**:
```
/commit stuff
/commit fix
/commit changes
```

---

### 4. Leverage Auto-Restore

✅ **DO**:
```
# End sessions properly
You: "Great progress today!"
/exit

# Next day - auto-restore works
$ cvc
[Resume session? R/F] R
# Context restored, continue where you left off
```

❌ **DON'T**:
```
# Force kill every time
^C^C^C^C
# Next day
$ cvc
# Empty context, lost yesterday's progress
```

---

### 5. Monitor Costs

✅ **DO**:
```
# Check costs periodically
/cost

# Switch to cheaper models for simple tasks
cvc agent --model claude-haiku
```

❌ **DON'T**:
```
# Use opus/gpt-4 for everything
# Get a $100 bill at month-end
# Surprised Pikachu face
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Tab** | Auto-complete slash commands |
| **Ctrl+C** | Cancel current response (graceful) |
| **Ctrl+C** (2x) | Force exit (saves session) |
| **Ctrl+D** | Exit agent (same as `/exit`) |
| **Ctrl+L** | Clear screen (same as `/clear`) |
| **↑/↓** | Navigate command history |

---

## Tips & Tricks

### 1. Smart File Loading

Instead of manually reading files, just reference them:

```
You: "Optimize the process_payment function"

Agent: [Automatically reads src/payments.py, finds function, optimizes]
```

### 2. Error Auto-Context

When you see an error, just paste it:

```
You: "I got this error:
Traceback (most recent call last):
  File "src/main.py", line 42
    async def process():
IndentationError: expected an indented block"

Agent: [Automatically reads src/main.py, finds line 42, fixes indentation]
```

### 3. Natural Language Git

```
You: "Show me what I changed"
Agent: [Runs /git diff automatically]

You: "Commit these changes with message 'Add auth system'"
Agent: [Runs /git commit automatically]
```

### 4. Multi-Turn Planning

```
You: "I want to build a user authentication system. Plan it out."

Agent: "Here's my plan:
1. Database schema for users
2. Password hashing with bcrypt
3. JWT token generation
4. Refresh token rotation
5. Rate limiting
6. Email verification

Let's start with step 1?"

You: "Yes, do all 6 steps"

Agent: [Executes entire plan over multiple turns, auto-commits progress]
```

---

## Version History

- **v1.4.3** (2026-02-17): Auto-restore, aggressive auto-commit, fixed cache bug
- **v1.4.2** (2026-02-17): Improved MCP UX messaging
- **v1.4.1** (2026-02-17): Multi-workspace support
- **v1.4.0** (2026-02-17): Persistent cache, database-backed retrieval
- **v1.3.2** (2026-02-14): Content truncation fixes
- **v1.3.0** (2026-02-13): Workspace detection improvements
- **v0.9.0** (2024): Initial CLI agent release

---

## See Also

- **Main Documentation**: [README.md](README.md)
- **MCP Server Guide**: [MCP_DOCUMENTATION.md](MCP_DOCUMENTATION.md)
- **Multi-Workspace Guide**: [MULTI_WORKSPACE.md](MULTI_WORKSPACE.md)
- **Persistence Architecture**: [VERIFICATION.md](VERIFICATION.md)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **PyPI Package**: [tm-ai](https://pypi.org/project/tm-ai/)

---

## Support

For issues, feature requests, or contributions:

- **GitHub Issues**: [Create an issue](https://github.com/mannuking/AI-Cognitive-Version-Control/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mannuking/AI-Cognitive-Version-Control/discussions)

---

**Last Updated**: February 17, 2026  
**Document Version**: 1.4.3  
**CLI Agent Version**: 1.4.3+
