# CVC MCP Server - Complete Documentation

## Table of Contents

- [Overview](#overview)
- [What is MCP?](#what-is-mcp)
- [Installation](#installation)
- [IDE Setup](#ide-setup)
  - [VS Code + GitHub Copilot](#vs-code--github-copilot)
  - [Windsurf](#windsurf)
  - [Antigravity](#antigravity)
  - [Other MCP-Compatible Tools](#other-mcp-compatible-tools)
- [MCP Tools Reference](#mcp-tools-reference)
- [Multi-Workspace Support](#multi-workspace-support)
- [Configuration Examples](#configuration-examples)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Overview

CVC (Cognitive Version Control) provides a **Model Context Protocol (MCP) server** that integrates seamlessly with AI IDEs like VS Code, Windsurf, Antigravity, and any other MCP-compatible tools.

The MCP server exposes CVC's git-like version control system as tools that AI assistants can use to:
- 💾 **Save context snapshots** (commits)
- 🌿 **Create branches** for experimental conversations
- 🔀 **Merge insights** from different conversation threads
- ⏪ **Restore to previous states** (time-travel)
- 📊 **View commit history** and branch status
- 🗂️ **Manage multiple workspaces** (projects)

---

## What is MCP?

**Model Context Protocol (MCP)** is an open standard developed by Anthropic that enables AI assistants to securely interact with external tools and data sources.

### Why MCP for CVC?

- **🔐 Secure**: Runs locally on your machine, no cloud required
- **🔌 Universal**: Works with any MCP-compatible IDE/tool
- **🚀 Zero-config**: No API keys needed for local operation
- **💬 Natural**: AI assistants call CVC tools automatically during conversations
- **📦 Isolated**: Each project gets its own `.cvc/` database

---

## Installation

### Prerequisites

- **Python 3.11+** (Python 3.12 or 3.13 recommended)
- **pip** or **uv** package manager

### Install CVC

```bash
# Using pip
pip install tm-ai

# Using uv (recommended - faster)
uv pip install tm-ai

# Verify installation
cvc --version
```

### Verify MCP Server

```bash
# Test MCP server (should output MCP protocol messages)
cvc mcp
```

Press `Ctrl+C` to stop the test. If you see MCP protocol messages, the server is working correctly.

---

## IDE Setup

### VS Code + GitHub Copilot

#### Step 1: Install CVC

```bash
pip install tm-ai
```

#### Step 2: Configure MCP Server

**Location**: `C:\Users\<username>\AppData\Roaming\Code\User\mcp.json` (Windows)  
**Location**: `~/.config/Code/User/mcp.json` (Linux/Mac)

Create or edit `mcp.json`:

```json
{
  "servers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio"
    }
  },
  "inputs": []
}
```

#### Step 3: Reload VS Code

- Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
- Type "Developer: Reload Window"
- Press Enter

#### Step 4: Verify in GitHub Copilot

Open Copilot Chat and ask:
```
What CVC tools do you have access to?
```

Copilot should list tools like `cvc_status`, `cvc_commit`, `cvc_branch`, etc.

#### Step 5: Set Your Workspace (First Time)

In Copilot Chat:
```
Use cvc_set_workspace to set the workspace to E:\Projects\my-project
```

The AI will call the tool and CVC will create a `.cvc/` folder in your project directory.

---

### Windsurf

#### Step 1: Install CVC

```bash
pip install tm-ai
```

#### Step 2: Configure MCP in Windsurf

1. Open Windsurf Settings
2. Navigate to **Cascade** → **MCP Servers**
3. Add new server configuration:

```json
{
  "cvc": {
    "command": "cvc",
    "args": ["mcp"],
    "type": "stdio"
  }
}
```

#### Step 3: Restart Windsurf

Close and reopen Windsurf for changes to take effect.

#### Step 4: Test in Cascade

Open Cascade (Windsurf's AI assistant) and ask:
```
Show me the CVC status
```

Cascade should automatically call `cvc_status` and show your current branch and commit information.

---

### Antigravity

#### Step 1: Install CVC

```bash
pip install tm-ai
```

#### Step 2: Configure MCP

**Location**: Antigravity MCP settings (varies by installation)

Add CVC to your MCP servers configuration:

```json
{
  "servers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio"
    }
  }
}
```

#### Step 3: Restart Antigravity

Restart the Antigravity application to load the new MCP server.

---

### Other MCP-Compatible Tools

CVC's MCP server works with any tool that supports the Model Context Protocol:

- **Claude Desktop** (Anthropic's official MCP client)
- **Zed Editor** (with MCP support)
- **Custom MCP clients** (via stdio transport)

**Generic Configuration**:

```json
{
  "mcpServers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio"
    }
  }
}
```

Refer to your specific tool's MCP configuration documentation for exact file locations and formats.

---

## MCP Tools Reference

CVC exposes the following tools via MCP:

### 1. `cvc_set_workspace`

**Purpose**: Set or change the workspace/project directory for CVC operations.

**Parameters**:
- `path` (string, required): Absolute path to the workspace directory

**Example**:
```json
{
  "tool": "cvc_set_workspace",
  "arguments": {
    "path": "E:\\Projects\\my-awesome-app"
  }
}
```

**Response**:
```json
{
  "success": true,
  "workspace": "E:\\Projects\\my-awesome-app",
  "message": "Workspace set to: E:\\Projects\\my-awesome-app",
  "cvc_initialized": true
}
```

**When to use**:
- When switching between multiple projects
- First time using CVC in a new project
- When automatic workspace detection fails

---

### 2. `cvc_status`

**Purpose**: Show current CVC status: active branch, HEAD commit, context size, and list of all branches.

**Parameters**: None

**Example**:
```json
{
  "tool": "cvc_status",
  "arguments": {}
}
```

**Response**:
```json
{
  "agent_id": "sofia",
  "active_branch": "main",
  "head_hash": "60ad7bef4cce",
  "context_size": 2,
  "branches": [
    {
      "name": "main",
      "head": "60ad7bef4cce",
      "status": "active"
    },
    {
      "name": "experimental",
      "head": "a1b2c3d4e5f6",
      "status": "active"
    }
  ]
}
```

**When to use**:
- Check current branch before making changes
- See how many messages are in the context window
- List all available branches

---

### 3. `cvc_capture_context`

**Purpose**: Capture specific messages into CVC's context window and commit them immediately.

**Parameters**:
- `messages` (array, required): Array of message objects with `role` and `content`
- `commit_message` (string, required): Commit message describing the snapshot

**Example**:
```json
{
  "tool": "cvc_capture_context",
  "arguments": {
    "messages": [
      {
        "role": "user",
        "content": "How do I implement async functions in Python?"
      },
      {
        "role": "assistant",
        "content": "Here's how to use async/await in Python..."
      }
    ],
    "commit_message": "Captured Python async conversation"
  }
}
```

**Response**:
```json
{
  "success": true,
  "captured_messages": 2,
  "new_context_size": 2,
  "commit_hash": "fcad7600ba23",
  "message": "Captured 2 messages into CVC context."
}
```

**When to use**:
- Save important conversation snapshots
- Create checkpoints before risky operations
- Archive successful solutions for later reference

---

### 4. `cvc_commit`

**Purpose**: Create a commit (checkpoint) of the current context window.

**Parameters**:
- `message` (string, required): Commit message

**Example**:
```json
{
  "tool": "cvc_commit",
  "arguments": {
    "message": "Implemented user authentication system"
  }
}
```

**Response**:
```json
{
  "success": true,
  "operation": "commit",
  "commit_hash": "60ad7bef4ccea3b35e9336ab44e90187fa53b63ebebba3fcaf2bd4270c7f1291",
  "branch": "main",
  "message": "Committed 60ad7bef4cce: Implemented user authentication system"
}
```

**When to use**:
- Save progress at logical milestones
- Create restore points before experiments
- Document important decision points

---

### 5. `cvc_get_context`

**Purpose**: Retrieve the current context or a specific commit's conversation history.

**Parameters**:
- `commit_hash` (string, optional): Specific commit to retrieve (omit for current HEAD)
- `limit` (integer, optional): Maximum number of messages to return (default: 50)
- `full` (boolean, optional): Return full message content vs previews (default: true)

**Example - Current Context**:
```json
{
  "tool": "cvc_get_context",
  "arguments": {
    "full": true,
    "limit": 10
  }
}
```

**Example - Historical Commit**:
```json
{
  "tool": "cvc_get_context",
  "arguments": {
    "commit_hash": "fcad7600ba23",
    "full": true
  }
}
```

**Response**:
```json
{
  "success": true,
  "source": "database",
  "commit_hash": "fcad7600ba23",
  "full_hash": "fcad7600ba23e8ef6599905c3a61562df9d37f90a0fbd6f24d8743ccd087634e",
  "commit_message": "Captured Python async conversation",
  "commit_type": "checkpoint",
  "timestamp": 1771311945.7544057,
  "message_count": 2,
  "total_messages": 2,
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "How do I implement async functions in Python?",
      "character_count": 45
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "Here's how to use async/await in Python...",
      "character_count": 198
    }
  ]
}
```

**When to use**:
- Review what was discussed in previous commits
- Retrieve month-old conversations from the database
- Audit conversation history
- Compare different conversation branches

---

### 6. `cvc_log`

**Purpose**: Show commit history for the current branch.

**Parameters**:
- `limit` (integer, optional): Maximum number of commits to show (default: 10)
- `branch` (string, optional): Branch to show history for (default: current branch)

**Example**:
```json
{
  "tool": "cvc_log",
  "arguments": {
    "limit": 5
  }
}
```

**Response**:
```json
{
  "branch": "main",
  "commits": [
    {
      "hash": "60ad7bef4ccea3b35e9336ab44e90187fa53b63ebebba3fcaf2bd4270c7f1291",
      "short": "60ad7bef4cce",
      "type": "checkpoint",
      "message": "Implemented user authentication system",
      "timestamp": 1771311959.925535,
      "parents": ["fcad7600ba23e8ef6599905c3a61562df9d37f90a0fbd6f24d8743ccd087634e"],
      "is_delta": true
    },
    {
      "hash": "fcad7600ba23e8ef6599905c3a61562df9d37f90a0fbd6f24d8743ccd087634e",
      "short": "fcad7600ba23",
      "type": "checkpoint",
      "message": "Captured Python async conversation",
      "timestamp": 1771311945.7544057,
      "parents": ["50e89273681f5450456d975f20fb8de96f6c61f9225f3994aa59b6b6b6fba436"],
      "is_delta": true
    }
  ]
}
```

**When to use**:
- View project history
- Find specific commits by message
- Audit when changes were made
- Understand conversation evolution

---

### 7. `cvc_branch`

**Purpose**: Create a new branch from the current commit.

**Parameters**:
- `name` (string, required): Name for the new branch

**Example**:
```json
{
  "tool": "cvc_branch",
  "arguments": {
    "name": "experimental-refactor"
  }
}
```

**Response**:
```json
{
  "success": true,
  "operation": "branch",
  "commit_hash": "60ad7bef4ccea3b35e9336ab44e90187fa53b63ebebba3fcaf2bd4270c7f1291",
  "branch": "experimental-refactor",
  "message": "Created and switched to branch 'experimental-refactor'",
  "detail": {
    "parent_branch": "main",
    "source_commit": "60ad7bef4ccea3b35e9336ab44e90187fa53b63ebebba3fcaf2bd4270c7f1291"
  }
}
```

**When to use**:
- Try risky experiments without affecting main conversation
- Explore alternative approaches
- Create parallel conversation threads
- Isolate specific topics

---

### 8. `cvc_restore`

**Purpose**: Restore the context window to a previous commit (time-travel).

**Parameters**:
- `commit_hash` (string, required): Hash of the commit to restore to

**Example**:
```json
{
  "tool": "cvc_restore",
  "arguments": {
    "commit_hash": "fcad7600ba23"
  }
}
```

**Response**:
```json
{
  "success": true,
  "operation": "restore",
  "commit_hash": "fcad7600ba23e8ef6599905c3a61562df9d37f90a0fbd6f24d8743ccd087634e",
  "branch": "main",
  "message": "Restored to fcad7600ba23",
  "detail": {
    "restored_commit": "fcad7600ba23e8ef6599905c3a61562df9d37f90a0fbd6f24d8743ccd087634e",
    "rollback_commit": "4a62d6d57177ec794be369e5de4925154c7cd23ba31066c274967668d0440e4f",
    "token_count": 0
  }
}
```

**When to use**:
- Undo mistakes in conversation
- Go back to working state before errors
- Explore "what if" scenarios
- Recover from infinite loops or confusion

---

### 9. `cvc_merge`

**Purpose**: Merge another branch into the current branch.

**Parameters**:
- `source_branch` (string, required): Name of the branch to merge from

**Example**:
```json
{
  "tool": "cvc_merge",
  "arguments": {
    "source_branch": "experimental-refactor"
  }
}
```

**Response**:
```json
{
  "success": true,
  "operation": "merge",
  "commit_hash": "70ec4ce7881656ba34fdd49c95faa1c2f41aa426f79c422ac7f398e47ef39728",
  "branch": "main",
  "message": "Merged 'experimental-refactor' into 'main'",
  "detail": {
    "lca": "60ad7bef4ccea3b35e9336ab44e90187fa53b63ebebba3fcaf2bd4270c7f1291",
    "source_head": "a1b2c3d4e5f6",
    "target_head": "60ad7bef4cce"
  }
}
```

**When to use**:
- Bring successful experiments back to main conversation
- Combine insights from parallel conversation threads
- Integrate solutions found in branches
- Consolidate context

---

## Multi-Workspace Support

CVC supports working with **multiple projects simultaneously**. Each project gets its own independent `.cvc/` database folder.

### Automatic Workspace Detection

CVC automatically detects your workspace using these strategies (in priority order):

1. **Explicit override** via `cvc_set_workspace` tool
2. **CVC_WORKSPACE** environment variable (optional)
3. **IDE-specific env vars** (CODEX_WORKSPACE_ROOT, PROJECT_ROOT, WORKSPACE_FOLDER)
4. **Workspace markers** - walks up from current directory to find:
   - `.cvc/` folder (existing CVC project)
   - `.git/` folder (Git repository)
   - `pyproject.toml` (Python project)
   - `package.json` (Node.js project)
5. **Fallback to current directory** (with warning)

### Multi-Workspace Workflow

#### Scenario: Working with Multiple Projects

You have three projects:
```
Projects/
├── web-app/          (React project)
├── backend-api/      (Python FastAPI)
└── mobile-app/       (Flutter)
```

**Workflow**:

1. **Open first project in IDE** (e.g., `web-app`)
2. **Set workspace** via Copilot/Cascade:
   ```
   Use cvc_set_workspace to set workspace to E:\Projects\web-app
   ```
3. **Work on web-app**, CVC saves to `web-app/.cvc/`

4. **Switch to second project** (e.g., `backend-api`)
5. **Set new workspace**:
   ```
   Use cvc_set_workspace to set workspace to E:\Projects\backend-api
   ```
6. **Work on backend-api**, CVC now saves to `backend-api/.cvc/`

Each project has **completely independent**:
- Conversation history
- Branches
- Commits
- Context windows

### Best Practices for Multi-Workspace

✅ **DO**:
- Keep workspace markers (`.git`, `pyproject.toml`) in your projects
- Use `cvc_set_workspace` when switching projects
- Let each project have its own `.cvc/` folder
- Commit important conversations before switching workspaces

❌ **DON'T**:
- Don't use `CVC_WORKSPACE` env var in `mcp.json` (breaks multi-workspace)
- Don't share `.cvc/` folders across projects
- Don't delete `.cvc/` folders (contains your conversation history)

See [MULTI_WORKSPACE.md](MULTI_WORKSPACE.md) for detailed documentation.

---

## Configuration Examples

### Minimal Configuration (Recommended)

**File**: `mcp.json`

```json
{
  "servers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio"
    }
  },
  "inputs": []
}
```

This configuration:
- ✅ Works with all projects
- ✅ Auto-detects workspace per project
- ✅ Supports multi-workspace workflows
- ✅ No hardcoded paths

---

### Single-Project Configuration (Not Recommended)

**Only use this if you work exclusively in ONE project**.

**File**: `mcp.json`

```json
{
  "servers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio",
      "env": {
        "CVC_WORKSPACE": "E:\\Projects\\my-main-project"
      }
    }
  },
  "inputs": []
}
```

⚠️ **Warning**: This locks CVC to a single workspace. Other projects will share the same `.cvc/` folder.

---

### HTTP/SSE Transport (Advanced)

For network-based MCP clients:

```bash
# Start MCP server with HTTP/SSE transport
cvc mcp --transport sse --host 127.0.0.1 --port 8080
```

**Client Configuration**:
```json
{
  "servers": {
    "cvc": {
      "url": "http://127.0.0.1:8080/sse",
      "type": "sse"
    }
  }
}
```

---

## Usage Examples

### Example 1: First-Time Setup

**User**: "Set up CVC for this project."

**AI Assistant** (automatically):
1. Calls `cvc_set_workspace` with current project path
2. CVC creates `.cvc/` folder with database
3. Confirms workspace initialized

**Result**:
```
✅ Workspace set to: E:\Projects\my-app
✅ CVC initialized (Genesis commit created)
```

---

### Example 2: Saving Progress

**User**: "Save this conversation about the authentication system."

**AI Assistant** (automatically):
1. Calls `cvc_commit` with descriptive message
2. CVC creates checkpoint with current context

**Result**:
```
✅ Committed 60ad7bef4cce: Authentication system implementation
📊 Context size: 12 messages
```

---

### Example 3: Time Travel

**User**: "Go back to before we broke the API."

**AI Assistant** (automatically):
1. Calls `cvc_log` to find relevant commit
2. Identifies commit hash from before the issue
3. Calls `cvc_restore` to rewind context

**Result**:
```
✅ Restored to fcad7600ba23: Working API before refactor
🔄 Rollback commit created for undo: 4a62d6d5
```

---

### Example 4: Branching Experiments

**User**: "Let's try a risky refactor, but keep our current work safe."

**AI Assistant** (automatically):
1. Calls `cvc_commit` to save current state
2. Calls `cvc_branch` with name like "refactor-experiment"
3. Proceeds with experimental changes

**User** (later): "That worked! Merge it back."

**AI Assistant**:
1. Switches back to main branch
2. Calls `cvc_merge` to bring in changes

**Result**:
```
✅ Created branch 'refactor-experiment'
... experiment happens ...
✅ Merged 'refactor-experiment' into 'main'
```

---

### Example 5: Multi-Workspace Switch

**User**: "I need to work on the mobile app now."

**AI Assistant** (automatically):
1. Calls `cvc_set_workspace` with mobile app path
2. CVC switches to mobile app's `.cvc/` database
3. Loads last commit from mobile app history (auto-restore)

**Result**:
```
✅ Workspace set to: E:\Projects\mobile-app
📂 Auto-restored 8 messages from last commit
🌿 Branch: main, HEAD: a1b2c3d4
```

---

### Example 6: Retrieving Old Conversations

**User**: "What did we discuss about database optimization last month?"

**AI Assistant** (automatically):
1. Calls `cvc_log` to search commit history
2. Finds commit with "database optimization" in message
3. Calls `cvc_get_context` with that commit hash
4. Retrieves full conversation from database

**Result**:
```
📜 Found commit fcad7600ba23 from 30 days ago
💬 Retrieved 15 messages about database indexing and query optimization
```

---

## Troubleshooting

### Issue: "Could not detect workspace reliably"

**Cause**: MCP server can't find workspace markers in your project.

**Solutions**:
1. **Manual override**: Ask AI to call `cvc_set_workspace` with your project path
2. **Add markers**: Create `.git` folder (`git init`) or add `pyproject.toml`/`package.json`
3. **Check cwd**: Ensure VS Code opened the project folder (not a parent directory)

---

### Issue: Wrong workspace detected

**Cause**: Multiple nested projects or workspace markers in parent directories.

**Solution**:
Ask AI to explicitly set the correct workspace:
```
Use cvc_set_workspace to set workspace to E:\Projects\correct-project
```

---

### Issue: MCP tools not showing up

**Cause**: MCP configuration not loaded or CVC not installed.

**Solutions**:
1. **Verify installation**: Run `cvc --version` in terminal
2. **Check mcp.json**: Ensure file exists and has correct syntax
3. **Reload IDE**: Restart VS Code/Windsurf/Antigravity
4. **Check logs**: Look for MCP errors in IDE developer console

---

### Issue: Multiple projects sharing same `.cvc/` folder

**Cause**: `CVC_WORKSPACE` env var hardcoded in `mcp.json`.

**Solution**:
Remove the `env` section from `mcp.json`:
```json
{
  "servers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio"
      // ❌ Remove the "env" section
    }
  }
}
```

Then manually set workspace per project using `cvc_set_workspace`.

---

### Issue: Context not persisting across restarts

**Cause**: Auto-restore might not be loading the last commit.

**Solutions**:
1. **Check for commits**: Ask AI to call `cvc_log` to verify commits exist
2. **Manual restore**: Ask AI to call `cvc_restore` with specific commit hash
3. **Verify database**: Check that `.cvc/cvc.db` file exists and has recent timestamp

---

### Issue: "Permission denied" on `.cvc/` folder

**Cause**: File permissions or antivirus blocking database access.

**Solutions**:
1. **Check permissions**: Ensure you have write access to project directory
2. **Antivirus exclusion**: Add `.cvc/` folder to antivirus whitelist
3. **Run as admin**: Try running IDE with administrator privileges (Windows)

---

## Best Practices

### 1. Workspace Management

✅ **Best Practice**: Use automatic workspace detection with markers (`.git`, `pyproject.toml`)
```bash
# Initialize Git in your project
cd my-project
git init
```

✅ **Best Practice**: Explicitly set workspace when switching projects
```
Use cvc_set_workspace to set workspace to E:\Projects\new-project
```

❌ **Avoid**: Hardcoding workspace in global `mcp.json`

---

### 2. Committing

✅ **Best Practice**: Commit at logical milestones
```
Commit this conversation about implementing user authentication
```

✅ **Best Practice**: Use descriptive commit messages
```
"Implemented JWT auth with refresh tokens and rate limiting"
```

❌ **Avoid**: Committing too frequently (every message) - clutters history

---

### 3. Branching

✅ **Best Practice**: Branch before risky experiments
```
Create a branch called 'experimental-refactor' before we try this
```

✅ **Best Practice**: Merge successful branches back to main
```
That worked! Merge the experimental branch back to main
```

❌ **Avoid**: Too many abandoned branches - clean up with CLI later

---

### 4. Time Travel

✅ **Best Practice**: Use `cvc_log` to find the right commit before restoring
```
Show me the commit history, I want to go back to the working version
```

✅ **Best Practice**: Commit current work before restoring to avoid losing progress
```
Commit this first, then restore to the previous commit
```

❌ **Avoid**: Restoring without knowing what commit you're going to

---

### 5. Multi-Workspace

✅ **Best Practice**: Set workspace explicitly when switching projects
```
I'm switching to the mobile app project now, set workspace to E:\Projects\mobile-app
```

✅ **Best Practice**: Keep related conversations in the same workspace
```
# All web-app discussions → web-app/.cvc/
# All backend discussions → backend/.cvc/
```

❌ **Avoid**: Mixing unrelated projects in the same `.cvc/` database

---

### 6. Context Retrieval

✅ **Best Practice**: Use `cvc_get_context` to review old conversations
```
What did we discuss about database optimization in commit fcad7600ba23?
```

✅ **Best Practice**: Use `limit` parameter to avoid overwhelming context
```
Show me just the last 5 messages from that commit
```

❌ **Avoid**: Retrieving entire commit history at once (slow, overwhelming)

---

## Advanced Features

### Auto-Restore on Startup

CVC automatically restores your last conversation when the MCP server starts:

1. **VS Code restarts** → MCP server reloads
2. **CVC auto-restore** → Loads HEAD commit or persistent cache
3. **Context restored** → Continue where you left off

**No manual action needed!** Your conversation history persists across IDE restarts.

---

### Persistent Cache

CVC saves a persistent cache file (`.cvc/context_cache.json`) on every message push:

- **Survives crashes**: Even if you force-quit the IDE
- **Automatic recovery**: Loaded if database commits don't exist yet
- **Non-blocking**: Cache writes don't slow down conversations

**You don't need to do anything** - it works automatically.

---

### Database-Backed History

All commits are stored in a SQLite database (`.cvc/cvc.db`):

- **Infinite retention**: Retrieve conversations from months ago
- **Full content**: Messages stored in content-addressable blobs
- **Fast queries**: Indexed by commit hash, timestamp, branch
- **Local-first**: No cloud required, your data stays on your machine

---

### Cross-Mode Compatibility

The same `.cvc/` database works across all CVC modes:

- **MCP Server** (VS Code, Windsurf, Antigravity)
- **Proxy Mode** (Continue.dev, Cline, Cursor)
- **CLI Agent** (`cvc` command)

Build context in MCP, analyze it in CLI, use it in Proxy - all seamlessly!

---

## Version Information

**Current Version**: 1.4.1  
**Release Date**: February 17, 2026  
**MCP Protocol Version**: 1.0  
**Transport Types**: stdio, HTTP/SSE

---

## Additional Resources

- **Main Documentation**: [README.md](README.md)
- **Multi-Workspace Guide**: [MULTI_WORKSPACE.md](MULTI_WORKSPACE.md)
- **Persistence Architecture**: [VERIFICATION.md](VERIFICATION.md)
- **Testing Guide**: [CLI_TEST.md](CLI_TEST.md)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **PyPI Package**: [tm-ai](https://pypi.org/project/tm-ai/)
- **GitHub Repository**: [AI-Cognitive-Version-Control](https://github.com/mannuking/AI-Cognitive-Version-Control)

---

## Support

For issues, feature requests, or contributions:

- **GitHub Issues**: [Create an issue](https://github.com/mannuking/AI-Cognitive-Version-Control/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mannuking/AI-Cognitive-Version-Control/discussions)

---

## License

MIT License - See [LICENSE](LICENSE) file for details

---

**Last Updated**: February 17, 2026  
**Document Version**: 1.4.1
