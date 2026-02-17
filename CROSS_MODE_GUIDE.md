# Cross-Mode Interoperability Guide

CVC provides **three ways** to interact with your cognitive version control system, and they all share the same `.cvc/` database seamlessly. This means you can start a conversation in one mode and continue it in another—**it's the same brain, three different interfaces**.

---

## The Three Modes

### 1. **MCP (Model Context Protocol)** — IDE Integration
- **Use Case**: Chat with AI directly in VS Code, Cursor, Windsurf, or other MCP-compatible IDEs
- **How**: Configure `mcp.json` in your editor's settings
- **When**: You want AI assistance while coding, with full IDE context
- **Auto-Restore**: ✅ Yes — restores last commit on IDE restart

### 2. **Proxy** — Standalone API Server
- **Use Case**: Use with Continue.dev, Cline, or any OpenAI-compatible client
- **How**: Run `cvc proxy` to start FastAPI server on `http://localhost:8000`
- **When**: You want flexibility to use multiple AI clients or custom integrations
- **Auto-Restore**: ✅ Yes — restores last commit on server startup

### 3. **CLI Agent** — Interactive Terminal
- **Use Case**: Chat with AI in your terminal, with 26 slash commands and Git integration
- **How**: Run `cvc` in any project directory
- **When**: You want a powerful AI assistant with Time Machine features and branching
- **Auto-Restore**: ✅ Yes — restores last commit or cache on launch

---

## How Cross-Mode Works

All three modes share:
- **Same `.cvc/` folder** — One database per project
- **Same commits** — All sessions are stored in the same Merkle DAG
- **Same branches** — Work across modes seamlessly
- **Same context** — Conversations persist regardless of which mode created them

### Under the Hood

When you switch modes, CVC:
1. **Detects the mode transition** (logs "🔄 Cross-mode restore")
2. **Loads the last commit** from whichever mode created it
3. **Continues the conversation** exactly where you left off
4. **Tracks the new mode** in subsequent commits

---

## Real-World Workflows

### Scenario 1: MCP → CLI
**Situation**: You're chatting with Copilot in VS Code (MCP), but need to switch to terminal work.

```bash
# In VS Code with MCP
User: "Help me refactor this auth module"
Copilot: [provides refactoring steps]
# You commit the conversation

# Later, in terminal
$ cvc
🔄 Cross-mode restore: 8 messages from MCP → CLI (commit a3f2b1c9)
User: /continue
# Conversation continues seamlessly
```

### Scenario 2: CLI → Proxy → MCP
**Situation**: Multi-device workflow across different tools.

```bash
# On laptop in terminal (CLI)
$ cvc
User: "Design a new feature for user profiles"
AI: [designs feature architecture]
User: /commit Feature design complete
# Commit a7b3c2d1 created

# On desktop with Continue.dev (Proxy)
$ cvc proxy
🔄 Cross-mode restore: 12 messages from CLI → PROXY (commit a7b3c2d1)
# Continue.dev sees the same conversation

# Back to laptop in VS Code (MCP)
# MCP auto-restores on IDE restart
🔄 Cross-mode restore: 18 messages from PROXY → MCP (commit e4f1a8b2)
# Full conversation history preserved
```

### Scenario 3: Parallel Development
**Situation**: Team collaboration or multi-project workflows.

```bash
# Developer A uses MCP in VS Code
# Creates branch "feature/auth"
# Commits conversation about auth implementation

# Developer B uses CLI
$ cvc
$ /branch feature/auth
$ /restore <commit-hash>
🔄 Cross-mode restore: 15 messages from MCP → CLI (commit xyz)
# Developer B can see and continue A's work
```

---

## Mode-Specific Features

### What's Shared Across All Modes
- ✅ All commits and branches
- ✅ Context window and message history
- ✅ Git integration and file tracking
- ✅ Provider and model configuration
- ✅ Auto-restore on restart
- ✅ Persistent cache for crash recovery

### Mode-Unique Features

#### MCP Only
- 🎯 IDE workspace context (automatic file discovery)
- 🎯 VS Code/Cursor/Windsurf integration
- 🎯 Real-time code context injection

#### Proxy Only
- 🎯 OpenAI-compatible API endpoints
- 🎯 SSE streaming for real-time responses
- 🎯 Multi-client support (Continue.dev, Cline, etc.)

#### CLI Only
- 🎯 26 interactive slash commands (`/commit`, `/branch`, `/diff`, etc.)
- 🎯 Rich terminal UI with syntax highlighting
- 🎯 Time Machine visualization
- 🎯 Interactive restore prompts
- 🎯 Cost tracking and analytics

---

## Best Practices

### 1. **Choose the Right Mode for the Task**
- **Coding in IDE** → MCP (best IDE integration)
- **API/scripting** → Proxy (most flexible)
- **Git workflows** → CLI (most features)

### 2. **Commit Often**
Commits are visible across all modes:
```bash
# In CLI
User: /commit Major refactoring complete

# In MCP
User: @cvc_commit "Added test coverage"

# All commits appear in:
$ cvc log
```

### 3. **Use Branches for Experiments**
Branches work seamlessly across modes:
```bash
# Create branch in CLI
$ cvc
User: /branch feature/experimental

# Switch to it in MCP
User: @cvc_log  # Shows all branches
User: @cvc_restore <branch-head-commit>

# Merge in Proxy (via Continue.dev)
User: Merge feature/experimental into main
AI: [uses @cvc_merge tool]
```

