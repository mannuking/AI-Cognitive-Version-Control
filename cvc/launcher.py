"""
cvc.launcher — Zero-config auto-launch engine for AI tools.

The ``cvc launch <tool>`` command wraps any AI coding agent (IDE or CLI)
so that ALL traffic flows through the CVC Cognitive Proxy automatically.

What it does:
  1. Ensures CVC is set up (provider, model, API key)
  2. Ensures ``cvc init`` is done for the current project
  3. Starts the CVC proxy in the background (if not already running)
  4. Configures the tool's environment / config files to point at CVC
  5. Launches the tool — every conversation is now time-machined

This is the "just works" layer on top of CVC.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("cvc.launcher")


# ---------------------------------------------------------------------------
# Tool Registry — how to launch every supported AI tool through CVC
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    # ── CLI Tools ─────────────────────────────────────────────────────────
    "claude": {
        "name": "Claude Code CLI",
        "binary": "claude",
        "kind": "cli",
        "env": {
            "ANTHROPIC_BASE_URL": "{endpoint}",
        },
        # Claude carries its own API key; CVC just intercepts traffic
        "pass_through_auth": True,
        "description": "Claude Code with cognitive versioning via /v1/messages",
    },
    "aider": {
        "name": "Aider",
        "binary": "aider",
        "kind": "cli",
        "env": {
            "OPENAI_API_BASE": "{endpoint}/v1",
            "OPENAI_API_KEY": "cvc",
        },
        "extra_args": ["--model", "openai/{model}"],
        "description": "Aider with CVC proxy as OpenAI-compatible backend",
    },
    "codex": {
        "name": "OpenAI Codex CLI",
        "binary": "codex",
        "kind": "cli",
        "env": {
            "OPENAI_API_BASE": "{endpoint}/v1",
            "OPENAI_API_KEY": "cvc",
        },
        "description": "Codex CLI routed through CVC proxy",
    },
    "gemini": {
        "name": "Gemini CLI",
        "binary": "gemini",
        "kind": "cli",
        "env": {
            "GEMINI_API_BASE_URL": "{endpoint}/v1",
        },
        "description": "Gemini CLI with CVC cognitive versioning",
    },
    "kiro": {
        "name": "Kiro CLI (Amazon)",
        "binary": "kiro",
        "kind": "cli",
        "env": {
            "OPENAI_API_BASE": "{endpoint}/v1",
            "OPENAI_API_KEY": "cvc",
        },
        "description": "Kiro CLI routed through CVC proxy",
    },
    # ── IDEs ──────────────────────────────────────────────────────────────
    "cursor": {
        "name": "Cursor",
        "binary": "cursor",
        "kind": "ide",
        "args": ["."],
        "env": {},
        "auto_config": "_auto_config_cursor",
        "description": "Cursor with CVC proxy as base URL override",
    },
    "code": {
        "name": "Visual Studio Code",
        "binary": "code",
        "kind": "ide",
        "args": ["."],
        "env": {},
        "auto_config": "_auto_config_vscode",
        "description": "VS Code with Copilot BYOK → CVC proxy",
    },
    "windsurf": {
        "name": "Windsurf",
        "binary": "windsurf",
        "kind": "ide",
        "args": ["."],
        "env": {},
        "auto_config": "_auto_config_mcp_ide",
        "mcp_config_name": "windsurf",
        "description": "Windsurf with CVC via MCP sidecar",
    },
}

# Aliases
TOOL_ALIASES = {
    "claude-code": "claude",
    "claude-cli": "claude",
    "vscode": "code",
    "vs-code": "code",
    "visual-studio-code": "code",
    "openai-codex": "codex",
    "codex-cli": "codex",
    "gemini-cli": "gemini",
    "kiro-cli": "kiro",
    "codeium": "windsurf",
}


def resolve_tool(name: str) -> str | None:
    """Resolve a tool name (or alias) to a registry key."""
    key = name.lower().strip()
    if key in TOOL_REGISTRY:
        return key
    return TOOL_ALIASES.get(key)


def list_launchable_tools() -> list[dict[str, str]]:
    """Return a list of all launchable tools with availability info."""
    tools = []
    for key, info in TOOL_REGISTRY.items():
        binary = info["binary"]
        installed = shutil.which(binary) is not None
        tools.append({
            "key": key,
            "name": info["name"],
            "binary": binary,
            "kind": info["kind"],
            "installed": installed,
            "description": info.get("description", ""),
        })
    return tools


# ---------------------------------------------------------------------------
# Proxy lifecycle helpers
# ---------------------------------------------------------------------------

def _check_proxy_health(endpoint: str) -> bool:
    """Return True if the CVC proxy is running and healthy."""
    try:
        import httpx
        r = httpx.get(f"{endpoint}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _start_proxy_background(host: str = "127.0.0.1", port: int = 8000) -> subprocess.Popen:
    """
    Start ``cvc serve`` as a detached background process.
    Returns the Popen handle.
    """
    # Use the same Python that's running CVC
    python = sys.executable
    cmd = [python, "-m", "cvc", "serve", "--host", host, "--port", str(port)]

    # Platform-specific daemonisation
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    return proc


def ensure_proxy_running(
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: float = 10.0,
) -> bool:
    """
    Ensure the CVC proxy is running.  Starts it in the background if needed.
    Returns True if the proxy is reachable within *timeout* seconds.
    """
    endpoint = f"http://{host}:{port}"

    if _check_proxy_health(endpoint):
        return True

    logger.info("Starting CVC proxy on %s:%d …", host, port)
    _start_proxy_background(host, port)

    # Wait for the proxy to become healthy
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.4)
        if _check_proxy_health(endpoint):
            return True

    return False


# ---------------------------------------------------------------------------
# IDE auto-configuration helpers
# ---------------------------------------------------------------------------

def _get_mcp_config_path(ide: str) -> Path | None:
    """Return the MCP config file path for an IDE, or None."""
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        paths = {
            "cursor": appdata / "Cursor" / "User" / "globalStorage" / "cursor.mcp" / "mcp.json",
            "windsurf": appdata / "Windsurf" / "User" / "globalStorage" / "windsurf.mcp" / "mcp.json",
        }
    elif sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
        paths = {
            "cursor": support / "Cursor" / "User" / "globalStorage" / "cursor.mcp" / "mcp.json",
            "windsurf": support / "Windsurf" / "User" / "globalStorage" / "windsurf.mcp" / "mcp.json",
        }
    else:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        paths = {
            "cursor": config_home / "Cursor" / "User" / "globalStorage" / "cursor.mcp" / "mcp.json",
            "windsurf": config_home / "Windsurf" / "User" / "globalStorage" / "windsurf.mcp" / "mcp.json",
        }
    return paths.get(ide)


def _auto_config_vscode(endpoint: str, model: str) -> dict[str, Any]:
    """
    Auto-configure VS Code Copilot BYOK and write .vscode/mcp.json
    for MCP integration.  Returns a status dict.
    """
    result: dict[str, Any] = {"actions": []}

    # 1. Write .vscode/mcp.json for MCP integration
    vscode_dir = Path.cwd() / ".vscode"
    mcp_json = vscode_dir / "mcp.json"
    vscode_dir.mkdir(exist_ok=True)

    mcp_config = {
        "servers": {
            "cvc": {
                "command": "cvc",
                "args": ["mcp"],
            }
        }
    }

    # Merge existing mcp.json if present
    existing = {}
    if mcp_json.exists():
        try:
            existing = json.loads(mcp_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "servers" not in existing:
        existing["servers"] = {}
    existing["servers"]["cvc"] = mcp_config["servers"]["cvc"]

    mcp_json.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    result["actions"].append("Wrote .vscode/mcp.json with CVC MCP server")

    # 2. Auto-configure Copilot BYOK in user settings
    if sys.platform == "win32":
        settings_path = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "settings.json"
    elif sys.platform == "darwin":
        settings_path = Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    else:
        settings_path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Code" / "User" / "settings.json"

    if settings_path.exists():
        try:
            raw = settings_path.read_text(encoding="utf-8")
            settings = json.loads(raw)
        except Exception:
            settings = None  # Can't parse (JSONC, etc.)

        if settings is not None:
            custom_models = settings.get("github.copilot.chat.customOAIModels", {})
            custom_models["cvc-proxy"] = {
                "name": f"CVC Proxy ({model})",
                "url": f"{endpoint}/v1/chat/completions",
                "toolCalling": True,
                "vision": False,
                "thinking": False,
                "maxInputTokens": 128000,
                "maxOutputTokens": 8192,
                "requiresAPIKey": True,
            }
            settings["github.copilot.chat.customOAIModels"] = custom_models
            settings_path.write_text(json.dumps(settings, indent=4), encoding="utf-8")
            result["actions"].append("Configured Copilot BYOK in VS Code settings.json")

    return result


def _auto_config_cursor(endpoint: str, model: str) -> dict[str, Any]:
    """Write CVC MCP server config for Cursor."""
    result: dict[str, Any] = {"actions": []}

    # Write .cursor/mcp.json
    cursor_dir = Path.cwd() / ".cursor"
    mcp_json = cursor_dir / "mcp.json"
    cursor_dir.mkdir(exist_ok=True)

    existing = {}
    if mcp_json.exists():
        try:
            existing = json.loads(mcp_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "mcpServers" not in existing:
        existing["mcpServers"] = {}
    existing["mcpServers"]["cvc"] = {
        "command": "cvc",
        "args": ["mcp"],
    }

    mcp_json.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    result["actions"].append("Wrote .cursor/mcp.json with CVC MCP server")
    result["manual_step"] = (
        f"Also set: Settings → Models → Override OpenAI Base URL → {endpoint}/v1"
    )
    return result


def _auto_config_mcp_ide(endpoint: str, model: str, *, ide_name: str = "windsurf") -> dict[str, Any]:
    """Write CVC MCP server config for MCP-only IDEs (Windsurf, etc.)."""
    result: dict[str, Any] = {"actions": []}

    mcp_path = _get_mcp_config_path(ide_name)
    if mcp_path:
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if mcp_path.exists():
            try:
                existing = json.loads(mcp_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        existing["mcpServers"]["cvc"] = {
            "command": "cvc",
            "args": ["mcp"],
        }

        mcp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        result["actions"].append(f"Wrote MCP config → {mcp_path}")
    else:
        result["actions"].append(f"Could not find {ide_name} MCP config path; manual setup needed")

    return result


def _auto_config_claude_mcp() -> dict[str, Any]:
    """Write CVC as an MCP server in Claude Code's project config."""
    result: dict[str, Any] = {"actions": []}

    # Write .mcp.json (Claude Code project-level MCP config)
    mcp_json = Path.cwd() / ".mcp.json"
    existing = {}
    if mcp_json.exists():
        try:
            existing = json.loads(mcp_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "mcpServers" not in existing:
        existing["mcpServers"] = {}
    existing["mcpServers"]["cvc"] = {
        "command": "cvc",
        "args": ["mcp"],
    }

    mcp_json.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    result["actions"].append("Wrote .mcp.json with CVC as MCP server for Claude Code")
    return result


# ---------------------------------------------------------------------------
# Core launch function
# ---------------------------------------------------------------------------

def launch_tool(
    tool_name: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    extra_args: list[str] | None = None,
    *,
    time_machine: bool = True,
    auto_setup: bool = True,
    auto_init: bool = True,
) -> dict[str, Any]:
    """
    Launch an AI coding tool with CVC automatically interceping all traffic.

    Returns a dict with status information.

    The *time_machine* flag enables aggressive auto-commit (every 3 turns)
    in the proxy, ensuring no conversation state is ever lost.
    """
    from cvc.core.models import CVCConfig, GlobalConfig, get_global_config_dir, discover_cvc_root

    key = resolve_tool(tool_name)
    if key is None:
        return {
            "success": False,
            "error": f"Unknown tool: '{tool_name}'",
            "available": list(TOOL_REGISTRY.keys()),
        }

    tool = TOOL_REGISTRY[key]
    binary = tool["binary"]
    endpoint = f"http://{host}:{port}"
    report: dict[str, Any] = {
        "success": False,
        "tool": tool["name"],
        "binary": binary,
        "endpoint": endpoint,
        "steps": [],
    }

    # ── Step 1: Ensure CVC is set up ─────────────────────────────────────
    if auto_setup:
        gc_path = get_global_config_dir() / "config.json"
        if not gc_path.exists():
            report["steps"].append("need_setup")
            return {**report, "error": "CVC is not set up. Run 'cvc setup' first."}
        report["steps"].append("setup_ok")

    gc = GlobalConfig.load()
    model = gc.model

    # ── Step 2: Ensure project is initialised ────────────────────────────
    if auto_init:
        project_root = discover_cvc_root()
        if project_root is None:
            # Auto-initialise in current directory
            config = CVCConfig.for_project(project_root=Path.cwd())
            config.ensure_dirs()
            from cvc.core.database import ContextDatabase
            ContextDatabase(config).close()
            report["steps"].append("auto_init")
        else:
            report["steps"].append("init_ok")

    # ── Step 3: Check tool is installed ──────────────────────────────────
    binary_path = shutil.which(binary)
    if binary_path is None:
        return {
            **report,
            "error": f"'{binary}' not found on PATH. Install {tool['name']} first.",
        }
    report["steps"].append("binary_found")

    # ── Step 4: Start proxy in background ────────────────────────────────
    if time_machine:
        os.environ["CVC_TIME_MACHINE"] = "1"

    proxy_ok = ensure_proxy_running(host, port, timeout=12.0)
    if not proxy_ok:
        return {**report, "error": "CVC proxy failed to start within 12 seconds."}
    report["steps"].append("proxy_running")

    # ── Step 5: Auto-configure the tool ──────────────────────────────────
    auto_config_fn = tool.get("auto_config")
    if auto_config_fn == "_auto_config_vscode":
        config_result = _auto_config_vscode(endpoint, model)
        report["auto_config"] = config_result
    elif auto_config_fn == "_auto_config_cursor":
        config_result = _auto_config_cursor(endpoint, model)
        report["auto_config"] = config_result
    elif auto_config_fn == "_auto_config_mcp_ide":
        ide_name = tool.get("mcp_config_name", "windsurf")
        config_result = _auto_config_mcp_ide(endpoint, model, ide_name=ide_name)
        report["auto_config"] = config_result

    # For Claude Code, also write .mcp.json so CVC tools are available
    if key == "claude":
        mcp_result = _auto_config_claude_mcp()
        report.setdefault("auto_config", {})["mcp"] = mcp_result

    report["steps"].append("configured")

    # ── Step 6: Build environment and launch ─────────────────────────────
    child_env = os.environ.copy()

    # Set tool-specific env vars
    for env_key, env_val in tool.get("env", {}).items():
        child_env[env_key] = env_val.format(endpoint=endpoint, model=model)

    # Build command
    cmd = [binary]
    cmd.extend(tool.get("args", []))
    cmd.extend(tool.get("extra_args", []))
    if extra_args:
        cmd.extend(extra_args)

    report["command"] = cmd
    report["env_overrides"] = {
        k: v.format(endpoint=endpoint, model=model) for k, v in tool.get("env", {}).items()
    }
    report["success"] = True

    # For IDEs, launch in background and return immediately
    if tool["kind"] == "ide":
        subprocess.Popen(
            cmd,
            env=child_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        report["steps"].append("ide_launched")
        return report

    # For CLI tools, exec into the tool (replace the current process on Unix,
    # or run and wait on Windows)
    report["steps"].append("launching_cli")
    return report, cmd, child_env  # type: ignore[return-value]


def exec_tool(cmd: list[str], env: dict[str, str]) -> int:
    """Execute the tool, replacing the current process where possible."""
    if sys.platform != "win32":
        # On Unix, exec replaces the process entirely
        os.execvpe(cmd[0], cmd, env)
        return 0  # unreachable, but for type checker
    else:
        # On Windows, run and wait
        try:
            result = subprocess.run(cmd, env=env)
            return result.returncode
        except KeyboardInterrupt:
            return 130
