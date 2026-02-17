# MCP Server Workspace Detection: Technical Research Summary

**Date:** February 17, 2026  
**Research Focus:** How MCP servers detect and use workspace/project directory context when launched by VS Code, Cursor, Claude Code, and other IDEs.

---

## Executive Summary

MCP servers face a **fundamental workspace detection challenge**: when launched by IDEs, they often cannot reliably determine the user's working directory through standard methods like `os.getcwd()` or `process.cwd()`. This research identifies **5 mechanisms** for workspace awareness and provides **concrete implementation recommendations** for the CVC MCP server.

---

## Key Findings

### 1. Does MCP Protocol Pass Workspace Information on Initialization?

**Answer: No directly, but yes through the "roots" capability.**

The MCP protocol specification (2024-11-05 and 2025-11-25) includes a **roots capability** that allows clients to communicate filesystem boundaries:

- **Protocol Support:** Clients can declare `roots` capability during initialization
- **Discovery Method:** Servers call `roots/list` to query accessible workspace directories
- **Data Format:** Returns array of `{uri: "file:///path", name: "Display Name"}` objects
- **Dynamic Updates:** Supports `notifications/roots/list_changed` for workspace changes
- **Security First:** Roots define "safe zones" - clients control what servers can access

**Initialization Flow:**
```json
// CLIENT → SERVER: initialize request
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "roots": {
        "listChanged": true  // Client supports dynamic root updates
      }
    },
    "clientInfo": {
      "name": "VS Code",
      "version": "1.85.0"
    }
  }
}

// SERVER → CLIENT: roots/list request (if needed)
{
  "jsonrpc": "2.0", 
  "method": "roots/list"
}

// CLIENT → SERVER: roots/list response
{
  "jsonrpc": "2.0",
  "result": {
    "roots": [
      {
        "uri": "file:///home/user/projects/my-project",
        "name": "My Project"
      }
    ]
  }
}
```

**Limitation:** Not all IDE MCP clients implement roots support yet (as of Feb 2026).

---

### 2. Can MCP Servers Access Environment Variables for Workspace Context?

**Answer: Yes, but support is IDE-dependent and timing-sensitive.**

**Environment Variables Found in the Wild:**

| Variable | IDE | When Available | Reliability |
|----------|-----|----------------|-------------|
| `CODEX_WORKSPACE_ROOT` | Codex | Tool-call time only | Medium |
| `CLAUDE_CODE_CWD` | Claude Code | Not standardized (proposed) | Low |
| Custom `CVC_WORKSPACE` | User-defined | Spawn time | High (if configured) |
| `PWD` / `OLDPWD` | Shell | Spawn time | Low (IDE dependent) |

**Critical Discovery:** Environment variables are often available at **tool-call time** but NOT at **server spawn time**, especially when using package managers like `uvx` or `npx`.

**Example Issue:**
```bash
# When launched via: claude mcp add my-mcp -- uvx my-mcp
# os.getcwd() returns: ~/.cache/uv/...
# NOT the actual workspace directory!
```

**Best Practice:** Accept workspace via **both** environment variable AND explicit configuration parameter.

---

### 3. Best Practices for Workspace-Aware MCP Servers

Based on analysis of popular MCP servers (filesystem, GitHub, Serena), here are the **proven patterns**:

#### **Pattern 1: Configuration `cwd` Parameter (Highest Priority)**

Most reliable method - let the IDE configuration explicitly set the working directory:

```json
// VS Code: .vscode/mcp.json
{
  "servers": {
    "cvc": {
      "command": "uv",
      "args": ["run", "cvc", "mcp"],
      "cwd": "${workspaceFolder}",  // VS Code variable
      "env": {
        "CVC_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}

// Cursor/Windsurf: .cursor/mcp.json
{
  "mcpServers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "cwd": "/absolute/path/to/workspace",  // Must be absolute
      "env": {
        "CVC_WORKSPACE": "/absolute/path/to/workspace"
      }
    }
  }
}
```

