"""
cvc.cli — Command-line interface for the Cognitive Version Control system.

A beautiful, developer-friendly CLI powered by Rich.

Usage:
    cvc setup                  Interactive first-time configuration
    cvc serve                  Start the Cognitive Proxy on localhost:8000
    cvc init                   Initialise a .cvc/ directory in the current project
    cvc status                 Show current branch, HEAD, and branch list
    cvc log                    Show commit history for the active branch
    cvc commit -m "message"    Create a manual cognitive commit
    cvc branch <name>          Create and switch to a new branch
    cvc merge <source>         Merge source branch into the active branch
    cvc restore <hash>         Restore context to a previous commit
    cvc install-hooks          Install Git hooks for VCS synchronisation
    cvc capture-snapshot       Capture CVC state linked to current Git commit
    cvc doctor                 Health check for your CVC environment
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

LOGO = """[bold #CC3333]
 ██████╗ ██╗   ██╗  ██████╗
██╔════╝ ██║   ██║ ██╔════╝
██║      ██║   ██║ ██║
██║      ╚██╗ ██╔╝ ██║
╚██████╗  ╚████╔╝  ╚██████╗
 ╚═════╝   ╚═══╝    ╚═════╝[/bold #CC3333]"""

TAGLINE = "[#8B7070]Cognitive Version Control — Git for the AI Agents[/#8B7070]"

try:
    from cvc import __version__ as VERSION
except ImportError:
    VERSION = "1.4.81"


def _banner(subtitle: str = "") -> None:
    """Print the CVC banner with custom top border (Meena center, version right)."""
    from rich.box import Box as _Box

    content = f"{LOGO}\n\n{TAGLINE}"
    if subtitle:
        content += f"\n\n[bold #E8D0D0]{subtitle}[/bold #E8D0D0]"

    # ── Custom top border: ── Meena ──────── v1.x.x ──
    tw = console.width or 80
    ver = f" v{VERSION} "
    meena = " Meena "
    inner = tw - 2  # space between ╭ and ╮
    center = inner // 2
    m_start = max(center - len(meena) // 2, 1)
    m_end = m_start + len(meena)
    v_start = max(inner - len(ver), m_end + 1)

    top = Text()
    top.append("╭", style="#8B0000")
    top.append("─" * m_start, style="#8B0000")
    top.append(meena, style="bold #CC3333")
    gap = v_start - m_end
    top.append("─" * max(gap, 1), style="#8B0000")
    top.append(ver, style="bold #FF4444")
    remaining = inner - v_start - len(ver)
    top.append("─" * max(remaining, 0), style="#8B0000")
    top.append("╮", style="#8B0000")
    console.print(top)

    # Body + bottom border via Panel with no-top-border custom box
    _NO_TOP_BOX = _Box(
        "│  │\n"
        "│  │\n"
        "├──┤\n"
        "│  │\n"
        "├──┤\n"
        "│  │\n"
        "├──┤\n"
        "╰──╯\n"
    )
    console.print(
        Panel(
            content,
            box=_NO_TOP_BOX,
            border_style="#8B0000",
            padding=(1, 4),
            width=tw,
            subtitle="[#8B7070]Time Machine for AI Agents[/#8B7070]",
            subtitle_align="center",
        ),
        highlight=False,
    )
    console.print()


def _success(msg: str) -> None:
    console.print(f"  [bold #55AA55]✓[/bold #55AA55] {msg}")


def _error(msg: str) -> None:
    console.print(f"  [bold red]✗[/bold red] {msg}")


def _warn(msg: str) -> None:
    console.print(f"  [bold #CCAA44]![/bold #CCAA44] {msg}")


def _info(msg: str) -> None:
    console.print(f"  [dim]→[/dim] {msg}")


def _hint(msg: str) -> None:
    console.print()
    console.print(
        Panel(
            msg,
            border_style="#5C1010",
            title="[bold #8B7070]Hint[/bold #8B7070]",
            padding=(0, 2),
        )
    )


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_config():
    from cvc.core.models import CVCConfig
    return CVCConfig.for_project()


def _get_engine():
    from cvc.core.database import ContextDatabase
    from cvc.operations.engine import CVCEngine
    config = _get_config()
    config.ensure_dirs()
    db = ContextDatabase(config)
    return CVCEngine(config, db), db


# ---------------------------------------------------------------------------
# IDE Auto-Detection & Auto-Configuration
# ---------------------------------------------------------------------------

def _get_ide_config_paths() -> dict[str, dict]:
    """Return known install/config paths for detectable IDEs per platform."""
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return {
            "vscode": {
                "name": "Visual Studio Code",
                "icon": "💎",
                "settings": appdata / "Code" / "User" / "settings.json",
                "command": "code",
                "can_auto_config": True,
                "auth_type": "byok",
            },
            "cursor": {
                "name": "Cursor",
                "icon": "🖱️",
                "settings": appdata / "Cursor" / "User" / "settings.json",
                "command": "cursor",
                "can_auto_config": False,
                "auth_type": "api_key_override",
            },
            "windsurf": {
                "name": "Windsurf",
                "icon": "🏄",
                "settings": appdata / "Windsurf" / "User" / "settings.json",
                "command": "windsurf",
                "can_auto_config": False,
                "auth_type": "account_auth",
            },
        }
    elif sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
        return {
            "vscode": {
                "name": "Visual Studio Code",
                "icon": "💎",
                "settings": support / "Code" / "User" / "settings.json",
                "command": "code",
                "can_auto_config": True,
                "auth_type": "byok",
            },
            "cursor": {
                "name": "Cursor",
                "icon": "🖱️",
                "settings": support / "Cursor" / "User" / "settings.json",
                "command": "cursor",
                "can_auto_config": False,
                "auth_type": "api_key_override",
            },
            "windsurf": {
                "name": "Windsurf",
                "icon": "🏄",
                "settings": support / "Windsurf" / "User" / "settings.json",
                "command": "windsurf",
                "can_auto_config": False,
                "auth_type": "account_auth",
            },
        }
    else:  # Linux
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return {
            "vscode": {
                "name": "Visual Studio Code",
                "icon": "💎",
                "settings": config_home / "Code" / "User" / "settings.json",
                "command": "code",
                "can_auto_config": True,
                "auth_type": "byok",
            },
            "cursor": {
                "name": "Cursor",
                "icon": "🖱️",
                "settings": config_home / "Cursor" / "User" / "settings.json",
                "command": "cursor",
                "can_auto_config": False,
                "auth_type": "api_key_override",
            },
            "windsurf": {
                "name": "Windsurf",
                "icon": "🏄",
                "settings": config_home / "Windsurf" / "User" / "settings.json",
                "command": "windsurf",
                "can_auto_config": False,
                "auth_type": "account_auth",
            },
        }


def _detect_ides() -> dict[str, dict]:
    """Detect installed IDEs by checking config directories and PATH."""
    ide_paths = _get_ide_config_paths()
    detected = {}
    for ide_key, info in ide_paths.items():
        found = False
        reason = ""
        # Check if config directory exists (indicates installation)
        settings_dir = info["settings"].parent
        if settings_dir.exists():
            found = True
            reason = "config found"
        # Check if command is on PATH
        cmd = info.get("command")
        if cmd and shutil.which(cmd):
            found = True
            reason = "installed"
        if found:
            detected[ide_key] = {**info, "reason": reason}
    return detected


def _auto_configure_vscode(settings_path: Path, endpoint: str, model: str) -> bool:
    """
    Auto-configure VS Code Copilot BYOK to route through CVC proxy.

    Writes ``github.copilot.chat.customOAIModels`` into the user-level
    settings.json so Copilot can use CVC as an OpenAI-compatible provider.
    Returns True on success.
    """
    settings: dict = {}
    if settings_path.exists():
        try:
            raw = settings_path.read_text(encoding="utf-8")
            settings = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return False  # JSONC, permissions, etc.

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

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=4), encoding="utf-8")
        return True
    except OSError:
        return False


def _run_ide_detection(model: str, endpoint: str = "http://127.0.0.1:8000") -> dict[str, dict]:
    """
    Detect IDEs and auto-configure where possible.

    Called at the end of ``setup`` to wire up detected IDEs automatically.
    Returns the detection results dict.
    """
    console.print("[bold #CC3333]  Detecting installed IDEs…[/bold #CC3333]")
    console.print()

    detected = _detect_ides()

    if not detected:
        _info("No IDEs auto-detected. Run [bold]cvc connect[/bold] for manual setup guides.")
        console.print()
        return detected

    for ide_key, ide_info in detected.items():
        _success(
            f"{ide_info['icon']}  [bold]{ide_info['name']}[/bold] detected  "
            f"[dim]({ide_info['reason']})[/dim]"
        )

        if ide_key == "vscode" and ide_info.get("can_auto_config"):
            ok = _auto_configure_vscode(ide_info["settings"], endpoint, model)
            if ok:
                _success("   → Copilot BYOK auto-configured with CVC proxy")
                _info("   Select [bold]CVC Proxy[/bold] in the Copilot model picker")
                _info("   Or run [bold]cvc mcp[/bold] for native Copilot MCP integration")
                ide_info["configured"] = True
            else:
                _warn("   → Could not auto-configure (settings.json may have comments)")
                _info("   Run [bold]cvc connect vscode[/bold] for manual steps")
                ide_info["configured"] = False

        elif ide_key == "cursor":
            _info("   → Open [bold]Cursor Settings → Models[/bold]")
            _info(f"   → Override OpenAI Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]")
            _info("   → API Key → [#CC3333]cvc[/#CC3333]")
            _info("   → Or add CVC as an MCP server: [bold]cvc connect cursor[/bold]")
            ide_info["configured"] = "manual"

        elif ide_key == "windsurf":
            _info("   → Windsurf uses account-based auth (no API override)")
            _info("   → Use CVC via MCP: run [bold]cvc mcp[/bold]")
            _info("   → Add to Windsurf MCP config: [bold]cvc connect windsurf[/bold]")
            ide_info["configured"] = "mcp"

    console.print()
    return detected


# ---------------------------------------------------------------------------
# Click Group (entry point)
# ---------------------------------------------------------------------------

class CvcGroup(click.Group):
    """Custom group that shows help in a styled format."""

    def format_help(self, ctx, formatter):
        """Override to use Rich-styled help."""
        _banner()

        # Commands table
        table = Table(
            box=box.ROUNDED,
            border_style="dim",
            show_header=True,
            header_style="bold #CC3333",
            padding=(0, 2),
        )
        table.add_column("Command", style="bold white", width=22)
        table.add_column("Description", style="dim white")

        cmds = [
            ("agent", "Interactive AI coding agent (like Claude Code)"),
            ("launch <tool>", "Auto-launch any AI tool through CVC"),
            ("up", "One-command start (setup + init + serve)"),
            ("setup", "Interactive first-time setup"),
            ("serve", "Start the Cognitive Proxy server"),
            ("connect", "Connect your AI tool to CVC"),
            ("mcp", "Start CVC as an MCP server"),
            ("recall \"query\"", "Search ALL past conversations (NL search)"),
            ("context --show", "Display stored conversation content"),
            ("export --markdown", "Export conversation as shareable Markdown"),
            ("inject <project>", "Cross-project context transfer"),
            ("diff <hash1> <hash2>", "Knowledge / decision diff between commits"),
            ("stats", "Analytics dashboard (tokens, costs, patterns)"),
            ("compact --smart", "AI-powered context compression"),
            ("timeline", "ASCII timeline of all AI interactions"),
            ("sync push/pull", "Push/pull AI context to team remote"),
            ("audit", "Security audit trail (compliance-ready)"),
            ("sessions", "View Time Machine session history"),
            ("init", "Initialise .cvc/ in your project"),
            ("status", "Show branch, HEAD, context size"),
            ("log", "View commit history"),
            ("commit -m '...'", "Create a cognitive checkpoint"),
            ("branch <name>", "Create an exploration branch"),
            ("merge <branch>", "Semantic merge into active branch"),
            ("restore <hash>", "Time-travel to a previous state"),
            ("install-hooks", "Install Git ↔ CVC sync hooks"),
            ("doctor", "Health check your environment"),
        ]
        for cmd, desc in cmds:
            table.add_row(cmd, desc)

        console.print(
            Panel(
                table,
                border_style="#8B0000",
                title="[bold white]Commands[/bold white]",
                padding=(1, 1),
            )
        )

        # Quick start hint
        console.print()
        console.print(
            Panel(
                "[bold #E8D0D0]Get started in 10 seconds:[/bold #E8D0D0]\n\n"
                "  [#CC3333]$[/#CC3333] cvc agent              [#8B7070]# Interactive AI agent right here in your terminal[/#8B7070]\n"
                "  [#CC3333]$[/#CC3333] cvc launch claude      [#8B7070]# Zero-config: launches Claude Code through CVC[/#8B7070]\n"
                "  [#CC3333]$[/#CC3333] cvc launch aider       [#8B7070]# Zero-config: launches Aider through CVC[/#8B7070]\n"
                "  [#CC3333]$[/#CC3333] cvc up                 [#8B7070]# One command: setup + init + serve[/#8B7070]\n\n"
                "[bold #E8D0D0]Or step by step:[/bold #E8D0D0]\n\n"
                "  [#CC3333]$[/#CC3333] cvc setup              [#8B7070]# Pick your provider & model[/#8B7070]\n"
                "  [#CC3333]$[/#CC3333] cvc serve              [#8B7070]# Start the proxy (API key tools)[/#8B7070]\n"
                "  [#CC3333]$[/#CC3333] cvc mcp                [#8B7070]# Start MCP server (auth-based IDEs)[/#8B7070]\n"
                "  [#CC3333]$[/#CC3333] cvc connect            [#8B7070]# Wire up Cursor, Cline, Claude Code…[/#8B7070]",
                border_style="#5C1010",
                title="[bold #55AA55]Quick Start[/bold #55AA55]",
                padding=(1, 2),
            )
        )

        console.print(
            "\n  [dim]Run[/dim] [bold]cvc <command> --help[/bold] [dim]for details on any command.[/dim]\n"
        )


@click.group(cls=CvcGroup, invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.version_option(VERSION, prog_name="cvc")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """CVC — Cognitive Version Control: Git for the AI Mind."""
    _setup_logging(verbose)

    if ctx.invoked_subcommand is not None:
        return  # A subcommand was given — Click handles it

    from cvc.core.models import get_global_config_dir, GlobalConfig

    gc_path = get_global_config_dir() / "config.json"

    if not gc_path.exists():
        # ─── First run — setup then straight into the agent ──────────────
        _banner(subtitle="Welcome to CVC!\n\nLooks like this is your first time here.\nLet's get you set up — it takes about 30 seconds.")
        ctx.invoke(setup, first_run=True)
        # After setup, fall through to launch the agent

    # ─── Launch the agent directly ───────────────────────────────────────
    ctx.invoke(agent)


# ---------------------------------------------------------------------------
# setup (guided first-time configuration)
# ---------------------------------------------------------------------------

MODEL_CATALOG = {
    "anthropic": [
        ("claude-opus-4-6", "Most intelligent — agents & coding (Feb 2026)", "$5/$25 per MTok"),
        ("claude-sonnet-4-6", "Best speed/intelligence balance (Feb 2026)", "$3/$15 per MTok"),
        ("claude-opus-4-5", "Previous flagship — excellent reasoning", "$5/$25 per MTok"),
        ("claude-sonnet-4-5", "Previous Sonnet — still great", "$3/$15 per MTok"),
        ("claude-haiku-4-5", "Fastest & cheapest", "$1/$5 per MTok"),
    ],
    "openai": [
        ("gpt-5.3", "Newest flagship — best reasoning & coding", "Frontier"),
        ("gpt-5.2", "Previous flagship — coding & agentic tasks", "Frontier"),
        ("gpt-5.2-codex", "Optimized for agentic coding", "Frontier"),
        ("gpt-5-mini", "Fast & cost-efficient GPT-5", "Mid-tier"),
        ("gpt-4.1", "Instruction following & tool calling (1M ctx)", "Mid-tier"),
    ],
    "google": [
        ("gemini-2.5-flash", "Best price-performance (GA) — recommended", "Standard"),
        ("gemini-2.5-pro", "Advanced thinking model (GA)", "Premium"),
        ("gemini-3-pro-preview", "Gemini 3 Pro (preview, very slow ~2min/turn)", "Premium"),
        ("gemini-3-flash-preview", "Gemini 3 Flash (preview, fast thinking)", "Standard"),
        ("gemini-2.5-flash-lite", "Fastest & cheapest (GA)", "Economy"),
    ],
    # Confirmed tools badge on Ollama library as of Feb 2026
    "ollama": [
        ("qwen2.5-coder:7b", "Best 7B coding — 11M+ pulls, tools ✓", "~4 GB"),
        ("qwen3:14b", "Qwen3 — thinking + non-thinking modes, tools ✓", "~9 GB"),
        ("qwen3-coder:30b", "Agentic coder — MoE, 256K context, tools ✓", "~19 GB"),
        ("devstral:24b", "Mistral best open-source coding agent, tools ✓", "~14 GB"),
        ("deepseek-r1:8b", "DeepSeek-R1 — reasoning + tool calling", "~5 GB"),
        ("mistral-small3.2:24b", "Improved function calling + vision, tools ✓", "~15 GB"),
        ("qwq:32b", "QwQ deep reasoning + tool calling", "~20 GB"),
        ("llama3.3:70b", "Meta Llama 3.3 — powerful general model, tools ✓", "~40 GB"),
    ],
    "lmstudio": [
        ("qwen2.5-coder-32b-instruct", "Best local coding — native tools", "~18 GB"),
        ("qwen3-14b", "Qwen3 14B — thinking mode + tool calling", "~9 GB"),
        ("devstral-small-2505", "Mistral agentic coding model, tool calling", "~14 GB"),
        ("deepseek-r1-distill-qwen-32b", "Reasoning + coding, chain-of-thought", "~18 GB"),
        ("gemma-3-27b-it", "Google Gemma 3 27B instruction tuned", "~15 GB"),
        ("mistral-small-3.2-24b-instruct", "Improved function calling over 3.1", "~13 GB"),
    ],
}


@main.command()
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai", "google", "ollama", "lmstudio"], case_sensitive=False),
    default=None,
    help="LLM provider (uses config default if omitted).",
)
@click.option("--model", default="", help="Model override (uses provider default if empty).")
@click.option("--api-key", default="", help="API key override.")
@click.option(
    "--no-think",
    "no_think",
    is_flag=True,
    default=False,
    help=(
        "Disable model reasoning/thinking phase for faster responses. "
        "Mainly useful for slow thinking models like gemini-3-pro-preview. "
        "Tradeoff: lower response quality on complex tasks."
    ),
)
def agent(provider: str | None, model: str, api_key: str, no_think: bool) -> None:
    """Interactive AI coding agent — Claude Code on steroids with Time Machine."""
    from cvc.core.models import GlobalConfig

    gc = GlobalConfig.load()

    # Resolve provider
    prov = provider or gc.provider
    if not prov:
        console.print(
            "[bold red]No provider configured.[/bold red] Run [bold]cvc setup[/bold] first, "
            "or pass [bold]--provider[/bold]."
        )
        raise SystemExit(1)

    # Resolve model
    mdl = model or gc.model or ""

    # Resolve API key
    key = api_key or gc.api_keys.get(prov, "") or ""
    if prov not in ("ollama", "lmstudio") and not key:
        console.print(
            f"[bold red]No API key for {prov}.[/bold red] Run [bold]cvc setup[/bold] first, "
            "or pass [bold]--api-key[/bold]."
        )
        raise SystemExit(1)

    from cvc.agent import run_agent

    run_agent(provider=prov, model=mdl, api_key=key, no_think=no_think)


# ═══════════════════════════════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════════════════════════════


@main.command()
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai", "google", "ollama", "lmstudio"], case_sensitive=False),
    prompt=False,
    help="LLM provider (interactive prompt if omitted).",
)
@click.option("--model", default="", help="Model override (uses provider default if empty).")
@click.option("--api-key", default="", help="API key (prompted interactively if omitted).")
def setup(provider: str | None, model: str, api_key: str, first_run: bool = False) -> None:
    """Interactive first-time setup — pick your provider, model, and go."""
    from cvc.adapters import PROVIDER_DEFAULTS
    from cvc.core.models import GlobalConfig as GC_Init, get_global_config_dir

    # Only show banner if not a first run (first run already showed it)
    if not first_run:
        _banner("Setup Wizard")

    # ─── Detect existing configuration ───────────────────────────────────
    gc_file = get_global_config_dir() / "config.json"
    existing_gc = GC_Init.load()
    # Only treat as "existing" if the config file actually exists on disk
    # (GlobalConfig has defaults like provider="anthropic", so bool(provider)
    # would always be True even on a fresh install)
    has_existing = gc_file.exists() and bool(existing_gc.provider)

    if has_existing and not provider and not first_run:
        # Show current config summary and let user choose
        masked_keys = {}
        for prov, key in existing_gc.api_keys.items():
            if key and len(key) > 12:
                masked_keys[prov] = key[:8] + "…" + key[-4:]
            elif key:
                masked_keys[prov] = "●●●●"

        current_info = (
            f"  Provider   [bold #CC3333]{existing_gc.provider}[/bold #CC3333]\n"
            f"  Model      [bold #CC3333]{existing_gc.model}[/bold #CC3333]"
        )
        if masked_keys:
            keys_str = ", ".join(f"{p}: {m}" for p, m in masked_keys.items())
            current_info += f"\n  API Keys   [dim]{keys_str}[/dim]"

        console.print(
            Panel(
                current_info,
                border_style="#5C1010",
                title="[bold #55AA55]Existing Configuration Found[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        console.print()

        console.print("  [bold white]What would you like to do?[/bold white]")
        console.print()
        console.print("    [#CC3333]1[/#CC3333]  [bold]Start Fresh[/bold]          [dim]— Reconfigure everything from scratch[/dim]")
        console.print("    [#55AA55]2[/#55AA55]  [bold]Change Provider[/bold]     [dim]— Switch to a different LLM provider[/dim]")
        console.print("    [#CCAA44]3[/#CCAA44]  [bold]Change Model[/bold]        [dim]— Keep provider, pick a different model[/dim]")
        console.print("    [#AA6666]4[/#AA6666]  [bold]Update API Key[/bold]      [dim]— Replace or add an API key[/dim]")
        console.print("    [red]5[/red]  [bold]Reset Everything[/bold]    [dim]— Delete all config and start over[/dim]")
        console.print()

        action = click.prompt(
            "  Enter number",
            type=click.IntRange(1, 5),
            default=1,
        )
        console.print()

        if action == 5:
            # Reset everything
            config_dir = get_global_config_dir()
            config_file = config_dir / "config.json"
            if config_file.exists():
                config_file.unlink()
                _success(f"Deleted global config → [dim]{config_file}[/dim]")
            # Reset the existing_gc so the wizard runs fresh
            existing_gc = GC_Init()
            _info("Starting fresh setup…")
            console.print()
        elif action == 3:
            # Change model only — jump straight to model selection
            provider = existing_gc.provider
            _success(f"Provider: [bold]{provider}[/bold]  [dim](keeping current)[/dim]")
            console.print()

            defaults = PROVIDER_DEFAULTS[provider]
            chosen_model = existing_gc.model

            console.print("[bold #CC3333]  Pick a new model[/bold #CC3333]")
            console.print()

            models = MODEL_CATALOG.get(provider, [])
            table = Table(box=box.ROUNDED, border_style="dim", show_header=True, header_style="bold #CC3333")
            table.add_column("#", style="bold", width=3)
            table.add_column("Model ID", style="#CC3333")
            table.add_column("Description")
            table.add_column("Tier", style="dim", justify="right")
            table.add_column("", width=3)
            for i, (mid, desc, tier) in enumerate(models, 1):
                marker = "[bold #55AA55]●[/bold #55AA55]" if mid == chosen_model else " "
                table.add_row(str(i), mid, desc, tier, marker)
            console.print(Panel(table, border_style="#8B0000", title=f"[bold white]{provider.title()} Models[/bold white]", padding=(1, 1)))

            model_choice = click.prompt("  Enter number or model ID", default="", show_default=False).strip()
            if model_choice:
                if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                    chosen_model = models[int(model_choice) - 1][0]
                else:
                    chosen_model = model_choice

            # Save with updated model
            api_keys = dict(existing_gc.api_keys)
            gc = GC_Init(provider=provider, model=chosen_model, api_keys=api_keys)
            gc_path = gc.save()
            _success(f"Model updated to [bold]{chosen_model}[/bold]")
            _success(f"Config saved → [dim]{gc_path}[/dim]")
            console.print()
            return

        elif action == 4:
            # Update API key only
            provider = existing_gc.provider
            _success(f"Provider: [bold]{provider}[/bold]")
            console.print()

            defaults = PROVIDER_DEFAULTS[provider]
            env_key = defaults["env_key"]

            if provider in ("ollama", "lmstudio"):
                _success(f"{provider.title()} doesn't need an API key — it runs locally!")
                console.print()
                return

            key_urls = {
                "anthropic": "https://console.anthropic.com/settings/keys",
                "openai": "https://platform.openai.com/api-keys",
                "google": "https://aistudio.google.com/apikey",
            }
            url = key_urls.get(provider, "")
            if url:
                console.print(f"  [dim]Get your key →[/dim] [bold underline]{url}[/bold underline]")
                console.print()

            new_key = click.prompt("  Paste your new API key", hide_input=True).strip()
            if new_key:
                api_keys = dict(existing_gc.api_keys)
                api_keys[provider] = new_key
                gc = GC_Init(provider=provider, model=existing_gc.model, api_keys=api_keys)
                gc_path = gc.save()
                _success("API key updated!")
                _success(f"Config saved → [dim]{gc_path}[/dim]")
            else:
                _warn("No key entered. Nothing changed.")
            console.print()
            return

        elif action == 2:
            # Change provider — fall through to full wizard but don't reset keys
            provider = None  # Will prompt for provider below
            _info("Select a new provider below…")
            console.print()

        # action == 1 (Start Fresh) or action == 2 (Change Provider)
        # Both fall through to the full wizard below

    console.print(
        Panel(
            "[bold white]This wizard will configure CVC in 4 quick steps.[/bold white]\n"
            "Your settings are saved globally — works across all projects.",
            border_style="#8B0000",
            padding=(0, 2),
        )
    )
    console.print()

    # ─── Step 1: Provider Selection ──────────────────────────────────────
    console.print("[bold #CC3333]  STEP 1 of 4[/bold #CC3333]  [bold white]Choose your LLM provider[/bold white]")
    console.print()

    if not provider:
        providers = [
            (("anthropic", "Anthropic", "Claude Opus 4.6 / 4.5, Sonnet 4.5", "#CC3333")),
            (("openai", "OpenAI", "GPT-5.2, GPT-5.2-Codex", "#CC6666")),
            (("google", "Google", "Gemini 3/2.5 Pro, Gemini 3/2.5 Flash", "#AA8844")),
            ("ollama", "Ollama", "Local models via Ollama — no API key needed!", "magenta"),
            ("lmstudio", "LM Studio", "Local models via LM Studio server — no API key needed!", "cyan"),
        ]
        for i, (key, name, desc, color) in enumerate(providers, 1):
            console.print(
                f"    [{color}]{i}[/{color}]  [bold]{name}[/bold]  [dim]— {desc}[/dim]"
            )
        console.print()

        choice = click.prompt(
            "  Enter number",
            type=click.IntRange(1, 5),
        )
        provider = providers[choice - 1][0]

    _success(f"Provider: [bold]{provider}[/bold]")
    console.print()

    defaults = PROVIDER_DEFAULTS[provider]
    chosen_model = model or defaults["model"]

    # ─── Step 2: Model Selection ─────────────────────────────────────────
    console.print("[bold #CC3333]  STEP 2 of 4[/bold #CC3333]  [bold white]Pick a model[/bold white]")
    console.print()

    models = MODEL_CATALOG.get(provider, [])
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold #CC3333",
    )
    table.add_column("#", style="bold", width=3)
    table.add_column("Model ID", style="#CC3333")
    table.add_column("Description")
    table.add_column("Tier", style="dim", justify="right")
    table.add_column("", width=3)

    for i, (mid, desc, tier) in enumerate(models, 1):
        # Don't pre-select any model for first-time users
        marker = " "
        table.add_row(str(i), mid, desc, tier, marker)

    console.print(
        Panel(table, border_style="#8B0000", title=f"[bold white]{provider.title()} Models[/bold white]", padding=(1, 1))
    )

    if not model and models:
        model_choice = click.prompt(
            "  Enter number or model ID",
            type=str,
        ).strip()
        if model_choice:
            # If it's a number, pick from the list
            if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                chosen_model = models[int(model_choice) - 1][0]
            else:
                chosen_model = model_choice
        else:
            # If empty, require selection
            console.print("  [bold red]Model selection is required.[/bold red]")
            return

    _success(f"Model: [bold]{chosen_model}[/bold]")
    console.print()

    # ─── Step 3: API Key ─────────────────────────────────────────────────
    console.print("[bold #CC3333]  STEP 3 of 4[/bold #CC3333]  [bold white]API Key[/bold white]")
    console.print()

    env_key = defaults["env_key"]

    if provider == "ollama":
        _success("No API key needed for Ollama — it runs locally!")
        console.print()
        console.print(
            Panel(
                f"Ollama runs automatically in the background on Windows/macOS.\n"
                f"Just make sure the model is downloaded:\n\n"
                f"  [#CC3333]$[/#CC3333] ollama pull {chosen_model}\n\n"
                f"[dim]Linux only:[/dim] if Ollama isn't running as a service, start it with:\n"
                f"  [dim]$ ollama serve[/dim]",
                border_style="#6B2020",
                title="[bold #AA6666]Local Setup — Ollama[/bold #AA6666]",
                padding=(1, 2),
            )
        )
    elif provider == "lmstudio":
        _success("No API key needed for LM Studio — it runs locally!")
        console.print()
        console.print(
            Panel(
                f"Make sure LM Studio is running with a model loaded:\n\n"
                f"  1. Open LM Studio\n"
                f"  2. Go to [bold]Developer → Local Server[/bold]\n"
                f"  3. Load model [bold]{chosen_model}[/bold] and click [bold]Start Server[/bold]\n"
                f"  4. Default URL: http://localhost:1234",
                border_style="#6B2020",
                title="[bold #AA6666]Local Setup — LM Studio[/bold #AA6666]",
                padding=(1, 2),
            )
        )
    else:
        # Check env var first
        env_val = os.environ.get(env_key, "") if env_key else ""
        # Then check saved config
        from cvc.core.models import GlobalConfig as GC_Check
        existing_gc = GC_Check.load()
        saved_key = existing_gc.api_keys.get(provider, "")

        if api_key:
            # Passed via --api-key flag
            pass
        elif env_val:
            masked = env_val[:8] + "…" + env_val[-4:]
            _success(f"Found in environment: [bold]{env_key}[/bold] ({masked})")
            console.print(f"  [dim]Using environment variable — no need to enter it again.[/dim]")
            api_key = ""  # Don't store; env takes precedence
        elif saved_key:
            masked = saved_key[:8] + "…" + saved_key[-4:]
            _success(f"Found saved key ({masked})")
            console.print(f"  [dim]Using previously saved key. Press Enter to keep it.[/dim]")
            new_key = click.prompt(
                "  Paste new key (or Enter to keep existing)",
                default="",
                hide_input=True,
                show_default=False,
            ).strip()
            api_key = new_key if new_key else saved_key
        else:
            _warn(f"No API key found for [bold]{provider}[/bold]")

            # Provider-specific instructions
            key_urls = {
                "anthropic": "https://console.anthropic.com/settings/keys",
                "openai": "https://platform.openai.com/api-keys",
                "google": "https://aistudio.google.com/apikey",
            }
            url = key_urls.get(provider, "")
            console.print()
            if url:
                console.print(f"  [dim]Get your key →[/dim] [bold underline]{url}[/bold underline]")
            console.print()

            api_key = click.prompt(
                "  Paste your API key",
                hide_input=True,
            ).strip()

            if api_key:
                _success("API key saved!")
            else:
                _warn("No key entered. You can set it later via env var or re-run setup.")

    console.print()

    # ─── Step 4: Save & Initialise ───────────────────────────────────────
    console.print("[bold #CC3333]  STEP 4 of 4[/bold #CC3333]  [bold white]Saving configuration[/bold white]")
    console.print()

    from cvc.core.models import GlobalConfig, CVCConfig, get_global_config_dir

    # Build api_keys dict: preserve existing keys, update current provider
    gc_existing = GlobalConfig.load()
    api_keys = dict(gc_existing.api_keys)  # Copy existing
    if api_key:
        api_keys[provider] = api_key

    gc = GlobalConfig(
        provider=provider,
        model=chosen_model,
        api_keys=api_keys,
    )
    gc_path = gc.save()
    _success(f"Global config saved → [dim]{gc_path}[/dim]")

    # Initialise .cvc in current directory
    config = CVCConfig.for_project(project_root=Path.cwd(), provider=provider, model=chosen_model)
    config.ensure_dirs()

    from cvc.core.database import ContextDatabase
    ContextDatabase(config)
    _success(f"Project initialised → [dim]{config.cvc_root}[/dim]")

    console.print()

    # ─── Summary ─────────────────────────────────────────────────────────
    key_display = "[#55AA55]● saved[/#55AA55]"
    if provider in ("ollama", "lmstudio"):
        key_display = "[dim]not needed[/dim]"
    elif not api_key and os.environ.get(env_key, ""):
        key_display = "[#55AA55]● from env[/#55AA55]"
    elif not api_key:
        key_display = "[red]● missing[/red]"

    console.print(
        Panel(
            f"  Provider   [bold #CC3333]{provider}[/bold #CC3333]\n"
            f"  Model      [bold #CC3333]{chosen_model}[/bold #CC3333]\n"
            f"  API Key    {key_display}\n"
            f"  Config     [dim]{gc_path}[/dim]\n"
            f"  Database   [dim]{config.db_path}[/dim]\n"
            f"  Objects    [dim]{config.objects_dir}[/dim]",
            border_style="#5C1010",
            title="[bold #55AA55]✓ CVC is Ready[/bold #55AA55]",
            padding=(1, 2),
        )
    )

    # ─── IDE Auto-Detection & Configuration ─────────────────────────────
    _run_ide_detection(chosen_model)

    # ─── Offer to start the proxy ────────────────────────────────────────
    start_now = click.confirm(
        "  Start the CVC proxy server now?",
        default=True,
    )

    if start_now:
        console.print()
        click.get_current_context().invoke(serve)
    else:
        console.print()
        console.print(
            Panel(
                "  [#CC3333]$[/#CC3333] cvc serve              [dim]# Start the proxy whenever you're ready[/dim]\n"
                "  [#CC3333]$[/#CC3333] cvc connect             [dim]# Tool-specific setup guides[/dim]\n"
                "  [#CC3333]$[/#CC3333] [dim]Point your agent → http://127.0.0.1:8000/v1/chat/completions[/dim]",
                border_style="#5C1010",
                title="[bold #8B7070]When You're Ready[/bold #8B7070]",
                padding=(1, 2),
            )
        )
        console.print()


# ---------------------------------------------------------------------------
# Connection guides (shared between `serve` and `connect`)
# ---------------------------------------------------------------------------

TOOL_GUIDES: dict[str, dict[str, str | list[str]]] = {
    # ── IDEs ──────────────────────────────────────────────────────────────
    "vscode": {
        "name": "Visual Studio Code",
        "icon": "💎",
        "category": "IDE",
        "steps": [
            "[bold]VS Code GitHub Copilot uses GitHub login authentication.[/bold]",
            "The native Copilot agent cannot be redirected to a custom endpoint.",
            "However, VS Code supports [bold]3 ways[/bold] to use CVC:",
            "",
            "[bold #CC3333]Option 1: Copilot BYOK (Bring Your Own Key)[/bold #CC3333]",
            "  Available on Copilot Individual plans (Free, Pro, Pro+):",
            "  1. [bold]Ctrl+Shift+P[/bold] → [bold]Chat: Manage Language Models[/bold]",
            "  2. Select [bold]OpenAI Compatible[/bold] as provider",
            "  3. Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "  4. API Key → [#CC3333]cvc[/#CC3333]  [dim](any non-empty string)[/dim]",
            "  5. Select model → [#CC3333]{model}[/#CC3333]",
            "",
            "[bold #CC3333]Option 2: MCP Server (Works with native Copilot)[/bold #CC3333]",
            "  Add to VS Code settings.json or .vscode/mcp.json:",
            '     [#CC3333]{{"mcp": {{"servers": {{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}}}}}[/#CC3333]',
            "  CVC tools will be available as MCP tools in Copilot agent mode.",
            "",
            "[bold #CC3333]Option 3: Extensions (Continue.dev / Cline)[/bold #CC3333]",
            "  Install from VS Code Marketplace and configure with:",
            "  Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "  API Key → [#CC3333]cvc[/#CC3333]",
            "",
            "[dim]BYOK is not available on Copilot Business/Enterprise plans.[/dim]",
            "[dim]For Enterprise, use MCP or an extension instead.[/dim]",
        ],
    },
    "antigravity": {
        "name": "Antigravity (Google)",
        "icon": "🚀",
        "category": "IDE",
        "steps": [
            "[bold]Antigravity uses Google account authentication[/bold] — you cannot",
            "override the LLM API endpoint directly. Use CVC via [bold]MCP[/bold] instead.",
            "",
            "[bold #CC3333]Option 1: MCP Server (Recommended)[/bold #CC3333]",
            "  1. Click [bold]⋯[/bold] in Antigravity's agent panel → [bold]Manage MCP Servers[/bold]",
            "  2. Click [bold]View raw config[/bold]",
            "  3. Add the CVC MCP server:",
            "",
            '     [#CC3333]{{"mcpServers": {{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}}}[/#CC3333]',
            "",
            "  4. The CVC tools (commit, branch, merge, restore, status, log)",
            "     will appear as available tools in Antigravity's agent.",
            "",
            "[bold #CC3333]Option 2: Continue.dev Extension[/bold #CC3333]",
            "  Antigravity is Code OSS-based and supports Open VSX extensions.",
            "  Install [bold]Continue.dev[/bold] from Open VSX and configure:",
            "     Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "     API Key  → [#CC3333]cvc[/#CC3333]",
            "     Model    → [#CC3333]{model}[/#CC3333]",
            "",
            "[dim]Antigravity's native Gemini agent uses Google auth internally.[/dim]",
            "[dim]MCP is the only way to add CVC to the native agent flow.[/dim]",
        ],
    },
    "cursor": {
        "name": "Cursor",
        "icon": "🖱️",
        "category": "IDE",
        "steps": [
            "[bold]Cursor supports API key + base URL override.[/bold]",
            "",
            "  1. Open Cursor → Settings (⚙️) → [bold]Models[/bold]",
            "  2. Click [bold]Add OpenAI API Key[/bold] → paste [#CC3333]cvc[/#CC3333]",
            "  3. Enable [bold]Override OpenAI Base URL[/bold] → set to:",
            "     [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "  4. Select your model and start coding!",
            "",
            "[bold #CC3333]Alternative: MCP Server[/bold #CC3333]",
            "  You can also add CVC as an MCP server in Cursor:",
            "  Settings → MCP Servers → Add:",
            '     [#CC3333]{{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}[/#CC3333]',
            "",
            "[dim]Note: Cursor's built-in models use subscription auth internally.[/dim]",
            "[dim]The override route above replaces those with CVC-proxied calls.[/dim]",
        ],
    },
    "windsurf": {
        "name": "Windsurf",
        "icon": "🏄",
        "category": "IDE",
        "steps": [
            "[bold]Windsurf uses account-based authentication[/bold] — you cannot",
            "override the LLM API endpoint directly. Use CVC via [bold]MCP[/bold].",
            "",
            "[bold #CC3333]MCP Server (Recommended)[/bold #CC3333]",
            "  1. Open Windsurf → click [bold]⋯[/bold] in Cascade panel",
            "  2. Go to [bold]MCP Settings[/bold] → [bold]Configure[/bold]",
            "  3. Add the CVC MCP server:",
            "",
            '     [#CC3333]{{"mcpServers": {{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}}}[/#CC3333]',
            "",
            "  4. CVC tools (commit, branch, merge, restore, status, log)",
            "     will be available to Windsurf's Cascade agent.",
            "",
            "[dim]Windsurf (formerly Codeium) is now owned by OpenAI.[/dim]",
            "[dim]The built-in Cascade agent authenticates via Windsurf account.[/dim]",
            "[dim]MCP is the supported way to extend its capabilities.[/dim]",
        ],
    },
    # ── IDE Extensions ────────────────────────────────────────────────────
    "vscode-continue": {
        "name": "Continue.dev (VS Code)",
        "icon": "🔄",
        "category": "IDE Extension",
        "steps": [
            "Install [bold]Continue[/bold] extension from VS Code Marketplace",
            "Open [bold]~/.continue/config.yaml[/bold] and add:",
            "",
            "  [#CC3333]models:[/#CC3333]",
            "    [#CC3333]- name: CVC Proxy[/#CC3333]",
            "      [#CC3333]provider: openai[/#CC3333]",
            "      [#CC3333]model: {model}[/#CC3333]",
            "      [#CC3333]apiBase: {endpoint}/v1[/#CC3333]",
            "      [#CC3333]apiKey: cvc[/#CC3333]",
            "",
            "Restart VS Code → select [bold]CVC Proxy[/bold] in Continue",
        ],
    },
    "vscode-cline": {
        "name": "Cline / Roo (VS Code)",
        "icon": "🤖",
        "category": "IDE Extension",
        "steps": [
            "Install [bold]Cline[/bold] extension from VS Code Marketplace",
            "Click the ⚙️ icon in the Cline panel",
            "Set API Provider → [bold]OpenAI Compatible[/bold]",
            "Set Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "Set API Key → [#CC3333]cvc[/#CC3333]  [dim](any non-empty string)[/dim]",
            "Set Model ID → [#CC3333]{model}[/#CC3333]",
            "Click [bold]Verify[/bold] → done!",
        ],
    },
    "vscode-copilot": {
        "name": "GitHub Copilot (BYOK)",
        "icon": "🐙",
        "category": "IDE Extension",
        "steps": [
            "Open VS Code → [bold]Chat: Manage Language Models[/bold] (Ctrl+Shift+P)",
            "Select [bold]OpenAI Compatible[/bold] as provider",
            "Set Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "Set API Key → [#CC3333]cvc[/#CC3333]  [dim](any non-empty string)[/dim]",
            "Select model → [#CC3333]{model}[/#CC3333]",
            "[dim]Note: BYOK is for Copilot Individual plans only (not Business/Enterprise)[/dim]",
        ],
    },
    # ── CLI Tools ─────────────────────────────────────────────────────────
    "claude-code": {
        "name": "Claude Code CLI",
        "icon": "🟠",
        "category": "CLI Tool",
        "steps_unix": [
            "[bold]Claude Code now works natively with CVC![/bold]",
            "CVC serves the Anthropic Messages API at [bold]/v1/messages[/bold],",
            "so Claude Code works without any format translation.",
            "",
            "[bold #CC3333]Quick start:[/bold #CC3333]",
            "",
            "  [#CC3333]export ANTHROPIC_BASE_URL=\"{endpoint}\"[/#CC3333]",
            "  [#CC3333]claude[/#CC3333]",
            "",
            "Your existing ANTHROPIC_API_KEY is passed through to the",
            "upstream Anthropic API. CVC intercepts the conversation for",
            "cognitive versioning and forwards everything else.",
            "",
            "[bold #CC3333]Or add to ~/.claude/settings.json:[/bold #CC3333]",
            "",
            "  [#CC3333]{{[/#CC3333]",
            "    [#CC3333]\"env\": {{[/#CC3333]",
            "      [#CC3333]\"ANTHROPIC_BASE_URL\": \"{endpoint}\"[/#CC3333]",
            "    [#CC3333]}}[/#CC3333]",
            "  [#CC3333]}}[/#CC3333]",
            "",
            "[dim]Auth pass-through: CVC forwards your API key to Anthropic.[/dim]",
            "[dim]No need to store your key in CVC — just set ANTHROPIC_API_KEY.[/dim]",
        ],
        "steps_win": [
            "[bold]Claude Code now works natively with CVC![/bold]",
            "CVC serves the Anthropic Messages API at [bold]/v1/messages[/bold].",
            "",
            "[bold #CC3333]Quick start:[/bold #CC3333]",
            "",
            "  [#CC3333]$env:ANTHROPIC_BASE_URL = \"{endpoint}\"[/#CC3333]",
            "  [#CC3333]claude[/#CC3333]",
            "",
            "Your existing ANTHROPIC_API_KEY is passed through to the",
            "upstream Anthropic API. CVC intercepts the conversation for",
            "cognitive versioning and forwards everything else.",
            "",
            "[dim]Auth pass-through: CVC forwards your API key to Anthropic.[/dim]",
            "[dim]No need to store your key in CVC — just set ANTHROPIC_API_KEY.[/dim]",
        ],
    },
    "gemini-cli": {
        "name": "Gemini CLI",
        "icon": "💠",
        "category": "CLI Tool",
        "steps_unix": [
            "Gemini CLI uses settings files for configuration.",
            "Edit [bold]~/.gemini/settings.json[/bold] and add:",
            "",
            "  [#CC3333]{{[/#CC3333]",
            "    [#CC3333]\"model\": {{[/#CC3333]",
            "      [#CC3333]\"name\": \"{model}\"[/#CC3333]",
            "    [#CC3333]}}[/#CC3333]",
            "  [#CC3333]}}[/#CC3333]",
            "",
            "Then set the API endpoint via environment variable:",
            "",
            "  [#CC3333]export GEMINI_API_BASE_URL=\"{endpoint}/v1\"[/#CC3333]",
            "  [#CC3333]export GEMINI_API_KEY=\"your-key\"[/#CC3333]",
            "  [#CC3333]gemini[/#CC3333]",
            "",
            "[dim]Custom base URL support may require Gemini CLI v2+.[/dim]",
            "[dim]Check: https://github.com/google-gemini/gemini-cli[/dim]",
        ],
        "steps_win": [
            "Gemini CLI uses settings files for configuration.",
            "Edit [bold]%USERPROFILE%\\.gemini\\settings.json[/bold] and add:",
            "",
            "  [#CC3333]{{[/#CC3333]",
            "    [#CC3333]\"model\": {{[/#CC3333]",
            "      [#CC3333]\"name\": \"{model}\"[/#CC3333]",
            "    [#CC3333]}}[/#CC3333]",
            "  [#CC3333]}}[/#CC3333]",
            "",
            "Then set the API endpoint via environment variable:",
            "",
            "  [#CC3333]$env:GEMINI_API_BASE_URL = \"{endpoint}/v1\"[/#CC3333]",
            "  [#CC3333]$env:GEMINI_API_KEY = \"your-key\"[/#CC3333]",
            "  [#CC3333]gemini[/#CC3333]",
            "",
            "[dim]Custom base URL support may require Gemini CLI v2+.[/dim]",
            "[dim]Check: https://github.com/google-gemini/gemini-cli[/dim]",
        ],
    },
    "kiro-cli": {
        "name": "Kiro CLI (Amazon)",
        "icon": "🦊",
        "category": "CLI Tool",
        "steps_unix": [
            "Kiro CLI from Amazon uses custom agents + MCP servers.",
            "Create a custom agent config to route through CVC:",
            "",
            "  Edit [bold]~/.kiro/settings.json[/bold]:",
            "",
            "  [#CC3333]{{[/#CC3333]",
            "    [#CC3333]\"model_provider\": \"openai\",[/#CC3333]",
            "    [#CC3333]\"model\": \"{model}\",[/#CC3333]",
            "    [#CC3333]\"base_url\": \"{endpoint}/v1\",[/#CC3333]",
            "    [#CC3333]\"api_key\": \"cvc\"[/#CC3333]",
            "  [#CC3333]}}[/#CC3333]",
            "",
            "Or use the Kiro Gateway for OpenAI-compatible routing:",
            "",
            "  [#CC3333]export OPENAI_API_BASE=\"{endpoint}/v1\"[/#CC3333]",
            "  [#CC3333]export OPENAI_API_KEY=\"cvc\"[/#CC3333]",
            "  [#CC3333]kiro[/#CC3333]",
            "",
            "[dim]See: https://kiro.dev/docs/cli/[/dim]",
        ],
        "steps_win": [
            "Kiro CLI from Amazon uses custom agents + MCP servers.",
            "Create a custom agent config to route through CVC:",
            "",
            "  Edit [bold]%USERPROFILE%\\.kiro\\settings.json[/bold]:",
            "",
            "  [#CC3333]{{[/#CC3333]",
            "    [#CC3333]\"model_provider\": \"openai\",[/#CC3333]",
            "    [#CC3333]\"model\": \"{model}\",[/#CC3333]",
            "    [#CC3333]\"base_url\": \"{endpoint}/v1\",[/#CC3333]",
            "    [#CC3333]\"api_key\": \"cvc\"[/#CC3333]",
            "  [#CC3333]}}[/#CC3333]",
            "",
            "Or use environment variables:",
            "",
            "  [#CC3333]$env:OPENAI_API_BASE = \"{endpoint}/v1\"[/#CC3333]",
            "  [#CC3333]$env:OPENAI_API_KEY = \"cvc\"[/#CC3333]",
            "  [#CC3333]kiro[/#CC3333]",
            "",
            "[dim]See: https://kiro.dev/docs/cli/[/dim]",
        ],
    },
    "aider": {
        "name": "Aider CLI",
        "icon": "🛠️",
        "category": "CLI Tool",
        "steps_unix": [
            "Set the environment variables:",
            "",
            "  [#CC3333]export OPENAI_API_BASE={endpoint}/v1[/#CC3333]",
            "  [#CC3333]export OPENAI_API_KEY=cvc[/#CC3333]",
            "",
            "Then start Aider:",
            "",
            "  [#CC3333]aider --model openai/{model}[/#CC3333]",
        ],
        "steps_win": [
            "Set the environment variables:",
            "",
            "  [#CC3333]$env:OPENAI_API_BASE = \"{endpoint}/v1\"[/#CC3333]",
            "  [#CC3333]$env:OPENAI_API_KEY = \"cvc\"[/#CC3333]",
            "",
            "Then start Aider:",
            "",
            "  [#CC3333]aider --model openai/{model}[/#CC3333]",
        ],
    },
    # ── Web Interface ─────────────────────────────────────────────────────
    "open-webui": {
        "name": "Open WebUI",
        "icon": "🌐",
        "category": "Web Interface",
        "steps": [
            "Open WebUI → [bold]Settings → Connections[/bold]",
            "Click [bold]+ Add Connection[/bold]",
            "URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "API Key → [#CC3333]cvc[/#CC3333]  [dim](any non-empty string)[/dim]",
            "Save → the CVC model will appear in the model dropdown",
        ],
    },
    # ── Cloud IDE ─────────────────────────────────────────────────────────
    "firebase-studio": {
        "name": "Firebase Studio",
        "icon": "🔥",
        "category": "Cloud IDE",
        "steps": [
            "Firebase Studio is Google's cloud IDE built on Code OSS.",
            "It uses Gemini natively but supports Open VSX extensions.",
            "To route AI through CVC:",
            "",
            "  1. Start CVC with [bold]--host 0.0.0.0[/bold] (or use a tunnel)",
            "  2. Open your Firebase Studio workspace",
            "  3. Install [bold]Continue.dev[/bold] or [bold]Cline[/bold] from Open VSX",
            "  4. Configure the extension with:",
            "     Base URL → [bold #CC3333]{endpoint}/v1[/bold #CC3333]",
            "     API Key  → [#CC3333]cvc[/#CC3333]",
            "     Model    → [#CC3333]{model}[/#CC3333]",
            "",
            "[bold #CC3333]Alternative: MCP Server[/bold #CC3333]",
            "  If your Firebase Studio workspace has terminal access:",
            '  Add CVC as an MCP server in [bold].vscode/mcp.json[/bold]',
            "",
            "[dim]Firebase Studio does not support direct API endpoint override.[/dim]",
            "[dim]Use extensions or MCP for custom model routing.[/dim]",
        ],
    },
    # ── CLI Tools (additional) ────────────────────────────────────────────
    "codex-cli": {
        "name": "OpenAI Codex CLI",
        "icon": "⌨️",
        "category": "CLI Tool",
        "steps_unix": [
            "[bold]Codex CLI supports custom model providers.[/bold]",
            "Add CVC as a proxy provider in your config:",
            "",
            "[bold #CC3333]Option 1: Environment variables[/bold #CC3333]",
            "",
            "  [#CC3333]export OPENAI_API_BASE={endpoint}/v1[/#CC3333]",
            "  [#CC3333]export OPENAI_API_KEY=cvc[/#CC3333]",
            "  [#CC3333]codex[/#CC3333]",
            "",
            "[bold #CC3333]Option 2: Config file (~/.codex/config.toml)[/bold #CC3333]",
            "",
            "  [#CC3333]model_provider = \"cvc\"[/#CC3333]",
            "",
            "  [#CC3333][model_providers.cvc][/#CC3333]",
            "  [#CC3333]name = \"CVC Proxy\"[/#CC3333]",
            '  [#CC3333]base_url = "{endpoint}"[/#CC3333]',
            '  [#CC3333]env_key = "OPENAI_API_KEY"[/#CC3333]',
            "",
            "Your API key is passed through to the upstream provider.",
            "",
            "[dim]Works with: codex, codex --provider openai, and custom providers.[/dim]",
        ],
        "steps_win": [
            "[bold]Codex CLI supports custom model providers.[/bold]",
            "",
            "[bold #CC3333]Option 1: Environment variables[/bold #CC3333]",
            "",
            "  [#CC3333]$env:OPENAI_API_BASE = \"{endpoint}/v1\"[/#CC3333]",
            "  [#CC3333]$env:OPENAI_API_KEY = \"cvc\"[/#CC3333]",
            "  [#CC3333]codex[/#CC3333]",
            "",
            "[bold #CC3333]Option 2: Config file (~/.codex/config.toml)[/bold #CC3333]",
            "",
            "  [#CC3333]model_provider = \"cvc\"[/#CC3333]",
            "",
            "  [#CC3333][model_providers.cvc][/#CC3333]",
            "  [#CC3333]name = \"CVC Proxy\"[/#CC3333]",
            '  [#CC3333]base_url = "{endpoint}"[/#CC3333]',
            '  [#CC3333]env_key = "OPENAI_API_KEY"[/#CC3333]',
            "",
            "[dim]Works with: codex, codex --provider openai, and custom providers.[/dim]",
        ],
    },
}


def _format_tool_guide(tool_key: str, endpoint: str, model: str) -> Panel:
    """Format a single tool's connection guide as a Rich Panel."""
    guide = TOOL_GUIDES[tool_key]
    name = guide["name"]
    icon = guide["icon"]

    # Pick platform-specific steps for CLI tools
    if sys.platform == "win32" and "steps_win" in guide:
        steps = guide["steps_win"]
    elif "steps_unix" in guide:
        steps = guide["steps_unix"]
    else:
        steps = guide.get("steps", [])

    # Format steps with endpoint/model placeholders
    formatted = []
    for step in steps:
        line = str(step).format(endpoint=endpoint, model=model)
        formatted.append(f"  {line}")

    return Panel(
        "\n".join(formatted),
        border_style="dim cyan",
        title=f"[bold white]{icon} {name}[/bold white]",
        title_align="left",
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

@main.command()
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8000, type=int, help="Bind port.")
@click.option("--reload", "do_reload", is_flag=True, help="Enable auto-reload for development.")
def serve(host: str, port: int, do_reload: bool) -> None:
    """Start the CVC Cognitive Proxy server."""
    import uvicorn

    config = _get_config()

    _banner("Proxy Server")

    endpoint = f"http://{host}:{port}"

    # Server info panel
    info_lines = [
        f"  Endpoint   [bold #CC3333]{endpoint}[/bold #CC3333]",
        f"  Chat API   [bold #CC3333]{endpoint}/v1/chat/completions[/bold #CC3333]",
        f"  Models     [bold #CC3333]{endpoint}/v1/models[/bold #CC3333]",
        f"  Provider   [bold]{config.provider}[/bold]",
        f"  Model      [bold]{config.model}[/bold]",
        f"  Agent      [dim]{config.agent_id}[/dim]",
    ]

    # API key status: check env + stored config
    from cvc.core.models import GlobalConfig as GC_Serve
    gc_serve = GC_Serve.load()

    env_key_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
    env_key = env_key_map.get(config.provider, "")
    if env_key:
        has_env = bool(os.environ.get(env_key))
        has_stored = bool(gc_serve.api_keys.get(config.provider))
        if has_env:
            key_status = "[#55AA55]● env var[/#55AA55]"
        elif has_stored:
            key_status = "[#55AA55]● saved[/#55AA55]"
        else:
            key_status = "[red]● missing[/red]"
        info_lines.append(f"  API Key    {key_status}  [dim]({env_key})[/dim]")
    elif config.provider == "ollama":
        info_lines.append(f"  API Key    [dim]not needed (local)[/dim]")

    console.print(
        Panel(
            "\n".join(info_lines),
            border_style="#5C1010",
            title="[bold #55AA55]Starting[/bold #55AA55]",
            padding=(1, 2),
        )
    )

    # Quick connection reference
    console.print()
    console.print(
        Panel(
            "  [bold white]Connect your tools:[/bold white]\n\n"
            f"  Base URL   [bold #CC3333]{endpoint}/v1[/bold #CC3333]\n"
            f"  API Key    [#CC3333]cvc[/#CC3333]  [dim](any non-empty string works)[/dim]\n"
            f"  Model      [#CC3333]{config.model}[/#CC3333]\n\n"
            f"  [bold white]Claude Code CLI:[/bold white]\n"
            f"  [#CC3333]export ANTHROPIC_BASE_URL={endpoint}[/#CC3333]\n\n"
            "  [bold white]Auth-based IDEs (Antigravity, Windsurf, native Copilot):[/bold white]\n"
            "  Run [bold]cvc mcp[/bold] to start the MCP server instead.\n\n"
            "  [dim]Works with: VS Code, Antigravity, Cursor, Windsurf, Cline,\n"
            "  Continue.dev, Claude Code, Codex CLI, Gemini CLI, Kiro CLI,\n"
            "  Aider, Open WebUI, Firebase Studio, and any OpenAI-compatible tool.[/dim]\n\n"
            "  [dim]Run[/dim] [bold]cvc connect[/bold] [dim]for tool-specific setup instructions.[/dim]",
            border_style="#5C1010",
            title="[bold #8B7070]Connect Your Tools[/bold #8B7070]",
            padding=(1, 2),
        )
    )

    console.print(
        f"\n  [dim]Press[/dim] [bold]Ctrl+C[/bold] [dim]to stop.[/dim]\n"
    )

    uvicorn.run(
        "cvc.proxy:app",
        host=host,
        port=port,
        reload=do_reload,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# connect (interactive tool connection wizard)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--host", default="127.0.0.1", help="Proxy host.")
@click.option("--port", default=8000, type=int, help="Proxy port.")
@click.argument("tool", required=False, default=None)
def connect(tool: str | None, host: str, port: int) -> None:
    """Show how to connect your AI tool to CVC.

    Run without arguments for an interactive picker, or specify a tool:

      cvc connect vscode
      cvc connect antigravity
      cvc connect cursor
      cvc connect windsurf
      cvc connect cline
      cvc connect claude-code
      cvc connect codex-cli
      cvc connect gemini-cli
      cvc connect kiro-cli
      cvc connect aider
      cvc connect open-webui
      cvc connect firebase-studio
      cvc connect --all
    """
    config = _get_config()
    endpoint = f"http://{host}:{port}"
    model = config.model

    _banner("Connect Your Tools")

    # Show the universal connection info first
    console.print(
        Panel(
            f"  [bold white]CVC Proxy Endpoint[/bold white]\n\n"
            f"  Base URL   [bold #CC3333]{endpoint}/v1[/bold #CC3333]\n"
            f"  API Key    [#CC3333]cvc[/#CC3333]  [dim](any non-empty string — CVC handles auth)[/dim]\n"
            f"  Model      [#CC3333]{model}[/#CC3333]\n\n"
            f"  [dim]CVC exposes a fully OpenAI-compatible API.[/dim]\n"
            f"  [dim]Any tool that supports custom OpenAI endpoints will work.[/dim]",
            border_style="#8B0000",
            title="[bold white]Universal Connection Info[/bold white]",
            padding=(1, 2),
        )
    )
    console.print()

    if tool and tool == "--all":
        # Show all guides
        for key in TOOL_GUIDES:
            console.print(_format_tool_guide(key, endpoint, model))
            console.print()
        return

    if tool:
        # Direct tool specified
        key = tool.lower().replace(" ", "-")
        # Allow shorthand lookups
        aliases = {
            "code": "vscode",
            "vs-code": "vscode",
            "visual-studio-code": "vscode",
            "continue": "vscode-continue",
            "continue.dev": "vscode-continue",
            "cline": "vscode-cline",
            "roo": "vscode-cline",
            "copilot": "vscode-copilot",
            "claude": "claude-code",
            "claude-cli": "claude-code",
            "gemini": "gemini-cli",
            "kiro": "kiro-cli",
            "webui": "open-webui",
            "openwebui": "open-webui",
            "firebase": "firebase-studio",
            "idx": "firebase-studio",
            "windsurf": "windsurf",
            "codeium": "windsurf",
            "codex": "codex-cli",
            "openai-codex": "codex-cli",
        }
        key = aliases.get(key, key)

        if key in TOOL_GUIDES:
            console.print(_format_tool_guide(key, endpoint, model))
        else:
            _error(f"Unknown tool: [bold]{tool}[/bold]")
            _info(f"Available: {', '.join(TOOL_GUIDES.keys())}")
        return

    # ─── Interactive picker ───────────────────────────────────────────────
    categories = {
        "IDE": [],
        "IDE Extension": [],
        "CLI Tool": [],
        "Web Interface": [],
        "Cloud IDE": [],
    }
    for key, guide in TOOL_GUIDES.items():
        cat = guide.get("category", "Other")
        if cat in categories:
            categories[cat].append((key, guide))

    # Build numbered list grouped by category
    all_items: list[tuple[str, dict]] = []
    colors = {"IDE": "#CC3333", "IDE Extension": "#CC6666", "CLI Tool": "#AA8844", "Web Interface": "#AA6666", "Cloud IDE": "red"}

    for cat, items in categories.items():
        if not items:
            continue
        color = colors.get(cat, "white")
        console.print(f"  [{color}]{cat}[/{color}]")
        for key, guide in items:
            idx = len(all_items) + 1
            all_items.append((key, guide))
            console.print(
                f"    [{color}]{idx}[/{color}]  {guide['icon']}  [bold]{guide['name']}[/bold]"
            )
        console.print()

    console.print(f"    [dim]{len(all_items) + 1}[/dim]  📋  [bold]Show all guides at once[/bold]")
    console.print()

    choice = click.prompt(
        "  Pick a tool (number)",
        type=click.IntRange(1, len(all_items) + 1),
        default=1,
    )

    console.print()

    if choice == len(all_items) + 1:
        # Show all
        for key in TOOL_GUIDES:
            console.print(_format_tool_guide(key, endpoint, model))
            console.print()
    else:
        key, _ = all_items[choice - 1]
        console.print(_format_tool_guide(key, endpoint, model))

    console.print()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@main.command()
@click.option("--path", default=".", help="Project root to initialise.")
def init(path: str) -> None:
    """Initialise a .cvc/ directory in the project."""
    from cvc.core.models import CVCConfig

    project_root = Path(path).resolve()
    config = CVCConfig.for_project(project_root=project_root)
    config.ensure_dirs()

    from cvc.core.database import ContextDatabase
    db = ContextDatabase(config)

    # Report vector store status
    vector_status = "[#55AA55]● enabled[/#55AA55]" if db.vectors.available else "[#CC3333]✗ unavailable[/#CC3333]"
    chroma_count = 0
    if db.vectors.available and db.vectors._collection:
        chroma_count = db.vectors._collection.count()

    console.print(
        Panel(
            f"  Directory  [bold]{config.cvc_root}[/bold]\n"
            f"  Database   [dim]{config.db_path}[/dim]\n"
            f"  Objects    [dim]{config.objects_dir}[/dim]\n"
            f"  Vectors    {vector_status}  [dim]{config.chroma_persist_dir}[/dim]\n"
            f"  Embeddings [dim]{chroma_count} indexed[/dim]",
            border_style="#5C1010",
            title="[bold #55AA55]✓ Initialised[/bold #55AA55]",
            padding=(1, 2),
        )
    )
    _hint("Run [bold]cvc setup[/bold] for guided provider configuration.")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@main.command()
def status() -> None:
    """Show CVC status: active branch, HEAD, branches."""
    engine, db = _get_engine()
    config = engine.config

    head_short = (engine.head_hash or "—")[:12]
    ctx_messages = engine.context_window
    ctx_size = len(ctx_messages)

    # Break down by role
    user_msgs = sum(1 for m in ctx_messages if m.role == "user")
    assistant_msgs = sum(1 for m in ctx_messages if m.role == "assistant")
    tool_msgs = sum(1 for m in ctx_messages if m.role == "tool")
    system_msgs = sum(1 for m in ctx_messages if m.role == "system")

    # Build context detail string
    if ctx_size > 0:
        ctx_detail = (
            f"[bold]{ctx_size}[/bold] messages  "
            f"[dim]({user_msgs} user, {assistant_msgs} assistant, "
            f"{tool_msgs} tool, {system_msgs} system)[/dim]"
        )
    else:
        ctx_detail = "[dim]0 messages — start a chat with [bold]cvc chat[/bold][/dim]"

    # Count total commits
    commits = db.index.list_commits(branch=engine.active_branch, limit=9999)
    commit_count = len(commits)

    # Check persistent cache
    cache_file = config.cvc_root / "context_cache.json"
    cache_status = "[#55AA55]●[/#55AA55] active" if cache_file.exists() else "[dim]○ none[/dim]"

    # Header info
    console.print(
        Panel(
            f"  Agent      [bold]{config.agent_id}[/bold]\n"
            f"  Branch     [bold #CC3333]{engine.active_branch}[/bold #CC3333]\n"
            f"  HEAD       [bold #CCAA44]{head_short}[/bold #CCAA44]\n"
            f"  Context    {ctx_detail}\n"
            f"  Commits    [bold]{commit_count}[/bold]\n"
            f"  Cache      {cache_status}\n"
            f"  Provider   [dim]{config.provider} / {config.model}[/dim]",
            border_style="#8B0000",
            title="[bold white]CVC Status[/bold white]",
            padding=(1, 2),
        )
    )

    branches = db.index.list_branches()
    if branches:
        table = Table(
            box=box.ROUNDED,
            border_style="dim",
            show_header=True,
            header_style="bold #CC3333",
        )
        table.add_column("", width=3)
        table.add_column("Branch", style="bold")
        table.add_column("HEAD", style="#CCAA44")
        table.add_column("Status")
        for b in branches:
            is_active = b.name == engine.active_branch
            marker = "[bold #55AA55]●[/bold #55AA55]" if is_active else "[dim]○[/dim]"
            name_style = "bold #CC3333" if is_active else "white"
            status_style = "green" if b.status.value == "active" else "dim"
            table.add_row(
                marker,
                f"[{name_style}]{b.name}[/{name_style}]",
                b.head_hash[:12],
                f"[{status_style}]{b.status.value}[/{status_style}]",
            )
        console.print(table)

    db.close()


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------

TYPE_ICONS = {
    "checkpoint": ">>",
    "analysis": "**",
    "generation": "++",
    "rollback": "<<",
    "merge": "<>",
    "anchor": "##",
}


@main.command()
@click.option("-n", "--limit", default=20, type=int, help="Max commits to show.")
def log(limit: int) -> None:
    """Show commit history for the active branch."""
    engine, db = _get_engine()
    entries = engine.log(limit=limit)

    if not entries:
        _warn("No commits yet on this branch.")
        _hint("Create your first commit: [bold]cvc commit -m \"initial state\"[/bold]")
        db.close()
        return

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold #CC3333",
        title=f"[bold white]Commit Log[/bold white] [dim]— {engine.active_branch}[/dim]",
        title_style="",
    )
    table.add_column("", width=2)
    table.add_column("Hash", style="#CCAA44", width=12)
    table.add_column("Type", style="#CC3333", width=12)
    table.add_column("Message", ratio=1)
    table.add_column("D", width=3, justify="center")

    for i, e in enumerate(entries):
        icon = TYPE_ICONS.get(e["type"], ">")
        delta = "[dim]d[/dim]" if e["is_delta"] else "[#55AA55]●[/#55AA55]"
        msg = e["message"][:55]
        if len(e["message"]) > 55:
            msg += "…"
        table.add_row(icon, e["short"], e["type"], msg, delta)

    console.print(table)
    console.print(f"  [dim]{len(entries)} commit(s) shown[/dim]\n")
    db.close()


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

@main.command()
@click.option("-m", "--message", required=True, help="Commit message.")
@click.option(
    "-t", "--type", "commit_type",
    default="checkpoint",
    type=click.Choice(["checkpoint", "analysis", "generation"], case_sensitive=False),
    help="Commit type.",
)
@click.option("--tag", "tags", multiple=True, help="Tags (can be repeated).")
def commit(message: str, commit_type: str, tags: tuple[str, ...]) -> None:
    """Create a cognitive commit (save the agent's brain state)."""
    from cvc.core.models import CVCCommitRequest

    engine, db = _get_engine()
    result = engine.commit(
        CVCCommitRequest(message=message, commit_type=commit_type, tags=list(tags))
    )

    if result.success:
        short_hash = (result.commit_hash or "")[:12]
        console.print(
            Panel(
                f"  [bold]{message}[/bold]\n"
                f"  Hash     [#CCAA44]{short_hash}[/#CCAA44]\n"
                f"  Type     [#CC3333]{commit_type}[/#CC3333]\n"
                f"  Branch   [dim]{engine.active_branch}[/dim]",
                border_style="#5C1010",
                title="[bold #55AA55]✓ Committed[/bold #55AA55]",
                padding=(1, 2),
            )
        )
    else:
        _error(result.message)

    db.close()


# ---------------------------------------------------------------------------
# branch
# ---------------------------------------------------------------------------

@main.command()
@click.argument("name")
@click.option("-d", "--description", default="", help="Branch purpose/description.")
def branch(name: str, description: str) -> None:
    """Create and switch to a new exploration branch."""
    from cvc.core.models import CVCBranchRequest

    engine, db = _get_engine()
    result = engine.branch(CVCBranchRequest(name=name, description=description))

    if result.success:
        console.print(
            Panel(
                f"  [bold #CC3333]{name}[/bold #CC3333]\n"
                f"  From     [dim]{engine.active_branch}[/dim]\n"
                f"  HEAD     [#CCAA44]{(result.commit_hash or '')[:12]}[/#CCAA44]",
                border_style="#5C1010",
                title="[bold #55AA55]✓ Branch Created[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        if description:
            _info(f"Description: {description}")
    else:
        _error(result.message)

    db.close()


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

@main.command()
@click.argument("source_branch")
@click.option("--target", default="main", help="Target branch (default: main).")
def merge(source_branch: str, target: str) -> None:
    """Merge a branch into the target (semantic three-way merge)."""
    from cvc.core.models import CVCMergeRequest

    engine, db = _get_engine()
    result = engine.merge(CVCMergeRequest(source_branch=source_branch, target_branch=target))

    if result.success:
        console.print(
            Panel(
                f"  [bold]{source_branch}[/bold] → [bold #CC3333]{target}[/bold #CC3333]\n"
                f"  Commit   [#CCAA44]{(result.commit_hash or '')[:12]}[/#CCAA44]",
                border_style="#5C1010",
                title="[bold #55AA55]✓ Merged[/bold #55AA55]",
                padding=(1, 2),
            )
        )
    else:
        _error(result.message)
        _hint(f"Check branch names with [bold]cvc status[/bold].")

    db.close()


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------

@main.command()
@click.argument("commit_hash")
def restore(commit_hash: str) -> None:
    """Time-travel: restore the agent's brain to a previous state."""
    from cvc.core.models import CVCRestoreRequest

    engine, db = _get_engine()
    result = engine.restore(CVCRestoreRequest(commit_hash=commit_hash))

    if result.success:
        console.print(
            Panel(
                f"  Restored to [#CCAA44]{commit_hash[:12]}[/#CCAA44]\n"
                f"  Branch   [dim]{engine.active_branch}[/dim]",
                border_style="#5C1010",
                title="[bold #55AA55]✓ Time-Travelled[/bold #55AA55]",
                padding=(1, 2),
            )
        )
    else:
        _error(result.message)
        _hint(
            "Use [bold]cvc log[/bold] to find valid commit hashes.\n"
            "Both full and short (12-char) hashes work."
        )

    db.close()


# ---------------------------------------------------------------------------
# VCS hooks
# ---------------------------------------------------------------------------

@main.command("install-hooks")
def install_hooks() -> None:
    """Install Git hooks for CVC ↔ Git synchronisation."""
    engine, db = _get_engine()
    from cvc.vcs.bridge import VCSBridge

    bridge = VCSBridge(engine.config, db)
    result = bridge.install_hooks()

    lines = []
    for hook, path in result.items():
        lines.append(f"  {hook}  [dim]→ {path}[/dim]")

    console.print(
        Panel(
            "\n".join(lines),
            border_style="#5C1010",
            title="[bold #55AA55]✓ Hooks Installed[/bold #55AA55]",
            padding=(1, 2),
        )
    )
    _info("CVC will now auto-sync with Git commits and checkouts.")
    db.close()


@main.command("capture-snapshot")
@click.option("--git-sha", default=None, help="Git SHA to link (auto-detected if omitted).")
def capture_snapshot(git_sha: str | None) -> None:
    """Capture CVC state linked to the current Git commit."""
    engine, db = _get_engine()
    from cvc.vcs.bridge import VCSBridge

    bridge = VCSBridge(engine.config, db)
    result = bridge.capture_snapshot(git_sha)

    if "error" in result:
        _error(result["error"])
    else:
        console.print(
            Panel(
                f"  Git    [dim]{result['git_sha'][:12]}[/dim]\n"
                f"  CVC    [#CCAA44]{result['cvc_hash'][:12]}[/#CCAA44]",
                border_style="#5C1010",
                title="[bold #55AA55]✓ Snapshot Captured[/bold #55AA55]",
                padding=(1, 2),
            )
        )

    db.close()


@main.command("restore-for-checkout")
@click.option("--git-sha", required=True, help="Git SHA being checked out.")
def restore_for_checkout(git_sha: str) -> None:
    """Restore CVC state corresponding to a Git checkout (called by hook)."""
    engine, db = _get_engine()
    from cvc.vcs.bridge import VCSBridge

    bridge = VCSBridge(engine.config, db)
    cvc_hash = bridge.restore_for_checkout(git_sha)

    if cvc_hash:
        from cvc.core.models import CVCRestoreRequest
        result = engine.restore(CVCRestoreRequest(commit_hash=cvc_hash))
        if result.success:
            _success(f"Restored CVC state: [#CCAA44]{cvc_hash[:12]}[/#CCAA44]")

    db.close()


# ---------------------------------------------------------------------------
# recall (natural language search across all conversations)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("query")
@click.option("-n", "--limit", default=10, type=int, help="Max results to return.")
@click.option("--deep/--no-deep", default=True, help="Search inside conversation content (slower but thorough).")
def recall(query: str, limit: int, deep: bool) -> None:
    """Search across ALL past conversations using natural language.

    \b
    Uses CVC's three-tier search:
      1. Semantic vector search (Tier 3, if Chroma is enabled)
      2. Commit message text search (Tier 1, always available)
      3. Deep content search (scans actual conversation messages)

    \b
    Examples:
      cvc recall "how did we implement auth?"
      cvc recall "database migration" --limit 5
      cvc recall "error handling" --no-deep
    """
    from datetime import datetime

    engine, db = _get_engine()

    console.print()
    console.print(
        f"  [bold #CC3333]Searching[/bold #CC3333] [dim]for:[/dim] "
        f"[bold white]\"{query}\"[/bold white]"
    )

    search_sources = []
    if db.vectors.available:
        search_sources.append("[#55AA55]semantic[/#55AA55]")
    search_sources.append("[#CCAA44]message[/#CCAA44]")
    if deep:
        search_sources.append("[#CC3333]deep content[/#CC3333]")
    console.print(f"  [dim]Sources:[/dim] {' + '.join(search_sources)}")
    console.print()

    results = engine.recall(query, limit=limit, deep=deep)

    if not results:
        _warn("No conversations found matching your query.")
        _hint(
            "Tips:\n"
            "• Try broader search terms\n"
            "• Use [bold]--deep[/bold] to search inside conversation content\n"
            "• Check [bold]cvc log[/bold] to see available commits"
        )
        db.close()
        return

    # Display results
    for i, r in enumerate(results, 1):
        ts = datetime.fromtimestamp(r["timestamp"])
        date_str = ts.strftime("%Y-%m-%d %H:%M")

        # Source badge
        src = r["relevance_source"]
        if src == "semantic":
            badge = "[bold #55AA55]SEMANTIC[/bold #55AA55]"
        elif src == "message":
            badge = "[bold #CCAA44]MESSAGE[/bold #CCAA44]"
        else:
            badge = "[bold #CC3333]CONTENT[/bold #CC3333]"

        # Distance indicator
        dist = r["distance"]
        if dist < 0.3:
            relevance = "[bold #55AA55]●●●[/bold #55AA55] High"
        elif dist < 0.6:
            relevance = "[bold #CCAA44]●●○[/bold #CCAA44] Medium"
        else:
            relevance = "[bold #CC3333]●○○[/bold #CC3333] Low"

        # Build result panel content
        content_lines = [
            f"  [dim]Commit[/dim]    [#CCAA44]{r['short_hash']}[/#CCAA44]  "
            f"[dim]{r['commit_type']}[/dim]",
            f"  [dim]Date[/dim]      {date_str}",
            f"  [dim]Source[/dim]    {badge}  {relevance}",
        ]
        if r["provider"] or r["model"]:
            content_lines.append(
                f"  [dim]Model[/dim]     "
                f"[#CC3333]{r.get('provider', '')}/{r.get('model', '')}[/#CC3333]"
            )

        # Show message
        msg = r["message"]
        if len(msg) > 120:
            msg = msg[:117] + "…"
        content_lines.append(f"  [dim]Message[/dim]   {msg}")

        # Show matching conversation excerpts
        matching = r.get("matching_messages", [])
        if matching:
            content_lines.append("")
            content_lines.append("  [bold white]Matching excerpts:[/bold white]")
            for mm in matching[:3]:
                role = mm["role"].upper()
                excerpt = mm["content"][:200]
                if len(mm["content"]) > 200:
                    excerpt += "…"
                content_lines.append(f"    [dim]{role}:[/dim] {excerpt}")

        console.print(
            Panel(
                "\n".join(content_lines),
                border_style="#5C1010" if i == 1 else "dim",
                title=f"[bold white]#{i}[/bold white]",
                title_align="left",
                padding=(0, 1),
            )
        )

    console.print(f"\n  [dim]{len(results)} result(s) found[/dim]")
    _hint(
        "View full context: [bold]cvc context --show --commit <hash>[/bold]\n"
        "Export as Markdown: [bold]cvc export --markdown --commit <hash>[/bold]"
    )
    console.print()
    db.close()


# ---------------------------------------------------------------------------
# context (display stored conversation content)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--show", is_flag=True, help="Display the full stored conversation content.")
@click.option("--commit", "commit_hash", default=None, help="Show context for a specific commit (default: current HEAD).")
@click.option("-n", "--limit", default=0, type=int, help="Limit number of messages shown (0 = all).")
@click.option("--role", default=None, type=click.Choice(["user", "assistant", "system", "tool"]), help="Filter by message role.")
def context(show: bool, commit_hash: str | None, limit: int, role: str | None) -> None:
    """Display stored conversation context.

    \b
    Without --show: displays a summary (count, roles, size)
    With    --show: displays the full conversation content

    \b
    Examples:
      cvc context               # Quick summary of current context
      cvc context --show        # Show the full conversation
      cvc context --show --commit abc123  # Show a specific commit's conversation
      cvc context --show --role user      # Show only user messages
      cvc context --show -n 20           # Show last 20 messages
    """
    from datetime import datetime

    engine, db = _get_engine()

    if commit_hash:
        # Load context from a specific commit
        commit = db.index.get_commit(commit_hash)
        if commit is None:
            _error(f"Commit '{commit_hash}' not found.")
            _hint("Use [bold]cvc log[/bold] to find valid commit hashes.")
            db.close()
            return
        blob = db.retrieve_blob(commit.commit_hash)
        if blob is None:
            _error(f"Could not reconstruct blob for commit '{commit_hash}'.")
            db.close()
            return
        messages = blob.messages
        context_source = f"commit {commit.commit_hash[:12]}"
        reasoning = blob.reasoning_trace
        token_count = blob.token_count
    else:
        # Use current context window
        messages = engine.context_window
        context_source = f"HEAD ({(engine.head_hash or '—')[:12]})"
        reasoning = engine._reasoning_trace
        token_count = sum(len(m.content.split()) for m in messages)

    # Apply role filter
    if role:
        messages = [m for m in messages if m.role == role]

    # Apply limit
    if limit > 0:
        messages = messages[-limit:]

    if not show:
        # Summary mode (existing behavior enhanced)
        total = len(messages)
        user_count = sum(1 for m in messages if m.role == "user")
        assistant_count = sum(1 for m in messages if m.role == "assistant")
        tool_count = sum(1 for m in messages if m.role == "tool")
        system_count = sum(1 for m in messages if m.role == "system")

        console.print(
            Panel(
                f"  [dim]Source[/dim]       {context_source}\n"
                f"  [dim]Messages[/dim]     [bold]{total}[/bold]\n"
                f"  [dim]  User[/dim]       {user_count}\n"
                f"  [dim]  Assistant[/dim]  {assistant_count}\n"
                f"  [dim]  Tool[/dim]       {tool_count}\n"
                f"  [dim]  System[/dim]     {system_count}\n"
                f"  [dim]Tokens[/dim]       ~{token_count}",
                border_style="#5C1010",
                title="[bold white]Context Summary[/bold white]",
                padding=(1, 2),
            )
        )
        _hint("Use [bold]cvc context --show[/bold] to view the actual conversation content.")
        db.close()
        return

    # Full conversation display
    if not messages:
        _warn("No messages in context.")
        _hint("Start a conversation with [bold]cvc agent[/bold] or create a commit.")
        db.close()
        return

    console.print()
    console.print(
        f"  [bold #CC3333]Context[/bold #CC3333] [dim]from[/dim] {context_source}  "
        f"[dim]({len(messages)} messages)[/dim]"
    )
    console.print()

    role_styles = {
        "system": ("#8B7070", "⚙️"),
        "user": ("#55AA55", "👤"),
        "assistant": ("#CC3333", "🤖"),
        "tool": ("#CCAA44", "🔧"),
    }

    for i, msg in enumerate(messages, 1):
        style, emoji = role_styles.get(msg.role, ("#888888", "❓"))
        ts = datetime.fromtimestamp(msg.timestamp)
        time_str = ts.strftime("%H:%M:%S")

        # Truncate very long messages for display
        content = msg.content
        truncated = False
        if len(content) > 2000:
            content = content[:2000]
            truncated = True

        header = f"{emoji} [bold {style}]{msg.role.upper()}[/bold {style}]  [dim]{time_str}[/dim]"

        panel_content = content
        if truncated:
            panel_content += f"\n\n[dim]… ({len(msg.content) - 2000} more chars)[/dim]"

        console.print(
            Panel(
                panel_content,
                border_style=style,
                title=header,
                title_align="left",
                padding=(0, 2),
            )
        )

    # Show reasoning trace if present
    if reasoning:
        console.print(
            Panel(
                reasoning[:1000] + ("…" if len(reasoning) > 1000 else ""),
                border_style="#8B7070",
                title="[bold #8B7070]Reasoning Trace[/bold #8B7070]",
                title_align="left",
                padding=(0, 2),
            )
        )

    console.print(f"\n  [dim]{len(messages)} message(s) displayed[/dim]\n")
    db.close()


# ---------------------------------------------------------------------------
# export (conversation to shareable formats)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--markdown", "as_markdown", is_flag=True, help="Export as shareable Markdown file.")
@click.option("--commit", "commit_hash", default=None, help="Commit hash to export (default: HEAD).")
@click.option("-o", "--output", "output_path", default=None, help="Output file path (auto-generated if omitted).")
def export(as_markdown: bool, commit_hash: str | None, output_path: str | None) -> None:
    """Export a commit's conversation as a shareable file.

    \b
    Perfect for code reviews — share the AI's reasoning with your team.

    \b
    Examples:
      cvc export --markdown                      # Export HEAD as Markdown
      cvc export --markdown --commit abc123       # Export specific commit
      cvc export --markdown -o review.md          # Custom output filename
    """
    engine, db = _get_engine()

    if not as_markdown:
        _warn("Please specify an export format.")
        _hint("Currently supported: [bold]--markdown[/bold]\n\nExample: [bold]cvc export --markdown[/bold]")
        db.close()
        return

    try:
        md_content, resolved_hash = engine.export_markdown(commit_hash)
    except ValueError as exc:
        _error(str(exc))
        _hint("Use [bold]cvc log[/bold] to find valid commit hashes.")
        db.close()
        return

    # Determine output path
    if output_path is None:
        short = resolved_hash[:12]
        output_path = f"cvc-export-{short}.md"

    out = Path(output_path)
    out.write_text(md_content, encoding="utf-8")

    # Stats
    lines_count = md_content.count("\n")
    size_kb = len(md_content.encode("utf-8")) / 1024

    console.print(
        Panel(
            f"  [dim]Commit[/dim]    [#CCAA44]{resolved_hash[:12]}[/#CCAA44]\n"
            f"  [dim]Format[/dim]    Markdown\n"
            f"  [dim]File[/dim]      [bold]{out.resolve()}[/bold]\n"
            f"  [dim]Size[/dim]      {size_kb:.1f} KB ({lines_count} lines)",
            border_style="#5C1010",
            title="[bold #55AA55]✓ Exported[/bold #55AA55]",
            padding=(1, 2),
        )
    )
    _hint(
        "Share this file during code reviews so your team can\n"
        "see exactly what the AI reasoned about."
    )
    console.print()
    db.close()


# ---------------------------------------------------------------------------
# inject (cross-project context transfer)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("source_project")
@click.option("--query", "-q", required=True, help="Natural language query to find relevant conversations.")
@click.option("-n", "--limit", default=5, type=int, help="Max conversations to pull from source.")
def inject(source_project: str, query: str, limit: int) -> None:
    """Pull relevant conversations from another project into this one.

    \b
    Cross-project context transfer — no other tool does this.
    Search another project's CVC history and inject the matching
    conversations into your current project as context.

    \b
    Examples:
      cvc inject ../auth-service --query "JWT token handling"
      cvc inject /projects/api --query "database migration patterns" -n 3
      cvc inject ../shared-lib -q "error handling middleware"
    """
    source_path = Path(source_project).resolve()

    if not source_path.is_dir():
        _error(f"Directory not found: {source_path}")
        return

    if not (source_path / ".cvc").is_dir():
        _error(f"No .cvc/ directory found at: {source_path}")
        _hint(
            f"Make sure the source project has CVC initialised:\n"
            f"  [bold]cd {source_path} && cvc init[/bold]"
        )
        return

    engine, db = _get_engine()

    console.print()
    console.print(
        f"  [bold #CC3333]Injecting context[/bold #CC3333]\n"
        f"  [dim]From[/dim]     [bold]{source_path.name}[/bold] [dim]({source_path})[/dim]\n"
        f"  [dim]Query[/dim]    [bold white]\"{query}\"[/bold white]\n"
        f"  [dim]Limit[/dim]    {limit} conversations"
    )
    console.print()

    result = engine.inject_from_project(source_path, query, limit=limit)

    if result.success:
        detail = result.detail
        console.print(
            Panel(
                f"  [dim]Source[/dim]              [bold]{detail.get('source_project', '')}[/bold]\n"
                f"  [dim]Query[/dim]               \"{detail.get('query', '')}\"\n"
                f"  [dim]Matching commits[/dim]    {detail.get('matching_commits', 0)}\n"
                f"  [dim]Messages injected[/dim]   [bold #55AA55]{detail.get('injected_messages', 0)}[/bold #55AA55]\n"
                f"  [dim]Commit[/dim]              [#CCAA44]{(result.commit_hash or '')[:12]}[/#CCAA44]",
                border_style="#5C1010",
                title="[bold #55AA55]✓ Context Injected[/bold #55AA55]",
                padding=(1, 2),
            )
        )

        # Show which commits were searched
        searched = detail.get("commits_searched", [])
        if searched:
            console.print("  [dim]Commits searched:[/dim]")
            for sh in searched:
                console.print(f"    [dim]→[/dim] [#CCAA44]{sh}[/#CCAA44]")
            console.print()

        _hint(
            "The injected context is now part of your conversation.\n"
            "View it: [bold]cvc context --show[/bold]\n"
            "Your agent will use this context in future responses."
        )
    else:
        _error(result.message)
        _hint(
            "Tips:\n"
            "• Make sure the source project has CVC commits\n"
            "• Try broader search terms\n"
            "• Check with: [bold]cd <source> && cvc log[/bold]"
        )

    console.print()
    db.close()


# ---------------------------------------------------------------------------
# diff (knowledge / decision diff between commits)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("hash_a")
@click.argument("hash_b", required=False, default=None)
def diff(hash_a: str, hash_b: str | None) -> None:
    """Show knowledge/decision differences between two commits.

    \b
    Compare what changed between two cognitive commits — messages added
    or removed, reasoning trace changes, source file changes, and
    metadata differences.

    If only one hash is given, compares against HEAD.

    \b
    Examples:
      cvc diff abc123 def456       # Compare two commits
      cvc diff abc123              # Compare commit against HEAD
    """
    engine, db = _get_engine()

    try:
        result = engine.diff(hash_a, hash_b)
    except ValueError as exc:
        _error(str(exc))
        _hint("Use [bold]cvc log[/bold] to find valid commit hashes.")
        db.close()
        return

    ca = result["commit_a"]
    cb = result["commit_b"]

    console.print()
    console.print(
        Panel(
            f"  [dim]From[/dim]  [#CCAA44]{ca['short']}[/#CCAA44]  {ca['message'][:60]}\n"
            f"  [dim]To  [/dim]  [#CCAA44]{cb['short']}[/#CCAA44]  {cb['message'][:60]}",
            border_style="#5C1010",
            title="[bold #CC3333]◈ Cognitive Diff[/bold #CC3333]",
            padding=(1, 2),
        )
    )

    # Messages diff
    msgs = result["messages"]
    msg_table = Table(
        box=box.SIMPLE,
        border_style="dim",
        show_header=False,
        padding=(0, 1),
    )
    msg_table.add_column("", width=3)
    msg_table.add_column("Detail")

    msg_table.add_row("[dim]Common[/dim]", f"{msgs['common_count']} messages unchanged")
    msg_table.add_row("[#55AA55]+[/#55AA55]", f"[#55AA55]{msgs['added_count']} messages added[/#55AA55]")
    msg_table.add_row("[red]−[/red]", f"[red]{msgs['removed_count']} messages removed[/red]")

    console.print(
        Panel(msg_table, border_style="dim", title="[bold]Messages[/bold]", padding=(0, 1))
    )

    # Show added messages (preview)
    if msgs["added"]:
        console.print("  [bold #55AA55]+ Added messages:[/bold #55AA55]")
        for m in msgs["added"][:5]:
            preview = m["content"][:120].replace("\n", " ")
            console.print(f"    [#55AA55]+ [{m['role']}][/#55AA55] {preview}")
        if len(msgs["added"]) > 5:
            console.print(f"    [dim]… and {len(msgs['added']) - 5} more[/dim]")
        console.print()

    if msgs["removed"]:
        console.print("  [bold red]− Removed messages:[/bold red]")
        for m in msgs["removed"][:5]:
            preview = m["content"][:120].replace("\n", " ")
            console.print(f"    [red]− [{m['role']}][/red] {preview}")
        if len(msgs["removed"]) > 5:
            console.print(f"    [dim]… and {len(msgs['removed']) - 5} more[/dim]")
        console.print()

    # Source files
    sf = result["source_files"]
    if sf["added"] or sf["removed"] or sf["modified"]:
        console.print("  [bold]Source Files:[/bold]")
        for f in sf["added"]:
            console.print(f"    [#55AA55]+ {f}[/#55AA55]")
        for f in sf["removed"]:
            console.print(f"    [red]− {f}[/red]")
        for f in sf["modified"]:
            console.print(f"    [#CCAA44]~ {f}[/#CCAA44]")
        console.print()

    # Reasoning trace
    rt = result["reasoning_trace"]
    if rt["changed"]:
        console.print("  [bold #CCAA44]⚡ Reasoning trace changed[/bold #CCAA44]")
        if rt["from"]:
            console.print(f"    [dim]From:[/dim] {rt['from'][:100]}…")
        if rt["to"]:
            console.print(f"    [dim]To:  [/dim] {rt['to'][:100]}…")
        console.print()

    # Metadata changes
    meta = result["metadata_changes"]
    if meta:
        console.print("  [bold]Metadata changes:[/bold]")
        for field, vals in meta.items():
            console.print(
                f"    {field}: [red]{vals['from']}[/red] → [#55AA55]{vals['to']}[/#55AA55]"
            )
        console.print()

    # Token delta
    td = result["token_delta"]
    if td > 0:
        console.print(f"  [dim]Token delta:[/dim] [#55AA55]+{td}[/#55AA55]")
    elif td < 0:
        console.print(f"  [dim]Token delta:[/dim] [red]{td}[/red]")
    else:
        console.print(f"  [dim]Token delta:[/dim] 0 (unchanged)")
    console.print()

    db.close()


# ---------------------------------------------------------------------------
# stats (analytics dashboard)
# ---------------------------------------------------------------------------

@main.command()
def stats() -> None:
    """Show an analytics dashboard for your CVC project.

    \b
    Displays aggregate statistics across all commits:
    total tokens, costs, message counts, commit types,
    providers/models used, most-discussed files, and timing patterns.

    \b
    Examples:
      cvc stats
    """
    engine, db = _get_engine()
    result = engine.stats()

    if result.get("total_commits", 0) == 0:
        _warn("No commits found. Create some commits first.")
        db.close()
        return

    console.print()

    # Header
    console.print(
        Panel(
            f"  [dim]Commits[/dim]      [bold]{result['total_commits']}[/bold]\n"
            f"  [dim]Messages[/dim]     [bold]{result['total_messages']}[/bold]\n"
            f"  [dim]Tokens[/dim]       [bold]{result['total_tokens']:,}[/bold]\n"
            f"  [dim]Est. Cost[/dim]    [bold]${result['estimated_cost_usd']:.4f}[/bold]\n"
            f"  [dim]Avg Size[/dim]     [bold]{result['average_commit_size']:.1f}[/bold] messages/commit\n"
            f"  [dim]Branch[/dim]       [bold]{result['current_branch']}[/bold] ({result['current_context_messages']} msgs in context)",
            border_style="#5C1010",
            title="[bold #CC3333]📊 CVC Analytics Dashboard[/bold #CC3333]",
            padding=(1, 2),
        )
    )

    # Time span
    ts = result.get("time_span", {})
    if ts:
        console.print(
            f"  [dim]Period[/dim]    {ts.get('first_commit', '?')} → {ts.get('last_commit', '?')}"
            f"  ({ts.get('span_days', 0)} days, {ts.get('commits_per_day', 0)} commits/day)"
        )
        console.print()

    # Tables side by side
    # Commit types
    ct = result.get("commit_types", {})
    if ct:
        type_table = Table(
            box=box.SIMPLE,
            border_style="dim",
            title="[bold]Commit Types[/bold]",
            title_style="bold",
            show_header=True,
            header_style="dim",
        )
        type_table.add_column("Type", style="bold")
        type_table.add_column("Count", justify="right")
        for t, c in ct.items():
            type_table.add_row(t, str(c))
        console.print(type_table)

    # Messages by role
    mr = result.get("messages_by_role", {})
    if mr:
        role_table = Table(
            box=box.SIMPLE,
            border_style="dim",
            title="[bold]Messages by Role[/bold]",
            title_style="bold",
            show_header=True,
            header_style="dim",
        )
        role_table.add_column("Role", style="bold")
        role_table.add_column("Count", justify="right")
        for r, c in mr.items():
            role_table.add_row(r, str(c))
        console.print(role_table)

    # Providers & Models
    providers = result.get("providers", {})
    models = result.get("models", {})
    if providers or models:
        pm_table = Table(
            box=box.SIMPLE,
            border_style="dim",
            title="[bold]Providers & Models[/bold]",
            title_style="bold",
            show_header=True,
            header_style="dim",
        )
        pm_table.add_column("Provider/Model", style="bold")
        pm_table.add_column("Commits", justify="right")
        for p, c in providers.items():
            pm_table.add_row(f"[#CC3333]{p}[/#CC3333]", str(c))
        for m, c in models.items():
            pm_table.add_row(f"  └ {m}", str(c))
        console.print(pm_table)

    # Branches
    br = result.get("branches", {})
    if br:
        console.print(
            f"  [bold]Branches:[/bold] {br['total']} total "
            f"({br['active']} active, {br['merged']} merged)"
        )
        branch_names = br.get("names", [])
        if branch_names:
            for bn in branch_names[:10]:
                marker = " [#55AA55]◄[/#55AA55]" if bn == result.get("current_branch") else ""
                console.print(f"    [dim]→[/dim] {bn}{marker}")
        console.print()

    # Top files
    tf = result.get("top_files", {})
    if tf:
        file_table = Table(
            box=box.SIMPLE,
            border_style="dim",
            title="[bold]Most Referenced Files[/bold]",
            title_style="bold",
            show_header=True,
            header_style="dim",
        )
        file_table.add_column("File", style="bold")
        file_table.add_column("Refs", justify="right")
        for f, c in list(tf.items())[:10]:
            file_table.add_row(f, str(c))
        console.print(file_table)

    # Peak hours
    ph = result.get("peak_hours", [])
    if ph:
        console.print("  [bold]Peak Coding Hours:[/bold]")
        for item in ph:
            h = item["hour"]
            c = item["commits"]
            bar = "█" * min(c, 30)
            console.print(f"    [dim]{h:02d}:00[/dim]  {bar} ({c})")
        bd = result.get("busiest_day", "N/A")
        console.print(f"    [dim]Busiest day:[/dim] [bold]{bd}[/bold]")
        console.print()

    # Tags
    tags = result.get("top_tags", {})
    if tags:
        tag_str = ", ".join(f"[#CCAA44]{t}[/#CCAA44]({c})" for t, c in tags.items())
        console.print(f"  [bold]Tags:[/bold] {tag_str}")
        console.print()

    db.close()


# ---------------------------------------------------------------------------
# compact (AI-powered context compression)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--smart/--no-smart", default=True, help="Use smart heuristic compression (default: smart).")
@click.option("--keep-recent", "-k", default=10, type=int, help="Number of recent messages to always keep.")
@click.option("--target-ratio", "-r", default=0.5, type=float, help="Target compression ratio (0.0-1.0).")
def compact(smart: bool, keep_recent: int, target_ratio: float) -> None:
    """Compress your context window to reduce token usage.

    \b
    Smart compression preserves important messages (decisions, code,
    architecture notes) while summarising routine conversation.

    \b
    Modes:
      --smart       Heuristic analysis: keeps decisions + code + recent (default)
      --no-smart    Simple truncation: keeps only the N most recent messages

    \b
    Examples:
      cvc compact --smart                    # Smart compression (default)
      cvc compact --no-smart --keep-recent 5 # Keep only last 5 messages
      cvc compact -k 20                      # Keep 20 recent messages
    """
    engine, db = _get_engine()

    original = len(engine.context_window)
    original_tokens = sum(len(m.content.split()) for m in engine.context_window)

    console.print()
    console.print(
        f"  [bold #CC3333]Compacting context[/bold #CC3333]\n"
        f"  [dim]Mode[/dim]      {'Smart (heuristic)' if smart else 'Simple truncation'}\n"
        f"  [dim]Current[/dim]   {original} messages (~{original_tokens} tokens)\n"
        f"  [dim]Keep[/dim]      {keep_recent} recent messages"
    )
    console.print()

    result = engine.compact(smart=smart, keep_recent=keep_recent, target_ratio=target_ratio)

    if result.success:
        detail = result.detail
        ratio = detail.get("compression_ratio", 1.0)
        pct = (1 - ratio) * 100

        console.print(
            Panel(
                f"  [dim]Before[/dim]       {detail.get('original_messages', '?')} messages ({detail.get('original_tokens', '?')} tokens)\n"
                f"  [dim]After[/dim]        {detail.get('final_messages', '?')} messages ({detail.get('final_tokens', '?')} tokens)\n"
                f"  [dim]Saved[/dim]        [bold #55AA55]{pct:.0f}%[/bold #55AA55] token reduction\n"
                f"  [dim]Mode[/dim]         {detail.get('mode', '?')}\n"
                + (
                    f"  [dim]Preserved[/dim]    {detail.get('important_preserved', 0)} important messages\n"
                    f"  [dim]Summarised[/dim]   {detail.get('summarised_chunks', 0)} chunks\n"
                    if detail.get("mode") == "smart" else ""
                )
                + (
                    f"  [dim]Commit[/dim]       [#CCAA44]{(result.commit_hash or '')[:12]}[/#CCAA44]"
                    if result.commit_hash else ""
                ),
                border_style="#5C1010",
                title="[bold #55AA55]✓ Compacted[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        _hint("Your context window is now smaller. Future LLM calls will use fewer tokens.")
    else:
        _warn(result.message)

    console.print()
    db.close()


# ---------------------------------------------------------------------------
# timeline (ASCII timeline of all AI interactions)
# ---------------------------------------------------------------------------

@main.command()
@click.option("-n", "--limit", default=30, type=int, help="Maximum commits to show.")
def timeline(limit: int) -> None:
    """Show an ASCII timeline of all AI interactions.

    \b
    Displays a beautiful visual timeline across all branches,
    showing commits, merges, branch points, and provider/model info.

    \b
    Examples:
      cvc timeline             # Show last 30 commits
      cvc timeline -n 50       # Show last 50 commits
    """
    engine, db = _get_engine()
    result = engine.timeline(limit=limit)

    if result.get("total_commits", 0) == 0:
        _warn("No commits found.")
        db.close()
        return

    console.print()

    # Branch legend
    branches = result.get("branches", [])
    if branches:
        branch_str = "  ".join(
            f"[bold {'#55AA55' if b['is_active'] else '#CCAA44'}]{b['name']}[/bold {'#55AA55' if b['is_active'] else '#CCAA44'}]"
            f"{'◄' if b['is_active'] else ''}"
            for b in branches
        )
        console.print(f"  [dim]Branches:[/dim] {branch_str}")
        console.print()

    # Timeline
    events = result.get("events", [])

    # Assign branch colors for visual distinction
    branch_colors = ["#CC3333", "#55AA55", "#CCAA44", "#5599CC", "#AA55AA", "#CC8844"]
    branch_color_map: dict[str, str] = {}
    for i, b in enumerate(branches):
        branch_color_map[b["name"]] = branch_colors[i % len(branch_colors)]

    TYPE_ICONS = {
        "checkpoint": "●",
        "analysis": "◎",
        "generation": "◉",
        "rollback": "↺",
        "merge": "⊕",
        "anchor": "◆",
    }

    for event in events:
        icon = TYPE_ICONS.get(event["type"], event.get("icon", "●"))
        primary_branch = event["branches"][0] if event["branches"] else "?"
        color = branch_color_map.get(primary_branch, "#CC3333")

        # Branch indicator line
        if event.get("is_merge"):
            parents = event.get("parents", [])
            console.print(
                f"  [{color}]  ╔═══╗[/{color}]"
            )
            line_prefix = f"  [{color}]  ║ {icon} ║[/{color}]"
        elif event.get("is_branch_point"):
            line_prefix = f"  [{color}]  ├─{icon}─┤[/{color}]"
        else:
            line_prefix = f"  [{color}]  │ {icon} │[/{color}]"

        # Build the main line
        short = event["short"]
        msg = event["message"][:50]
        time_str = event["time_str"]
        provider = event.get("provider", "")
        model = event.get("model", "")
        pm_str = ""
        if provider and model:
            pm_str = f" [dim]({provider}/{model})[/dim]"
        elif provider:
            pm_str = f" [dim]({provider})[/dim]"

        tags = event.get("tags", [])
        tag_str = ""
        if tags:
            tag_str = " " + " ".join(f"[#CCAA44]#{t}[/#CCAA44]" for t in tags[:3])

        branch_labels = ""
        if len(event["branches"]) > 1:
            branch_labels = " [dim](" + ", ".join(event["branches"]) + ")[/dim]"

        console.print(
            f"{line_prefix}  [#CCAA44]{short}[/#CCAA44]  {msg}"
            f"  [dim]{time_str}[/dim]{pm_str}{tag_str}{branch_labels}"
        )

        if event.get("is_merge"):
            console.print(
                f"  [{color}]  ╚═══╝[/{color}]"
            )

    # Footer connector
    last_event = events[-1] if events else None
    if last_event:
        primary = last_event["branches"][0] if last_event["branches"] else "?"
        color = branch_color_map.get(primary, "#CC3333")
        console.print(f"  [{color}]  │   │[/{color}]")
        console.print(f"  [{color}]  ╰───╯[/{color}]  [dim]({result['total_commits']} commits total)[/dim]")

    console.print()
    db.close()


# ---------------------------------------------------------------------------
# sync (push/pull context to remote repository)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("action", type=click.Choice(["push", "pull", "status", "remote"], case_sensitive=False))
@click.argument("remote_path", required=False, default=None)
@click.option("--name", "-n", default="origin", help="Remote name (default: origin).")
@click.option("--branch", "-b", default=None, help="Branch to sync (default: active branch).")
def sync(action: str, remote_path: str | None, name: str, branch: str | None) -> None:
    """Push/pull cognitive context to a remote repository.

    \b
    Share AI knowledge across teams. Like git push/pull but for
    AI conversation context, decisions, and reasoning.

    \b
    Actions:
      push     Push local commits to a remote CVC repository
      pull     Pull remote commits into local repository
      status   Show sync status with configured remotes
      remote   Add/show a named remote (requires path argument)

    \b
    Examples:
      cvc sync push /shared/team-cvc                  # Push to shared dir
      cvc sync pull /shared/team-cvc                  # Pull from shared dir
      cvc sync push //server/share/cvc --name team    # Named remote
      cvc sync pull //server/share/cvc --name team
      cvc sync remote /shared/team-cvc --name origin  # Register a remote
      cvc sync status                                 # Show sync status
    """
    engine, db = _get_engine()

    if action == "status":
        result = engine.sync_status(remote_name=name)
        console.print()

        if not result.get("configured"):
            _warn("No sync remotes configured.")
            _hint(
                "Set up a remote:\n"
                "  [bold]cvc sync push /path/to/shared/repo[/bold]\n"
                "  [bold]cvc sync remote /path/to/shared/repo --name origin[/bold]"
            )
        else:
            remotes = result.get("remotes", [])
            remote_table = Table(
                box=box.ROUNDED,
                border_style="dim",
                show_header=True,
                header_style="bold #CC3333",
                title="[bold]Sync Remotes[/bold]",
            )
            remote_table.add_column("Name", style="bold")
            remote_table.add_column("Path")
            remote_table.add_column("Last Push", style="#55AA55")
            remote_table.add_column("Last Pull", style="#CCAA44")
            remote_table.add_column("Last Sync")

            from datetime import datetime
            for r in remotes:
                last_sync = ""
                if r.get("last_sync_at"):
                    try:
                        last_sync = datetime.fromtimestamp(r["last_sync_at"]).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        last_sync = "?"
                remote_table.add_row(
                    r["name"],
                    r["remote_path"],
                    (r.get("last_push_hash") or "—")[:12],
                    (r.get("last_pull_hash") or "—")[:12],
                    last_sync or "—",
                )
            console.print(remote_table)
        console.print()
        db.close()
        return

    if action == "remote":
        if not remote_path:
            _error("Remote path is required.")
            _hint("Usage: [bold]cvc sync remote /path/to/repo --name origin[/bold]")
            db.close()
            return

        resolved = Path(remote_path).resolve()
        db.index.upsert_remote(name, str(resolved))
        _success(f"Registered remote '[bold]{name}[/bold]' → {resolved}")
        console.print()
        db.close()
        return

    # push or pull
    if not remote_path:
        # Try to use the named remote
        remote_info = db.index.get_remote(name)
        if remote_info:
            remote_path = remote_info["remote_path"]
        else:
            _error("Remote path is required (or configure a named remote first).")
            _hint(
                "Usage: [bold]cvc sync push /path/to/shared/repo[/bold]\n"
                "   or: [bold]cvc sync remote /path --name origin[/bold] first"
            )
            db.close()
            return

    console.print()
    console.print(
        f"  [bold #CC3333]Syncing ({action})[/bold #CC3333]\n"
        f"  [dim]Remote[/dim]    [bold]{name}[/bold] ({remote_path})\n"
        f"  [dim]Branch[/dim]    {branch or engine.active_branch}"
    )
    console.print()

    if action == "push":
        result = engine.sync_push(remote_path, remote_name=name, branch=branch)
    else:
        result = engine.sync_pull(remote_path, remote_name=name, branch=branch)

    if result.success:
        detail = result.detail
        console.print(
            Panel(
                f"  [dim]Remote[/dim]     [bold]{detail.get('remote_name', name)}[/bold]\n"
                f"  [dim]Path[/dim]       {detail.get('remote_path', remote_path)}\n"
                f"  [dim]Commits[/dim]    [bold #55AA55]{detail.get('pushed_commits', detail.get('pulled_commits', 0))}[/bold #55AA55]\n"
                f"  [dim]Blobs[/dim]      {detail.get('pushed_blobs', detail.get('pulled_blobs', 0))}\n"
                f"  [dim]HEAD[/dim]       [#CCAA44]{(detail.get('head_hash', detail.get('remote_head', ''))[:12])}[/#CCAA44]",
                border_style="#5C1010",
                title=f"[bold #55AA55]✓ Sync {action.title()} Complete[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        _hint(f"Your team can now {'pull' if action == 'push' else 'use'} this context.")
    else:
        _error(result.message)

    console.print()
    db.close()


# ---------------------------------------------------------------------------
# audit (security audit trail)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--type", "-t", "event_type", default=None,
              type=click.Choice(["commit", "merge", "restore", "compact", "inject", "sync_push", "sync_pull"], case_sensitive=False),
              help="Filter by event type.")
@click.option("--risk", "-r", default=None,
              type=click.Choice(["low", "medium", "high", "critical"], case_sensitive=False),
              help="Filter by risk level.")
@click.option("--since", "-s", "since_days", default=None, type=int, help="Show events from last N days.")
@click.option("-n", "--limit", default=30, type=int, help="Max events to show.")
@click.option("--export-json", is_flag=True, help="Export audit log as JSON file.")
@click.option("--export-csv", is_flag=True, help="Export audit log as CSV file.")
@click.option("--summary", is_flag=True, help="Show summary dashboard only.")
def audit(event_type: str | None, risk: str | None, since_days: int | None,
          limit: int, export_json: bool, export_csv: bool, summary: bool) -> None:
    """Security audit trail of every AI-generated code decision.

    \b
    Enterprise-grade compliance: every AI interaction is logged with
    who, what, when, which model, risk level, and affected files.

    \b
    Features:
      • Complete audit trail of all AI decisions
      • Risk-level classification (low/medium/high/critical)
      • Code generation tracking
      • Compliance scoring
      • Export to JSON/CSV for compliance reporting

    \b
    Examples:
      cvc audit                           # View recent audit events
      cvc audit --summary                 # Compliance dashboard
      cvc audit --risk high               # Filter high-risk events
      cvc audit --type commit --since 7   # Commits from last 7 days
      cvc audit --export-json             # Export for compliance review
      cvc audit --export-csv              # Export as spreadsheet
    """
    engine, db = _get_engine()

    export_format = None
    if export_json:
        export_format = "json"
    elif export_csv:
        export_format = "csv"

    result = engine.audit(
        event_type=event_type,
        risk_level=risk,
        since_days=since_days,
        limit=limit,
        export_format=export_format,
    )

    console.print()

    # Summary dashboard
    audit_summary = result.get("summary", {})
    score = result.get("compliance_score", 100)
    assessment = result.get("risk_assessment", "")

    # Compliance score color
    if score >= 90:
        score_color = "#55AA55"
        score_icon = "✓"
    elif score >= 70:
        score_color = "#CCAA44"
        score_icon = "⚠"
    else:
        score_color = "red"
        score_icon = "✗"

    console.print(
        Panel(
            f"  [dim]Total Events[/dim]       [bold]{audit_summary.get('total_events', 0)}[/bold]\n"
            f"  [dim]Compliance Score[/dim]   [{score_color}][bold]{score_icon} {score}%[/bold][/{score_color}]\n"
            f"  [dim]Assessment[/dim]         {assessment}\n"
            f"  [dim]Code Gen Events[/dim]    {audit_summary.get('code_generation_events', 0)}\n"
            f"  [dim]Total Tokens[/dim]       {audit_summary.get('total_tokens_audited', 0):,}",
            border_style="#5C1010",
            title="[bold #CC3333]🛡️ Security Audit Dashboard[/bold #CC3333]",
            padding=(1, 2),
        )
    )

    if summary:
        # Show breakdowns
        by_type = audit_summary.get("events_by_type", {})
        if by_type:
            type_table = Table(
                box=box.SIMPLE, border_style="dim",
                title="[bold]Events by Type[/bold]", show_header=True, header_style="dim",
            )
            type_table.add_column("Type", style="bold")
            type_table.add_column("Count", justify="right")
            for t, c in by_type.items():
                type_table.add_row(t, str(c))
            console.print(type_table)

        by_risk = audit_summary.get("events_by_risk", {})
        if by_risk:
            risk_colors = {"low": "#55AA55", "medium": "#CCAA44", "high": "red", "critical": "bold red"}
            risk_table = Table(
                box=box.SIMPLE, border_style="dim",
                title="[bold]Events by Risk Level[/bold]", show_header=True, header_style="dim",
            )
            risk_table.add_column("Risk", style="bold")
            risk_table.add_column("Count", justify="right")
            for r, c in by_risk.items():
                color = risk_colors.get(r, "white")
                risk_table.add_row(f"[{color}]{r}[/{color}]", str(c))
            console.print(risk_table)

        by_provider = audit_summary.get("events_by_provider", {})
        if by_provider:
            console.print("  [bold]By Provider:[/bold]")
            for p, c in by_provider.items():
                console.print(f"    [dim]→[/dim] {p}: {c}")
            console.print()

        console.print()
        db.close()
        return

    # Event list
    events = result.get("events", [])
    if not events:
        _warn("No audit events found matching your filters.")
        _hint("Events are recorded automatically. Try: [bold]cvc commit -m 'test'[/bold] first.")
        console.print()
        db.close()
        return

    RISK_ICONS = {"low": "[#55AA55]○[/#55AA55]", "medium": "[#CCAA44]◐[/#CCAA44]", "high": "[red]●[/red]", "critical": "[bold red]◉[/bold red]"}
    EVENT_ICONS = {
        "commit": "💾", "merge": "🔀", "restore": "⏪",
        "compact": "📦", "inject": "💉", "sync_push": "⬆️", "sync_pull": "⬇️",
    }

    event_table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold #CC3333",
        title="[bold]Audit Trail[/bold]",
    )
    event_table.add_column("", width=3)
    event_table.add_column("Time", style="dim", width=16)
    event_table.add_column("Event", style="bold", width=10)
    event_table.add_column("Commit", style="#CCAA44", width=12)
    event_table.add_column("Agent", width=8)
    event_table.add_column("Provider", width=12)
    event_table.add_column("Risk", width=8)
    event_table.add_column("Code", width=4)

    for e in events:
        risk_icon = RISK_ICONS.get(e.get("risk_level", "low"), "?")
        evt_icon = EVENT_ICONS.get(e.get("event_type", ""), "📋")
        code_flag = "[#55AA55]✓[/#55AA55]" if e.get("code_generated") else "[dim]—[/dim]"
        event_table.add_row(
            risk_icon,
            e.get("time_str", "?"),
            f"{evt_icon} {e.get('event_type', '?')}",
            (e.get("commit_hash") or "—")[:12],
            e.get("agent_id", "?"),
            e.get("provider", "—") or "—",
            e.get("risk_level", "?"),
            code_flag,
        )

    console.print(event_table)

    # Export notification
    export_path = result.get("export_path")
    if export_path:
        console.print()
        _success(f"Exported audit log to [bold]{export_path}[/bold]")
        _hint("Share this file with your compliance team for review.")

    console.print()
    db.close()


# ---------------------------------------------------------------------------
# mcp (MCP server mode for auth-based IDEs)
# ---------------------------------------------------------------------------

@main.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"], case_sensitive=False),
    default="stdio",
    help="MCP transport: stdio (default) or sse.",
)
@click.option("--host", default="127.0.0.1", help="SSE transport bind host.")
@click.option("--port", default=8001, type=int, help="SSE transport bind port.")
def mcp(transport: str, host: str, port: int) -> None:
    """Start CVC as an MCP server for AI agent IDEs.

    MCP (Model Context Protocol) lets authentication-based IDEs like
    Antigravity, Windsurf, GitHub Copilot (native), and Cursor use
    CVC's cognitive versioning without API endpoint redirection.

    The IDE's built-in agent calls CVC tools (commit, branch, merge,
    restore, status, log) through the MCP protocol.

    \b
    Transports:
      stdio  — IDE launches 'cvc mcp' as a subprocess (default)
      sse    — HTTP Server-Sent Events on localhost:8001

    \b
    IDE configuration examples:

      VS Code (settings.json):
        "mcp": {"servers": {"cvc": {"command": "cvc", "args": ["mcp"]}}}

      Antigravity / Windsurf / Cursor (MCP config):
        {"mcpServers": {"cvc": {"command": "cvc", "args": ["mcp"]}}}
    """
    from cvc.mcp_server import run_mcp_stdio, run_mcp_sse

    if transport == "sse":
        _banner("MCP Server (SSE)")
        console.print(
            Panel(
                f"  Transport  [bold #CC3333]SSE[/bold #CC3333]\n"
                f"  Endpoint   [bold #CC3333]http://{host}:{port}/sse[/bold #CC3333]\n"
                f"  Messages   [bold #CC3333]http://{host}:{port}/messages[/bold #CC3333]",
                border_style="#5C1010",
                title="[bold #55AA55]MCP Server[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        console.print()
        run_mcp_sse(host=host, port=port)
    else:
        # stdio transport — no banner (stdout is the protocol channel)
        run_mcp_stdio()


# ---------------------------------------------------------------------------
# doctor (system health check)
# ---------------------------------------------------------------------------

@main.command()
def doctor() -> None:
    """Check your CVC installation and environment."""
    from cvc.adapters import PROVIDER_DEFAULTS
    from cvc.core.models import get_global_config_dir, GlobalConfig, discover_cvc_root

    _banner("System Check")

    checks: list[tuple[str, bool, str]] = []

    # Python version
    py = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python", py_ok, f"{py}  {'✓ 3.11+' if py_ok else '✗ Need 3.11+'}"))

    # Global config
    gc_dir = get_global_config_dir()
    gc_exists = (gc_dir / "config.json").exists()
    gc = GlobalConfig.load()  # Returns defaults if file missing
    if gc_exists:
        checks.append(("Global config", True, f"{gc_dir}  (provider={gc.provider})"))
    else:
        checks.append(("Global config", False, f"Not found — run: cvc setup"))

    # .cvc directory (project-level)
    project_root = discover_cvc_root()
    if project_root:
        checks.append(("Project .cvc/", True, f"Found at {project_root / '.cvc'}"))
    else:
        checks.append(("Project .cvc/", False, "Not found — run: cvc init"))

    # Git
    try:
        import subprocess
        subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, check=True)
        checks.append(("Git repository", True, "Found"))
    except Exception:
        checks.append(("Git repository", False, "Not a Git repo (VCS bridge won't work)"))

    # Provider API keys (check env + stored)
    for prov, defaults in PROVIDER_DEFAULTS.items():
        env_key_name = defaults["env_key"]
        if env_key_name:
            has_env = bool(os.environ.get(env_key_name))
            has_stored = bool(gc.api_keys.get(prov)) if gc_exists else False
            if has_env:
                checks.append((f"{prov.title()} key", True, f"{env_key_name} ● env var set"))
            elif has_stored:
                checks.append((f"{prov.title()} key", True, f"● saved in global config"))
            else:
                checks.append((f"{prov.title()} key", False, f"{env_key_name} ○ not set"))

    # Ollama
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        models = [m["name"] for m in r.json().get("models", [])]
        checks.append(("Ollama", True, f"Running — {len(models)} model(s) loaded"))
    except Exception:
        checks.append(("Ollama", False, "Not running (optional)"))

    # Display results
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold #CC3333",
    )
    table.add_column("", width=3)
    table.add_column("Check", style="bold")
    table.add_column("Status")

    for name, ok, detail in checks:
        icon = "[#55AA55]✓[/#55AA55]" if ok else "[red]✗[/red]"
        table.add_row(icon, name, detail)

    console.print(table)
    console.print()

    all_ok = all(ok for _, ok, _ in checks[:3])  # Python + global config + .cvc/
    if all_ok:
        _success("CVC is ready to go!")
    else:
        _warn("Some checks failed. See details above.")

    console.print()


# ---------------------------------------------------------------------------
# launch (zero-config auto-launch for any AI tool)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("tool", required=False, default=None)
@click.option("--host", default="127.0.0.1", help="Proxy bind host.")
@click.option("--port", default=8000, type=int, help="Proxy bind port.")
@click.option("--no-time-machine", is_flag=True, help="Disable aggressive auto-commit.")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def launch(tool: str | None, host: str, port: int, no_time_machine: bool, extra_args: tuple[str, ...]) -> None:
    """Zero-config auto-launch: start any AI tool through CVC.

    \b
    Examples:
      cvc launch claude       # Launch Claude Code CLI with CVC
      cvc launch aider        # Launch Aider through CVC proxy
      cvc launch codex        # Launch OpenAI Codex CLI through CVC
      cvc launch cursor       # Open Cursor with CVC auto-configured
      cvc launch code         # Open VS Code with Copilot BYOK configured

    CVC automatically:
      1. Sets up configuration (if first run)
      2. Initialises .cvc/ in the current project (if needed)
      3. Starts the proxy server in the background
      4. Configures the tool's environment variables / config files
      5. Launches the tool — every conversation is time-machined
    """
    from cvc.launcher import launch_tool, exec_tool, list_launchable_tools, resolve_tool

    _banner("Time Machine Launcher")

    # If no tool specified, show interactive picker
    if tool is None:
        tools = list_launchable_tools()

        console.print("  [bold white]Pick an AI tool to launch through CVC:[/bold white]\n")

        # Group by kind
        cli_tools = [t for t in tools if t["kind"] == "cli"]
        ide_tools = [t for t in tools if t["kind"] == "ide"]

        idx = 1
        index_map: dict[int, str] = {}

        if cli_tools:
            console.print("  [bold #CC3333]CLI Tools[/bold #CC3333]")
            for t in cli_tools:
                status = "[#55AA55]●[/#55AA55]" if t["installed"] else "[red]○[/red]"
                console.print(
                    f"    [#CC3333]{idx}[/#CC3333]  {status}  [bold]{t['name']}[/bold]  "
                    f"[dim]({t['binary']})[/dim]"
                )
                index_map[idx] = t["key"]
                idx += 1
            console.print()

        if ide_tools:
            console.print("  [bold #CCAA44]IDEs[/bold #CCAA44]")
            for t in ide_tools:
                status = "[#55AA55]●[/#55AA55]" if t["installed"] else "[red]○[/red]"
                console.print(
                    f"    [#CCAA44]{idx}[/#CCAA44]  {status}  [bold]{t['name']}[/bold]  "
                    f"[dim]({t['binary']})[/dim]"
                )
                index_map[idx] = t["key"]
                idx += 1
            console.print()

        console.print("  [dim]● = installed   ○ = not found on PATH[/dim]")
        console.print()

        choice = click.prompt("  Pick a tool", type=click.IntRange(1, len(index_map)), default=1)
        tool = index_map[choice]
        console.print()

    # Resolve alias
    resolved = resolve_tool(tool)
    if resolved is None:
        _error(f"Unknown tool: [bold]{tool}[/bold]")
        _info("Run [bold]cvc launch[/bold] (no arguments) to see available tools.")
        return

    console.print(f"  [bold]Launching[/bold] [#CC3333]{resolved}[/#CC3333] through CVC…")
    console.print()

    time_machine = not no_time_machine

    result = launch_tool(
        resolved,
        host=host,
        port=port,
        extra_args=list(extra_args) if extra_args else None,
        time_machine=time_machine,
    )

    # Handle tuple return (CLI tools return (report, cmd, env))
    cmd = None
    child_env = None
    if isinstance(result, tuple):
        result, cmd, child_env = result

    if not result["success"]:
        _error(result.get("error", "Launch failed"))
        if "need_setup" in result.get("steps", []):
            _hint("Run [bold]cvc setup[/bold] to configure your provider and API key.")
        return

    # Show what happened
    steps = result.get("steps", [])
    if "auto_init" in steps:
        _success("Auto-initialised .cvc/ in current directory")
    if "proxy_running" in steps:
        _success(f"CVC proxy running at [bold #CC3333]{result['endpoint']}[/bold #CC3333]")

    if time_machine:
        _success("Time Machine mode: [bold]ON[/bold] (auto-commit every 3 turns)")

    # Show env overrides
    env_overrides = result.get("env_overrides", {})
    if env_overrides:
        for k, v in env_overrides.items():
            _info(f"[dim]{k}[/dim] = [#CC3333]{v}[/#CC3333]")

    # Show auto-config results
    auto_config = result.get("auto_config", {})
    for action in auto_config.get("actions", []):
        _success(action)
    if "manual_step" in auto_config:
        _warn(auto_config["manual_step"])

    console.print()

    # For CLI tools, exec into the tool
    if cmd and child_env:
        console.print(
            Panel(
                f"  [bold white]{result['tool']}[/bold white] is launching…\n"
                f"  [dim]All conversations flow through CVC automatically.[/dim]\n"
                f"  [dim]Use /cvc commands or CVC tools for version control.[/dim]",
                border_style="#5C1010",
                title="[bold #55AA55]Time Machine Active[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        console.print()
        exit_code = exec_tool(cmd, child_env)
        raise SystemExit(exit_code)
    else:
        # IDE was launched
        console.print(
            Panel(
                f"  [bold white]{result['tool']}[/bold white] has been opened.\n"
                f"  [dim]CVC proxy is running in the background.[/dim]\n"
                f"  [dim]Conversations will be auto-saved by the Time Machine.[/dim]",
                border_style="#5C1010",
                title="[bold #55AA55]Time Machine Active[/bold #55AA55]",
                padding=(1, 2),
            )
        )
        console.print()


# ---------------------------------------------------------------------------
# up (one-command start: setup + init + serve)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--host", default="127.0.0.1", help="Proxy bind host.")
@click.option("--port", default=8000, type=int, help="Proxy bind port.")
@click.option("--time-machine/--no-time-machine", default=True, help="Enable Time Machine auto-commit.")
def up(host: str, port: int, time_machine: bool) -> None:
    """One-command start: setup (if needed) + init (if needed) + serve.

    \b
    This is the fastest way to get CVC running:
      $ cvc up

    If CVC hasn't been set up yet, it runs the setup wizard first.
    If the current project has no .cvc/, it initialises one.
    Then it starts the proxy server with Time Machine enabled.
    """
    from cvc.core.models import get_global_config_dir, GlobalConfig, CVCConfig, discover_cvc_root

    _banner("One-Command Start")

    # Step 1: Check setup
    gc_path = get_global_config_dir() / "config.json"
    if not gc_path.exists():
        console.print("  [#CCAA44]First-time setup required.[/#CCAA44]")
        console.print()
        click.get_current_context().invoke(setup)
        console.print()
        # Re-check after setup
        if not gc_path.exists():
            _error("Setup was not completed. Run [bold]cvc setup[/bold] manually.")
            return

    gc = GlobalConfig.load()
    _success(f"Config: [bold]{gc.provider}[/bold] / [bold]{gc.model}[/bold]")

    # Step 2: Check init
    project_root = discover_cvc_root()
    if project_root is None:
        config = CVCConfig.for_project(project_root=Path.cwd())
        config.ensure_dirs()
        from cvc.core.database import ContextDatabase
        ContextDatabase(config).close()
        _success(f"Initialised .cvc/ at [dim]{Path.cwd()}[/dim]")
    else:
        _success(f"Project CVC found at [dim]{project_root}[/dim]")

    # Step 3: Set Time Machine env
    if time_machine:
        os.environ["CVC_TIME_MACHINE"] = "1"
        _success("Time Machine mode: [bold]ON[/bold]")

    console.print()

    # Step 4: Start the proxy
    click.get_current_context().invoke(serve, host=host, port=port, do_reload=False)


# ---------------------------------------------------------------------------
# sessions (view Time Machine session history)
# ---------------------------------------------------------------------------

@main.command()
@click.option("--host", default="127.0.0.1", help="Proxy host.")
@click.option("--port", default=8000, type=int, help="Proxy port.")
def sessions(host: str, port: int) -> None:
    """View Time Machine session history.

    Shows all agent sessions tracked by the CVC proxy, including
    which tool was used, message counts, and auto-commit stats.

    The proxy must be running for this command to work.
    """
    import httpx
    from datetime import datetime

    _banner("Session History")

    endpoint = f"http://{host}:{port}"

    try:
        r = httpx.get(f"{endpoint}/cvc/sessions", timeout=5.0)
        r.raise_for_status()
        data = r.json()
    except httpx.ConnectError:
        _error(f"CVC proxy is not running on {endpoint}")
        _hint("Start the proxy: [bold]cvc serve[/bold] or [bold]cvc up[/bold]")
        return
    except Exception as exc:
        _error(f"Failed to fetch sessions: {exc}")
        return

    # Config info
    tm_status = "[bold #55AA55]ON[/bold #55AA55]" if data.get("time_machine") else "[dim]OFF[/dim]"
    interval = data.get("auto_commit_interval", "?")
    console.print(
        Panel(
            f"  Time Machine    {tm_status}\n"
            f"  Auto-commit     every [bold]{interval}[/bold] assistant turns\n"
            f"  Session timeout [dim]{data.get('session_timeout_seconds', '?')}s[/dim]",
            border_style="#8B0000",
            title="[bold white]Configuration[/bold white]",
            padding=(0, 2),
        )
    )
    console.print()

    session_list = data.get("sessions", [])
    if not session_list:
        _warn("No sessions recorded yet.")
        _info("Sessions are tracked when tools send requests through the proxy.")
        return

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold #CC3333",
    )
    table.add_column("#", width=4)
    table.add_column("Tool", style="#CC3333", width=12)
    table.add_column("Started", width=20)
    table.add_column("Messages", justify="right", width=10)
    table.add_column("Commits", justify="right", width=10)
    table.add_column("Status", width=10)

    for s in session_list:
        started = datetime.fromtimestamp(s["started_at"]).strftime("%Y-%m-%d %H:%M") if s.get("started_at") else "?"
        status_str = "[bold #55AA55]active[/bold #55AA55]" if s.get("active") else "[dim]ended[/dim]"
        table.add_row(
            str(s.get("id", "?")),
            s.get("tool", "?"),
            started,
            str(s.get("messages", 0)),
            str(s.get("commits", 0)),
            status_str,
        )

    console.print(table)
    console.print(f"\n  [dim]{len(session_list)} session(s) total[/dim]\n")


if __name__ == "__main__":
    main()
