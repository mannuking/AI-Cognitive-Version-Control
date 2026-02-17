# Multi-Workspace Support in CVC

## Overview

CVC is designed to work across **multiple projects** simultaneously. Each project gets its own `.cvc/` folder with independent conversation history, branches, and time-travel capabilities.

## How It Works

### Automatic Workspace Detection

CVC automatically detects your workspace using these strategies (in priority order):

1. **Explicit override via `cvc_set_workspace` tool** (recommended for multi-workspace)
2. **CVC_WORKSPACE environment variable** (optional, for single-project setups)
3. **IDE-specific env vars** (CODEX_WORKSPACE_ROOT, PROJECT_ROOT, WORKSPACE_FOLDER)
4. **Workspace markers** - walks up from cwd to find:
   - `.cvc/` (existing CVC project)
   - `.git/` (Git repository)
   - `pyproject.toml` (Python project)
   - `package.json` (Node.js project)
5. **Fallback to cwd** (with warning to use `cvc_set_workspace`)

### Each Project Gets Its Own `.cvc/` Folder

```
Projects/
├── project-a/
│   ├── .git/
│   ├── .cvc/                    # Independent CVC history
│   │   ├── cvc.db
│   │   ├── objects/
│   │   └── branches/
│   └── src/
│
├── project-b/
│   ├── .git/
│   ├── .cvc/                    # Different CVC history
│   │   ├── cvc.db
│   │   ├── objects/
│   │   └── branches/
│   └── index.js
│
└── project-c/
    ├── pyproject.toml
    ├── .cvc/                    # Yet another independent history
    │   ├── cvc.db
    │   ├── objects/
    │   └── branches/
    └── main.py
```

## Usage

### Option 1: Automatic Detection (Recommended for Most Users)

Ensure your projects have workspace markers:
- ✅ Git repository (`.git/` folder)
- ✅ Python project (`pyproject.toml`)
- ✅ Node.js project (`package.json`)
- ✅ Existing CVC project (`.cvc/` folder)

CVC will automatically detect and use the correct workspace!

### Option 2: Manual Workspace Switching (Multi-Workspace Power Users)

When working with multiple projects in VS Code, explicitly set the workspace:

```json
// Call this MCP tool when switching projects:
{
  "tool": "cvc_set_workspace",
  "arguments": {
    "path": "e:\\Projects\\project-a"
  }
}
```

**Example workflow:**
1. Open `project-a` in VS Code
2. Call `cvc_set_workspace` with `project-a` path
3. Work with CVC (captures context to `project-a/.cvc/`)
4. Switch to `project-b` in VS Code
5. Call `cvc_set_workspace` with `project-b` path
6. Work with CVC (now captures to `project-b/.cvc/`)

### Option 3: Environment Variable (Single Project)

If you work primarily in one project, set the env var ONCE in your MCP config:

```json
// C:\Users\<username>\AppData\Roaming\Code\User\mcp.json
{
  "servers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "type": "stdio",
      "env": {
        "CVC_WORKSPACE": "e:\\Projects\\my-main-project"
      }
    }
  }
}
```

⚠️ **Warning**: This locks CVC to ONE project. Other projects will share the same `.cvc/` folder (not recommended).

## Best Practices

### ✅ DO:
- Keep workspace markers (`.git`, `pyproject.toml`) in your projects
- Use `cvc_set_workspace` when switching between projects
- Let each project have its own `.cvc/` folder
- Use auto-commit intervals to save context automatically

### ❌ DON'T:
- Don't use `CVC_WORKSPACE` env var for multi-workspace setups
- Don't share `.cvc/` folders across multiple projects
- Don't delete `.cvc/` folders (contains your conversation history!)

## Troubleshooting

### "Could not detect workspace reliably" warning

**Cause**: MCP server couldn't find workspace markers.

**Solutions**:
1. Add a `.git` folder (initialize Git)
2. Add `pyproject.toml` or `package.json`
3. Call `cvc_set_workspace` with your project path manually

### Wrong workspace detected

**Cause**: Multiple nested projects or workspace markers in parent directories.

**Solution**: Call `cvc_set_workspace` explicitly:
```json
{
  "tool": "cvc_set_workspace",
  "arguments": {
    "path": "/absolute/path/to/your/project"
  }
}
```

### Different projects sharing same `.cvc/` folder

**Cause**: `CVC_WORKSPACE` env var is hardcoded in `mcp.json`.

**Solution**: Remove the `env` section from `mcp.json` and use auto-detection or `cvc_set_workspace` instead.

## Architecture Notes

- **MCP server runs globally** (one instance for all VS Code windows)
- **Workspace detection is dynamic** (can change between operations)
- **Each `.cvc/` folder is independent** (separate SQLite databases)
- **Auto-restore loads from workspace-specific database** (no cross-project contamination)
- **Cross-workspace time-travel** works (just switch workspace first)

## Examples

### Python Project
```
my-python-app/
├── pyproject.toml          # Workspace marker ✓
├── .cvc/                   # Auto-created here
└── src/
```

### Node.js Project
```
my-node-app/
├── package.json            # Workspace marker ✓
├── .cvc/                   # Auto-created here
└── index.js
```

### Git Repository
```
any-project/
├── .git/                   # Workspace marker ✓
├── .cvc/                   # Auto-created here
└── README.md
```

### Multi-Service Monorepo
```
monorepo/
├── .git/                   # Root marker
├── .cvc/                   # Root CVC (for overall project)
├── service-a/
│   ├── .cvc/              # Service-specific CVC (call cvc_set_workspace)
│   └── pyproject.toml
└── service-b/
    ├── .cvc/              # Another service-specific CVC
    └── package.json
```

## See Also

- [README.md](README.md) - Main CVC documentation
- [VERIFICATION.md](VERIFICATION.md) - Persistence architecture deep-dive
- [CLI_TEST.md](CLI_TEST.md) - Testing instructions