**Current IDE Support:**
- ✅ **VS Code MCP Extension**: Supports `${workspaceFolder}` variable
- ❌ **Cursor**: Requires absolute paths (feature request #74861)
- ❌ **Windsurf**: Limited variable support
- ✅ **Claude Code CLI**: Respects `cwd` parameter

#### **Pattern 2: Environment Variable Fallback**

```python
import os
from pathlib import Path

def detect_workspace() -> Path:
    """Multi-strategy workspace detection."""
    # Strategy 1: Explicit environment variable (highest priority)
    if workspace := os.getenv("CVC_WORKSPACE"):
        return Path(workspace).resolve()
    
    # Strategy 2: IDE-specific environment variables
    if workspace := os.getenv("CODEX_WORKSPACE_ROOT"):
        return Path(workspace).resolve()
    
    # Strategy 3: Current working directory (may be wrong!)
    cwd = Path.cwd()
    
    # Strategy 4: Walk up to find project marker (.git, pyproject.toml, etc.)
    project_root = find_project_root(cwd)
    if project_root:
        return project_root
    
    # Strategy 5: Fallback to cwd
    return cwd

def find_project_root(start: Path) -> Path | None:
    """Walk up directory tree to find project root markers."""
    markers = [".git", "pyproject.toml", "package.json", ".cvc"]
    current = start.resolve()
    
    while current != current.parent:  # Stop at filesystem root
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent
    
    return None
```

#### **Pattern 3: MCP Roots Protocol Integration**

For future-proofing and advanced IDE support:

```python
async def request_workspace_roots(session) -> list[Path]:
    """Query MCP client for workspace roots."""
    try:
        result = await session.send_request(
            method="roots/list",
            params={}
        )
        roots = [
            Path(root["uri"].removeprefix("file://"))
            for root in result.get("roots", [])
        ]
        return roots
    except Exception:
        return []  # Client doesn't support roots
```

---

### 4. How Do Popular MCP Servers Handle Working Directory?

**Analysis of Real-World Implementations:**

#### **Filesystem MCP Server (Official)**
- **Method:** Requires workspace path as command-line argument
- **Configuration:** `args: ["/path/to/workspace"]` or accepts environment variable
- **Security:** Restricts all operations to provided base directory
- **Docs:** "The cwd parameter is required for proper server operation"

#### **GitHub MCP Server**
- **Method:** Assumes `os.getcwd()` is correct at spawn time
- **Limitation:** Broken when launched from IDE installation directory
- **Issue:** Multiple bug reports about "wrong repository detection"

#### **Serena (Semantic Code Analysis)**
- **Method:** Attempts to detect project from `cwd` via `.git`, `pyproject.toml`
- **Fallback:** Provides `activate_project(path)` tool for manual specification
- **Limitation:** Auto-detection fails if spawned from wrong directory

#### **FastMCP Context Broker**
- **Method:** Uses FastMCP's `Context.get_state()` for session-aware workspace
- **Feature:** Allows setting workspace via initialization or first tool call
- **State:** Persists workspace across all tool calls in the session

---

### 5. Can MCP Servers Maintain Persistent State Between Tool Calls?

**Answer: YES - MCP servers ARE stateful within a session.**

**Critical Insight:** This contradicts the common assumption that MCP is stateless!

#### **State Persistence Mechanisms:**

**1. Stdio Transport (Most Common):**
- Server process persists for entire IDE session
- Single process handles all tool calls from one client
- State stored in memory persists naturally
- Session ends when IDE disconnects or restarts

**2. FastMCP Context API:**
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CVC")

@mcp.tool()
async def set_workspace(path: str, ctx: Context) -> str:
    """Set the workspace directory for this session."""
    # State persists across tool calls
    await ctx.set_state("workspace", path)
    return f"Workspace set to: {path}"

@mcp.tool()
async def commit(message: str, ctx: Context) -> str:
    """Create a commit in the configured workspace."""
    # Retrieve state from previous tool call
    workspace = await ctx.get_state("workspace")
    if not workspace:
        return "Error: Workspace not set. Call set_workspace first."
    
    # Use the workspace...
    return f"Committed in {workspace}"
```

**3. Session-Aware Architecture:**
```python
class CVCMCPServer:
    def __init__(self):
        self.sessions = {}  # session_id -> session state
    
    def handle_initialize(self, session_id: str, params: dict):
        """Store session state on initialization."""
        self.sessions[session_id] = {
            "workspace": self._detect_workspace(),
            "initialized_at": datetime.now(),
        }
    
    def handle_tool_call(self, session_id: str, tool_name: str, args: dict):
        """Access session state during tool calls."""
        session = self.sessions.get(session_id, {})
        workspace = session.get("workspace")
        # Use workspace for CVC operations...
```

#### **State Isolation Levels:**

| Transport | State Scope | Identification |
|-----------|-------------|----------------|
| Stdio | Per process (single client) | Process lifetime |
| SSE/HTTP (single server) | Per session | `mcp-session-id` header |
| HTTP (serverless/distributed) | No state (each request different machine) | Not reliable |

**Important:** For distributed/serverless deployments, state must be externalized (Redis, database) because different HTTP requests may hit different server instances.

---

## Specific Recommendations for CVC MCP Server

Based on this research, here's how to implement workspace awareness in the CVC MCP server:

### **Immediate Implementation (High Priority)**

#### 1. **Add Workspace Detection at Startup**

Modify `cvc/mcp_server.py` to detect workspace using multi-strategy approach:

```python
import os
from pathlib import Path

class CVCWorkspaceDetector:
    """Detects the project workspace directory for CVC operations."""
    
    @staticmethod
    def detect() -> Path:
        """Detect workspace using multiple strategies."""
        # Strategy 1: Environment variable (highest priority)
        if workspace := os.getenv("CVC_WORKSPACE"):
            path = Path(workspace).resolve()
            if path.exists():
                logger.info("Workspace detected via CVC_WORKSPACE: %s", path)
                return path
        
        # Strategy 2: IDE-specific environment variables
        for env_var in ["CODEX_WORKSPACE_ROOT", "CLAUDE_CODE_CWD"]:
            if workspace := os.getenv(env_var):
                path = Path(workspace).resolve()
                if path.exists():
                    logger.info("Workspace detected via %s: %s", env_var, path)
                    return path
        
        # Strategy 3: Current working directory
        cwd = Path.cwd().resolve()
        
        # Strategy 4: Find project root by walking up
        project_root = CVCWorkspaceDetector._find_project_root(cwd)
        if project_root:
            logger.info("Workspace detected via project markers: %s", project_root)
            return project_root
        
        # Strategy 5: Fallback to cwd
        logger.warning("Using current directory as workspace (may be incorrect): %s", cwd)
        return cwd
    
    @staticmethod
    def _find_project_root(start: Path) -> Path | None:
        """Walk up to find project root markers."""
        markers = [".git", ".cvc", "pyproject.toml", "package.json"]
        current = start
        
        # Limit search to 10 levels up to avoid scanning entire filesystem
        for _ in range(10):
            if current == current.parent:  # Reached filesystem root
                break
            
            # Check for any marker
            if any((current / marker).exists() for marker in markers):
                return current
            
            current = current.parent
        
        return None
```

#### 2. **Store Workspace in Server State**

Add session-aware workspace storage:

```python
_workspace_root: Path | None = None  # Module-level state

def run_mcp_stdio() -> None:
    """Run the CVC MCP server using stdio transport."""
    global _workspace_root
    
    # Detect workspace at startup
    _workspace_root = CVCWorkspaceDetector.detect()
    
    # Log for debugging
    sys.stderr.write(f"\n✓ CVC workspace: {_workspace_root}\n\n")
    sys.stderr.flush()
    
    # Continue with existing stdio loop...
```

#### 3. **Add Workspace Configuration Tool**

Expose workspace control to the AI agent:

```python
MCP_TOOLS.append({
    "name": "cvc_set_workspace",
    "description": (
        "Set or change the CVC workspace directory. Use this if CVC is "
        "operating in the wrong directory or if you want to work with "
        "a different project. Returns the current workspace path."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to workspace directory",
            }
        },
        "required": ["path"],
    },
})