### 4. **Trust the Auto-Restore**
All modes automatically restore your last session:
- **MCP**: On IDE restart
- **Proxy**: On server startup
- **CLI**: On `cvc` launch

If you see "🔄 Cross-mode restore", it means you're **continuing a conversation from a different mode**—this is normal and expected!

### 5. **Check Mode History**
Want to see which mode created each commit?

```bash
$ cvc log --verbose
# Shows metadata including mode field:
# - mode: mcp
# - mode: proxy
# - mode: cli
```

---

## Troubleshooting

### "Cross-mode restore failed"
**Cause**: Database corruption or commit missing.

**Fix**:
```bash
# Check database integrity
$ cvc status

# If corrupted, restore from last good commit
$ cvc
User: /restore <last-good-commit-hash>
```

### "Mode mismatch warnings"
**Cause**: You switched modes mid-conversation.

**Fix**: This is **not an error**! CVC is designed for cross-mode workflows. The warning is informational only.

### "Context window size different across modes"
**Cause**: Different auto-commit intervals in each mode.

**Explanation**:
- **MCP**: Manual commits (user-triggered)
- **Proxy**: Auto-commits every 1-3 turns
- **CLI**: Auto-commits every 2 turns

**Fix**: Commit manually in MCP using `@cvc_commit` to keep contexts aligned.

---

## Technical Details

### Metadata Tracking
Every commit stores which mode created it:

```python
# CommitMetadata schema
{
    "timestamp": 1234567890.0,
    "agent_id": "sofia",
    "mode": "cli",  # or "mcp" or "proxy"
    "provider": "anthropic",
    "model": "claude-opus-4-6",
    "git_commit_sha": "abc123...",
    "tags": ["feature-design"]
}
```

### Auto-Restore Priority
All modes follow the same restoration logic:

1. **Last committed context** from database (highest priority)
2. **Persistent cache** (if crash before commit)
3. **Empty state** (new session)

### Cross-Mode Detection
When restoring, CVC compares:
- `config.mode` (current mode)
- `commit.metadata.mode` (previous mode)

If they differ → "🔄 Cross-mode restore" log appears.

---

## Architectural Guarantees

CVC's cross-mode interoperability is **guaranteed** by:

1. **Single source of truth**: All modes read/write to `.cvc/cvc.db`
2. **Content-addressable storage**: Blobs in `.cvc/objects/` are immutable
3. **Merkle DAG**: Commits have cryptographic hashes preventing conflicts
4. **Atomic transactions**: SQLite ensures database consistency
5. **Mode-agnostic schema**: Database structure is identical across modes

---

## Summary

**One `.cvc/` folder = Three access modes**

| Feature | MCP | Proxy | CLI |
|---------|-----|-------|-----|
| Auto-Restore | ✅ | ✅ | ✅ |
| Cross-Mode Support | ✅ | ✅ | ✅ |
| Shared Commits | ✅ | ✅ | ✅ |
| Shared Branches | ✅ | ✅ | ✅ |
| Mode Tracking | ✅ | ✅ | ✅ |
| Interactive Commands | ❌ | ❌ | ✅ |
| IDE Integration | ✅ | ❌ | ❌ |
| API Server | ❌ | ✅ | ❌ |

**The golden rule**: Use whichever mode fits your workflow—CVC ensures they all work together seamlessly.

---

## Examples

### Full Cross-Mode Workflow
```bash
# Day 1: Start in CLI
$ cvc
User: "Help me design a new authentication system"
AI: [provides design]
User: /commit Auth design v1
# Commit: d4e5f6a7 (mode: cli)

# Day 2: Continue in VS Code with MCP
# MCP auto-restores on IDE startup
🔄 Cross-mode restore: 10 messages from CLI → MCP (commit d4e5f6a7)
User: "Implement the login endpoint"
AI: [writes code]
# Auto-commit via Copilot
# Commit: g7h8i9j0 (mode: mcp)

# Day 3: Test with Proxy + Continue.dev
$ cvc proxy
🔄 Cross-mode restore: 24 messages from MCP → PROXY (commit g7h8i9j0)
# Continue.dev sends request to http://localhost:8000
User: "Write tests for the auth system"
AI: [generates tests]
# Commit: k1l2m3n4 (mode: proxy)

# Day 4: Back to CLI for deployment
$ cvc
🔄 Cross-mode restore: 35 messages from PROXY → CLI (commit k1l2m3n4)
User: /log
# Shows full history across all three modes
User: /git commit -m "Auth system complete with tests"
# Links CVC conversation to Git commit
```

**Result**: One seamless conversation across three different tools, all tracked in `.cvc/`—no data loss, full continuity.

---

## Related Documentation
- [MCP_DOCUMENTATION.md](./MCP_DOCUMENTATION.md) — Full MCP server setup guide
- [CLI_AGENT_GUIDE.md](./CLI_AGENT_GUIDE.md) — Complete CLI features reference
- [README.md](./README.md) — General CVC overview
- [MULTI_WORKSPACE.md](./MULTI_WORKSPACE.md) — Multi-project workflows

---

**Version**: 1.4.4  
**Last Updated**: February 2026  
**Compatibility**: All CVC modes (MCP, Proxy, CLI)
