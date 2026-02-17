# CLI Agent Mode Test Plan

## 🎯 Goal: Verify persistence works perfectly in CLI mode

### Test Scenario 1: Auto-Initialization
```bash
# Create a fresh test directory
mkdir E:\test-cvc-cli
cd E:\test-cvc-cli

# Start agent (should auto-create .cvc/)
cvc agent

# Expected:
# ✓ Auto-creates .cvc/ folder
# ✓ Shows "CVC initialized" message
# ✓ Starts with empty context
```

### Test Scenario 2: Persistent Cache (Crash Recovery)
```bash
# Start agent
cvc agent

# Send a few messages
> Hello, this is a test message
> Let's see if this survives a crash

# FORCE-QUIT (Ctrl+C or close terminal)

# Check cache file exists
cat .cvc/context_cache.json

# Expected:
# ✓ File exists with your messages
# ✓ Contains full conversation JSON

# Restart agent
cvc agent

# Expected:
# ✓ Shows "Loaded N messages from persistent cache"
# ✓ Context restored with your messages
```

### Test Scenario 3: Auto-Commit + Auto-Restore
```bash
# Start agent
cvc agent

# Send exactly 5 messages (triggers auto-commit)
> Message 1
> Message 2
> Message 3
> Message 4
> Message 5

# Expected:
# ✓ After 5th assistant response: "Auto-commit: abc123..."

# Exit cleanly
> /exit

# Restart agent
cvc agent

# Expected:
# ✓ Shows "Auto-restored N messages from commit abc123"
# ✓ Context contains all 10 messages (5 user + 5 assistant)
```

### Test Scenario 4: Manual Commit
```bash
# Start agent
cvc agent

> Test message before manual commit

# Manual commit
> /commit

# Expected:
# ✓ Prompts for commit message
# ✓ Creates commit successfully
# ✓ Shows commit hash
```

### Test Scenario 5: View History
```bash
# After multiple commits
cvc agent

> /log

# Expected:
# ✓ Shows all commits with hashes
# ✓ Shows commit messages
# ✓ Shows timestamps
```

### Test Scenario 6: Time-Travel (Restore)
```bash
# Start agent
cvc agent

> /log

# Copy a commit hash from the log

> /restore abc123

# Expected:
# ✓ Loads that old conversation
# ✓ Context window contains old messages
# ✓ Creates rollback commit
# ✓ Shows "Context restored to abc123"
```

### Test Scenario 7: Cross-Mode Verification
```bash
# 1. Create commit in CLI
cvc agent
> /commit "CLI commit test"
> /exit

# 2. Check from MCP (GitHub Copilot)
@cvc /cvc_log

# Expected:
# ✓ Shows the CLI commit in the log
# ✓ Can retrieve via @cvc /cvc_get_context

# 3. Check from Proxy
curl http://127.0.0.1:8000/cvc/log

# Expected:
# ✓ Shows the CLI commit
# ✓ All modes share the same .cvc/ database
```

## 📊 Success Criteria

All tests must pass:
- [x] Auto-creates `.cvc/` on first run
- [x] Saves to `.cvc/context_cache.json` on every message
- [x] Cache survives crashes
- [x] Auto-commits at configured interval
- [x] Auto-restores on startup
- [x] Manual `/commit` works
- [x] `/log` shows all history
- [x] `/restore` time-travels correctly
- [x] Database shared across all 3 modes

## 🚀 Run the Test

```bash
cd "E:\Projects\AI Cognitive Version Control"

# Install latest version
pip install -e .

# Start CLI agent
cvc agent

# Follow test scenarios above
```