def _handle_set_workspace(args: dict) -> dict:
    """Set the workspace directory for CVC operations."""
    global _workspace_root
    
    path_str = args.get("path", "")
    path = Path(path_str).resolve()
    
    if not path.exists():
        return {
            "success": False,
            "error": f"Path does not exist: {path}"
        }
    
    if not path.is_dir():
        return {
            "success": False,
            "error": f"Path is not a directory: {path}"
        }
    
    _workspace_root = path
    return {
        "success": True,
        "workspace": str(_workspace_root),
        "message": f"CVC workspace set to: {_workspace_root}"
    }
```

#### 4. **Update All Tool Handlers to Use Workspace**

Ensure all CVC operations use the detected workspace:

```python
def _handle_tool_call(tool_name: str, arguments: dict) -> dict:
    """Dispatch tool calls to appropriate handlers."""
    global _workspace_root
    
    # Ensure we have a workspace
    if not _workspace_root:
        _workspace_root = CVCWorkspaceDetector.detect()
    
    # Pass workspace to all handlers
    if tool_name == "cvc_status":
        return _handle_status(_workspace_root)
    elif tool_name == "cvc_commit":
        return _handle_commit(_workspace_root, arguments)
    # ... etc
```

### **Future Enhancements (Medium Priority)**

#### 1. **Implement MCP Roots Protocol Support**

Add roots capability declaration and handler:

```python
def _handle_initialize(params: dict) -> dict:
    """Handle MCP initialize request with roots support."""
    client_caps = params.get("capabilities", {})
    supports_roots = "roots" in client_caps
    
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
            "roots": {  # Declare server wants roots
                "listChanged": False
            } if supports_roots else None
        },
        "serverInfo": {
            "name": "cvc",
            "version": _get_version(),
        },
    }

# Add roots/list request after initialization
def _request_workspace_roots() -> list[Path]:
    """Request workspace roots from MCP client (if supported)."""
    request = {
        "jsonrpc": "2.0",
        "id": "roots-query",
        "method": "roots/list",
        "params": {}
    }
    sys.stdout.write(json.dumps(request) + "\n")
    sys.stdout.flush()
    
    # Wait for response (simplified - needs proper async handling)
    response = json.loads(sys.stdin.readline())
    
    if "result" in response:
        roots = response["result"].get("roots", [])
        return [
            Path(root["uri"].removeprefix("file://").removeprefix("///"))
            for root in roots
        ]
    
    return []
```

#### 2. **Add Workspace Detection Report Tool**

Help users debug workspace detection issues:

```python
{
    "name": "cvc_debug_workspace",
    "description": "Show how CVC detected the workspace directory and available alternatives",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}

def _handle_debug_workspace() -> dict:
    """Return diagnostic information about workspace detection."""
    return {
        "current_workspace": str(_workspace_root),
        "detection_strategies": {
            "CVC_WORKSPACE": os.getenv("CVC_WORKSPACE", "not set"),
            "CODEX_WORKSPACE_ROOT": os.getenv("CODEX_WORKSPACE_ROOT", "not set"),
            "os.getcwd()": str(Path.cwd()),
            "project_root_search": str(CVCWorkspaceDetector._find_project_root(Path.cwd())),
        },
        "markers_checked": [".git", ".cvc", "pyproject.toml", "package.json"],
        "workspace_exists": _workspace_root.exists() if _workspace_root else False,
        "workspace_is_dir": _workspace_root.is_dir() if _workspace_root else False,
    }
```

### **Documentation Updates (High Priority)**

Update installation docs with proper workspace configuration examples:

```markdown
## Configuring CVC MCP Server

### VS Code

1. Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "cvc": {
      "command": "uv",
      "args": ["run", "cvc", "mcp"],
      "cwd": "${workspaceFolder}",
      "env": {
        "CVC_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

### Cursor/Windsurf

1. Create `.cursor/mcp.json` or equivalent:

```json
{
  "mcpServers": {
    "cvc": {
      "command": "cvc",
      "args": ["mcp"],
      "env": {
        "CVC_WORKSPACE": "/absolute/path/to/your/project"
      }
    }
  }
}
```

**Note:** Until Cursor supports `${workspaceFolder}`, use absolute paths.

### Manual Workspace Setting

If workspace detection fails, use the `cvc_set_workspace` tool:

```
Agent: Call cvc_set_workspace with path="/home/user/my-project"
```
```

---

## Technical Insights: Session State Management

### **stdin/stdout Transport is Stateful**

Contrary to HTTP's stateless nature, stdio MCP transport maintains state:

```
┌─────────────────┐         ┌──────────────────┐
│   VS Code       │         │  CVC MCP Server  │
│                 │         │   (one process)  │
│  Copilot Agent  │◄───────►│                  │
│                 │  stdio  │   Workspace:     │
│                 │         │   /home/user/... │
└─────────────────┘         └──────────────────┘
                                     │
                                     │ Lives for entire
                                     │ IDE session
                                     ▼
                            All tool calls share
                            same process & state
```

**Benefits:**
- No need for external state storage (Redis, DB)
- Simple in-memory state (Python dict, class instance)
- Workspace detection happens once at startup
- Fast - no network roundtrips for state

**Limitations:**
- State lost on server restart
- Cannot share state across multiple IDE windows
- Not suitable for HTTP/SSE unless using sticky sessions

---

## Security Considerations

### **Workspace Validation**

Always validate workspace paths to prevent directory traversal attacks:

```python
def validate_workspace(path: Path) -> bool:
    """Validate workspace path for security."""
    # Must be absolute
    if not path.is_absolute():
        return False
    
    # Must exist
    if not path.exists():
        return False
    
    # Must be a directory
    if not path.is_dir():
        return False
    
    # Optionally: Restrict to user's home directory
    try:
        home = Path.home()
        path.relative_to(home)  # Raises ValueError if not under home
    except ValueError:
        logger.warning("Workspace outside user home: %s", path)
        # Decide policy: allow or deny
    
    return True
```

### **MCP Roots for Sandboxing**

When implemented, roots provide client-side security:

- Client controls which directories server can access
- Server operations restricted to declared roots
- User explicitly approves root access in IDE
- Follows principle of least privilege

---

## Comparison: MCP vs LSP (Language Server Protocol)

Since MCP was inspired by LSP, comparing their approaches:

| Aspect | LSP | MCP |
|--------|-----|-----|
| **Workspace Detection** | Explicit `rootUri` in initialize | Roots protocol (optional) |
| **Multiple Workspaces** | `workspaceFolders` capability | Multiple roots support |
| **State Management** | Per-workspace state | Per-session state |
| **CWD Handling** | Client sends `rootUri` | Server must detect/receive via roots |
| **Maturity** | Established (2016) | Emerging (2024) |

**Lesson:** MCP should evolve toward LSP's explicit workspace communication model.

---

## References

**MCP Specification:**
- https://modelcontextprotocol.io/specification/2025-11-25
- https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices

**Real-World Issues:**
- GitHub Issue #1520: "How to access the current working directory when an MCP server is launched via claude mcp add"
- GitHub Issue #9989: "Pass workspace directory to MCP servers"
- Cursor Forum #74861: "Allow ${workspaceFolder} in MCP project configuration"

**Example Implementations:**
- Official Filesystem MCP Server: https://github.com/modelcontextprotocol/servers
- Enhanced Filesystem MCP: https://github.com/redf0x1/MCP-Server-Filesystem
- Cyanheads Filesystem MCP: https://github.com/cyanheads/filesystem-mcp-server

**Community Resources:**
- Real Python MCP Client Tutorial: https://realpython.com/python-mcp-client/
- Composio MCP Guide: https://composio.dev/blog/mcp-client-step-by-step-guide-to-building-from-scratch
- HuggingFace MCP Course: https://huggingface.co/learn/mcp-course/en/unit1/sdk

---

## Conclusion

**MCP workspace detection requires a defense-in-depth strategy:**

1. ✅ **Primary:** `cwd` parameter in IDE configuration + environment variable
2. ✅ **Detection:** Project root discovery via marker files (.git, pyproject.toml)
3. ✅ **Override:** Tool for manual workspace setting
4. ✅ **Future:** MCP roots protocol integration
5. ✅ **State:** Leverage stdio transport's stateful nature

The CVC MCP server should implement strategies 1-3 immediately and prepare for strategy 4 as IDE support matures.

**Most Critical Finding:** Do NOT rely on `os.getcwd()` alone - it will be wrong when launched via package managers (uvx, npx) or from incorrect IDE spawn locations. Always provide explicit configuration paths.
