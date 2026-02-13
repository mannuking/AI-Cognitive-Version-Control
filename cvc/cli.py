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

LOGO = """[bold cyan]
   ██████ ██    ██  ██████
  ██      ██    ██ ██
  ██      ██    ██ ██
  ██       ██  ██  ██
   ██████   ████    ██████[/bold cyan]"""

TAGLINE = "[dim]Cognitive Version Control — Git for the AI Mind[/dim]"

try:
    from cvc import __version__ as VERSION
except ImportError:
    VERSION = "0.4.0"


def _banner(subtitle: str = "") -> None:
    """Print the CVC banner."""
    content = f"{LOGO}\n\n{TAGLINE}"
    if subtitle:
        content += f"\n[bold white]{subtitle}[/bold white]"
    console.print(
        Panel(
            content,
            border_style="cyan",
            padding=(1, 4),
            title=f"[bold white]v{VERSION}[/bold white]",
            title_align="right",
            subtitle="[dim]Time Machine for AI Agents[/dim]",
            subtitle_align="center",
        )
    )
    console.print()


def _success(msg: str) -> None:
    console.print(f"  [bold green]✓[/bold green] {msg}")


def _error(msg: str) -> None:
    console.print(f"  [bold red]✗[/bold red] {msg}")


def _warn(msg: str) -> None:
    console.print(f"  [bold yellow]![/bold yellow] {msg}")


def _info(msg: str) -> None:
    console.print(f"  [dim]→[/dim] {msg}")


def _hint(msg: str) -> None:
    console.print()
    console.print(
        Panel(
            msg,
            border_style="blue",
            title="[bold blue]Hint[/bold blue]",
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
    console.print("[bold cyan]  Detecting installed IDEs…[/bold cyan]")
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
            _info(f"   → Override OpenAI Base URL → [bold cyan]{endpoint}/v1[/bold cyan]")
            _info("   → API Key → [cyan]cvc[/cyan]")
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
            header_style="bold cyan",
            padding=(0, 2),
        )
        table.add_column("Command", style="bold white", width=22)
        table.add_column("Description", style="dim white")

        cmds = [
            ("launch <tool>", "Auto-launch any AI tool through CVC"),
            ("up", "One-command start (setup + init + serve)"),
            ("setup", "Interactive first-time setup"),
            ("serve", "Start the Cognitive Proxy server"),
            ("connect", "Connect your AI tool to CVC"),
            ("mcp", "Start CVC as an MCP server"),
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
                border_style="cyan",
                title="[bold white]Commands[/bold white]",
                padding=(1, 1),
            )
        )

        # Quick start hint
        console.print()
        console.print(
            Panel(
                "[bold white]Get started in 10 seconds:[/bold white]\n\n"
                "  [cyan]$[/cyan] cvc launch claude      [dim]# Zero-config: launches Claude Code through CVC[/dim]\n"
                "  [cyan]$[/cyan] cvc launch aider       [dim]# Zero-config: launches Aider through CVC[/dim]\n"
                "  [cyan]$[/cyan] cvc up                 [dim]# One command: setup + init + serve[/dim]\n\n"
                "[bold white]Or step by step:[/bold white]\n\n"
                "  [cyan]$[/cyan] cvc setup              [dim]# Pick your provider & model[/dim]\n"
                "  [cyan]$[/cyan] cvc serve              [dim]# Start the proxy (API key tools)[/dim]\n"
                "  [cyan]$[/cyan] cvc mcp                [dim]# Start MCP server (auth-based IDEs)[/dim]\n"
                "  [cyan]$[/cyan] cvc connect            [dim]# Wire up Cursor, Cline, Claude Code…[/dim]",
                border_style="green",
                title="[bold green]Quick Start[/bold green]",
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
        # ─── First run — welcome + auto-launch setup ─────────────────────
        _banner()
        console.print(
            Panel(
                "[bold white]Welcome to CVC![/bold white]\n\n"
                "Looks like this is your [bold cyan]first time[/bold cyan] here.\n"
                "Let's get you set up — it takes about 30 seconds.",
                border_style="yellow",
                title="[bold yellow]First Run[/bold yellow]",
                padding=(1, 3),
            )
        )
        console.print()
        ctx.invoke(setup)
        return

    # ─── Returning user — interactive main menu ──────────────────────────
    gc = GlobalConfig.load()
    _banner()

    console.print(
        Panel(
            f"  Provider   [bold cyan]{gc.provider}[/bold cyan]\n"
            f"  Model      [bold cyan]{gc.model}[/bold cyan]",
            border_style="dim green",
            title="[bold white]Current Config[/bold white]",
            padding=(0, 2),
        )
    )
    console.print()
    console.print("  [bold white]What would you like to do?[/bold white]\n")

    menu = [
        ("1", "Launch", "Auto-launch an AI tool through CVC", "bold green"),
        ("2", "Up", "One-command start (setup + init + serve)", "green"),
        ("3", "Setup", "Configure provider, model & API key", "cyan"),
        ("4", "Serve", "Start the CVC proxy server", "yellow"),
        ("5", "Connect", "Wire up your AI tool to CVC", "yellow"),
        ("6", "MCP", "Start MCP server (auth-based IDEs)", "magenta"),
        ("7", "Sessions", "View Time Machine session history", "blue"),
        ("8", "Status", "View current project status", "blue"),
        ("9", "Doctor", "Health check your environment", "dim"),
        ("0", "Help", "Show all available commands", "dim"),
    ]
    for num, label, desc, color in menu:
        console.print(f"    [{color}]{num}[/{color}]  [bold]{label}[/bold]  [dim]— {desc}[/dim]")

    console.print()

    choice = click.prompt("  Pick an option", type=click.IntRange(0, 9), default=1)
    console.print()

    if choice == 1:
        ctx.invoke(launch)
    elif choice == 2:
        ctx.invoke(up)
    elif choice == 3:
        ctx.invoke(setup)
    elif choice == 4:
        ctx.invoke(serve)
    elif choice == 5:
        ctx.invoke(connect)
    elif choice == 6:
        ctx.invoke(mcp)
    elif choice == 7:
        ctx.invoke(sessions)
    elif choice == 8:
        ctx.invoke(status)
    elif choice == 9:
        ctx.invoke(doctor)
    elif choice == 0:
        ctx.command.format_help(ctx, click.HelpFormatter())


# ---------------------------------------------------------------------------
# setup (guided first-time configuration)
# ---------------------------------------------------------------------------

MODEL_CATALOG = {
    "anthropic": [
        ("claude-opus-4-6", "Most intelligent — agents & coding", "$5/$25 per MTok"),
        ("claude-opus-4-5", "Previous flagship — excellent reasoning", "$5/$25 per MTok"),
        ("claude-sonnet-4-5", "Best speed / intelligence balance", "$3/$15 per MTok"),
        ("claude-haiku-4-5", "Fastest & cheapest", "$1/$5 per MTok"),
    ],
    "openai": [
        ("gpt-5.2", "Best for coding & agentic tasks", "Frontier"),
        ("gpt-5.2-codex", "Optimized for agentic coding", "Frontier"),
        ("gpt-5-mini", "Fast & cost-efficient", "Mid-tier"),
        ("gpt-4.1", "Smartest non-reasoning model", "Mid-tier"),
    ],
    "google": [
        ("gemini-3-pro", "Most powerful multimodal & agentic", "Premium"),
        ("gemini-3-flash", "Balanced speed & intelligence", "Standard"),
        ("gemini-2.5-flash", "Best price-performance", "Economy"),
        ("gemini-2.5-pro", "Advanced thinking model", "Premium"),
    ],
    "ollama": [
        ("qwen2.5-coder:7b", "Best coding model — 11M+ pulls", "~4 GB"),
        ("qwen3-coder:30b", "Latest agentic coding model", "~18 GB"),
        ("devstral:24b", "Mistral's best open-source coding agent", "~14 GB"),
        ("deepseek-r1:8b", "Open reasoning model (chain-of-thought)", "~5 GB"),
    ],
}


@main.command()
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai", "google", "ollama"], case_sensitive=False),
    prompt=False,
    help="LLM provider (interactive prompt if omitted).",
)
@click.option("--model", default="", help="Model override (uses provider default if empty).")
@click.option("--api-key", default="", help="API key (prompted interactively if omitted).")
def setup(provider: str | None, model: str, api_key: str) -> None:
    """Interactive first-time setup — pick your provider, model, and go."""
    from cvc.adapters import PROVIDER_DEFAULTS
    from cvc.core.models import GlobalConfig as GC_Init, get_global_config_dir

    _banner("Setup Wizard")

    # ─── Detect existing configuration ───────────────────────────────────
    existing_gc = GC_Init.load()
    has_existing = bool(existing_gc.provider)

    if has_existing and not provider:
        # Show current config summary and let user choose
        masked_keys = {}
        for prov, key in existing_gc.api_keys.items():
            if key and len(key) > 12:
                masked_keys[prov] = key[:8] + "…" + key[-4:]
            elif key:
                masked_keys[prov] = "●●●●"

        current_info = (
            f"  Provider   [bold cyan]{existing_gc.provider}[/bold cyan]\n"
            f"  Model      [bold cyan]{existing_gc.model}[/bold cyan]"
        )
        if masked_keys:
            keys_str = ", ".join(f"{p}: {m}" for p, m in masked_keys.items())
            current_info += f"\n  API Keys   [dim]{keys_str}[/dim]"

        console.print(
            Panel(
                current_info,
                border_style="green",
                title="[bold green]Existing Configuration Found[/bold green]",
                padding=(1, 2),
            )
        )
        console.print()

        console.print("  [bold white]What would you like to do?[/bold white]")
        console.print()
        console.print("    [cyan]1[/cyan]  [bold]Start Fresh[/bold]          [dim]— Reconfigure everything from scratch[/dim]")
        console.print("    [green]2[/green]  [bold]Change Provider[/bold]     [dim]— Switch to a different LLM provider[/dim]")
        console.print("    [yellow]3[/yellow]  [bold]Change Model[/bold]        [dim]— Keep provider, pick a different model[/dim]")
        console.print("    [magenta]4[/magenta]  [bold]Update API Key[/bold]      [dim]— Replace or add an API key[/dim]")
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

            console.print("[bold cyan]  Pick a new model[/bold cyan]")
            console.print()

            models = MODEL_CATALOG.get(provider, [])
            table = Table(box=box.ROUNDED, border_style="dim", show_header=True, header_style="bold cyan")
            table.add_column("#", style="bold", width=3)
            table.add_column("Model ID", style="cyan")
            table.add_column("Description")
            table.add_column("Tier", style="dim", justify="right")
            table.add_column("", width=3)
            for i, (mid, desc, tier) in enumerate(models, 1):
                marker = "[bold green]●[/bold green]" if mid == chosen_model else " "
                table.add_row(str(i), mid, desc, tier, marker)
            console.print(Panel(table, border_style="cyan", title=f"[bold white]{provider.title()} Models[/bold white]", padding=(1, 1)))

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

            if provider == "ollama":
                _success("Ollama doesn't need an API key — it runs locally!")
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
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    # ─── Step 1: Provider Selection ──────────────────────────────────────
    console.print("[bold cyan]  STEP 1 of 4[/bold cyan]  [bold white]Choose your LLM provider[/bold white]")
    console.print()

    if not provider:
        providers = [
            ("anthropic", "Anthropic", "Claude Opus 4.6 / 4.5, Sonnet 4.5", "cyan"),
            ("openai", "OpenAI", "GPT-5.2, GPT-5.2-Codex", "green"),
            ("google", "Google", "Gemini 3 Pro, Gemini 3 Flash", "yellow"),
            ("ollama", "Ollama", "Local models — no API key needed!", "magenta"),
        ]
        for i, (key, name, desc, color) in enumerate(providers, 1):
            console.print(
                f"    [{color}]{i}[/{color}]  [bold]{name}[/bold]  [dim]— {desc}[/dim]"
            )
        console.print()

        choice = click.prompt(
            "  Enter number",
            type=click.IntRange(1, 4),
            default=1,
        )
        provider = providers[choice - 1][0]

    _success(f"Provider: [bold]{provider}[/bold]")
    console.print()

    defaults = PROVIDER_DEFAULTS[provider]
    chosen_model = model or defaults["model"]

    # ─── Step 2: Model Selection ─────────────────────────────────────────
    console.print("[bold cyan]  STEP 2 of 4[/bold cyan]  [bold white]Pick a model[/bold white]")
    console.print()

    models = MODEL_CATALOG.get(provider, [])
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="bold", width=3)
    table.add_column("Model ID", style="cyan")
    table.add_column("Description")
    table.add_column("Tier", style="dim", justify="right")
    table.add_column("", width=3)

    for i, (mid, desc, tier) in enumerate(models, 1):
        marker = "[bold green]●[/bold green]" if mid == chosen_model else " "
        table.add_row(str(i), mid, desc, tier, marker)

    console.print(
        Panel(table, border_style="cyan", title=f"[bold white]{provider.title()} Models[/bold white]", padding=(1, 1))
    )

    if not model and models:
        console.print(f"  [dim]Default:[/dim] [bold cyan]{chosen_model}[/bold cyan]  [dim](press Enter to keep)[/dim]")
        model_choice = click.prompt(
            "  Enter number or model ID",
            default="",
            show_default=False,
        ).strip()
        if model_choice:
            # If it's a number, pick from the list
            if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                chosen_model = models[int(model_choice) - 1][0]
            else:
                chosen_model = model_choice

    _success(f"Model: [bold]{chosen_model}[/bold]")
    console.print()

    # ─── Step 3: API Key ─────────────────────────────────────────────────
    console.print("[bold cyan]  STEP 3 of 4[/bold cyan]  [bold white]API Key[/bold white]")
    console.print()

    env_key = defaults["env_key"]

    if provider == "ollama":
        _success("No API key needed for Ollama — it runs locally!")
        console.print()
        console.print(
            Panel(
                f"Make sure Ollama is running:\n\n"
                f"  [cyan]$[/cyan] ollama serve\n"
                f"  [cyan]$[/cyan] ollama pull {chosen_model}",
                border_style="magenta",
                title="[bold magenta]Local Setup[/bold magenta]",
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
    console.print("[bold cyan]  STEP 4 of 4[/bold cyan]  [bold white]Saving configuration[/bold white]")
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
    key_display = "[green]● saved[/green]"
    if provider == "ollama":
        key_display = "[dim]not needed[/dim]"
    elif not api_key and os.environ.get(env_key, ""):
        key_display = "[green]● from env[/green]"
    elif not api_key:
        key_display = "[red]● missing[/red]"

    console.print(
        Panel(
            f"  Provider   [bold cyan]{provider}[/bold cyan]\n"
            f"  Model      [bold cyan]{chosen_model}[/bold cyan]\n"
            f"  API Key    {key_display}\n"
            f"  Config     [dim]{gc_path}[/dim]\n"
            f"  Database   [dim]{config.db_path}[/dim]\n"
            f"  Objects    [dim]{config.objects_dir}[/dim]",
            border_style="green",
            title="[bold green]✓ CVC is Ready[/bold green]",
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
                "  [cyan]$[/cyan] cvc serve              [dim]# Start the proxy whenever you're ready[/dim]\n"
                "  [cyan]$[/cyan] cvc connect             [dim]# Tool-specific setup guides[/dim]\n"
                "  [cyan]$[/cyan] [dim]Point your agent → http://127.0.0.1:8000/v1/chat/completions[/dim]",
                border_style="blue",
                title="[bold blue]When You're Ready[/bold blue]",
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
            "[bold cyan]Option 1: Copilot BYOK (Bring Your Own Key)[/bold cyan]",
            "  Available on Copilot Individual plans (Free, Pro, Pro+):",
            "  1. [bold]Ctrl+Shift+P[/bold] → [bold]Chat: Manage Language Models[/bold]",
            "  2. Select [bold]OpenAI Compatible[/bold] as provider",
            "  3. Base URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "  4. API Key → [cyan]cvc[/cyan]  [dim](any non-empty string)[/dim]",
            "  5. Select model → [cyan]{model}[/cyan]",
            "",
            "[bold cyan]Option 2: MCP Server (Works with native Copilot)[/bold cyan]",
            "  Add to VS Code settings.json or .vscode/mcp.json:",
            '     [cyan]{{"mcp": {{"servers": {{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}}}}}[/cyan]',
            "  CVC tools will be available as MCP tools in Copilot agent mode.",
            "",
            "[bold cyan]Option 3: Extensions (Continue.dev / Cline)[/bold cyan]",
            "  Install from VS Code Marketplace and configure with:",
            "  Base URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "  API Key → [cyan]cvc[/cyan]",
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
            "[bold cyan]Option 1: MCP Server (Recommended)[/bold cyan]",
            "  1. Click [bold]⋯[/bold] in Antigravity's agent panel → [bold]Manage MCP Servers[/bold]",
            "  2. Click [bold]View raw config[/bold]",
            "  3. Add the CVC MCP server:",
            "",
            '     [cyan]{{"mcpServers": {{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}}}[/cyan]',
            "",
            "  4. The CVC tools (commit, branch, merge, restore, status, log)",
            "     will appear as available tools in Antigravity's agent.",
            "",
            "[bold cyan]Option 2: Continue.dev Extension[/bold cyan]",
            "  Antigravity is Code OSS-based and supports Open VSX extensions.",
            "  Install [bold]Continue.dev[/bold] from Open VSX and configure:",
            "     Base URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "     API Key  → [cyan]cvc[/cyan]",
            "     Model    → [cyan]{model}[/cyan]",
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
            "  2. Click [bold]Add OpenAI API Key[/bold] → paste [cyan]cvc[/cyan]",
            "  3. Enable [bold]Override OpenAI Base URL[/bold] → set to:",
            "     [bold cyan]{endpoint}/v1[/bold cyan]",
            "  4. Select your model and start coding!",
            "",
            "[bold cyan]Alternative: MCP Server[/bold cyan]",
            "  You can also add CVC as an MCP server in Cursor:",
            "  Settings → MCP Servers → Add:",
            '     [cyan]{{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}[/cyan]',
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
            "[bold cyan]MCP Server (Recommended)[/bold cyan]",
            "  1. Open Windsurf → click [bold]⋯[/bold] in Cascade panel",
            "  2. Go to [bold]MCP Settings[/bold] → [bold]Configure[/bold]",
            "  3. Add the CVC MCP server:",
            "",
            '     [cyan]{{"mcpServers": {{"cvc": {{"command": "cvc", "args": ["mcp"]}}}}}}[/cyan]',
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
            "  [cyan]models:[/cyan]",
            "    [cyan]- name: CVC Proxy[/cyan]",
            "      [cyan]provider: openai[/cyan]",
            "      [cyan]model: {model}[/cyan]",
            "      [cyan]apiBase: {endpoint}/v1[/cyan]",
            "      [cyan]apiKey: cvc[/cyan]",
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
            "Set Base URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "Set API Key → [cyan]cvc[/cyan]  [dim](any non-empty string)[/dim]",
            "Set Model ID → [cyan]{model}[/cyan]",
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
            "Set Base URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "Set API Key → [cyan]cvc[/cyan]  [dim](any non-empty string)[/dim]",
            "Select model → [cyan]{model}[/cyan]",
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
            "[bold cyan]Quick start:[/bold cyan]",
            "",
            "  [cyan]export ANTHROPIC_BASE_URL=\"{endpoint}\"[/cyan]",
            "  [cyan]claude[/cyan]",
            "",
            "Your existing ANTHROPIC_API_KEY is passed through to the",
            "upstream Anthropic API. CVC intercepts the conversation for",
            "cognitive versioning and forwards everything else.",
            "",
            "[bold cyan]Or add to ~/.claude/settings.json:[/bold cyan]",
            "",
            "  [cyan]{{[/cyan]",
            "    [cyan]\"env\": {{[/cyan]",
            "      [cyan]\"ANTHROPIC_BASE_URL\": \"{endpoint}\"[/cyan]",
            "    [cyan]}}[/cyan]",
            "  [cyan]}}[/cyan]",
            "",
            "[dim]Auth pass-through: CVC forwards your API key to Anthropic.[/dim]",
            "[dim]No need to store your key in CVC — just set ANTHROPIC_API_KEY.[/dim]",
        ],
        "steps_win": [
            "[bold]Claude Code now works natively with CVC![/bold]",
            "CVC serves the Anthropic Messages API at [bold]/v1/messages[/bold].",
            "",
            "[bold cyan]Quick start:[/bold cyan]",
            "",
            "  [cyan]$env:ANTHROPIC_BASE_URL = \"{endpoint}\"[/cyan]",
            "  [cyan]claude[/cyan]",
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
            "  [cyan]{{[/cyan]",
            "    [cyan]\"model\": {{[/cyan]",
            "      [cyan]\"name\": \"{model}\"[/cyan]",
            "    [cyan]}}[/cyan]",
            "  [cyan]}}[/cyan]",
            "",
            "Then set the API endpoint via environment variable:",
            "",
            "  [cyan]export GEMINI_API_BASE_URL=\"{endpoint}/v1\"[/cyan]",
            "  [cyan]export GEMINI_API_KEY=\"your-key\"[/cyan]",
            "  [cyan]gemini[/cyan]",
            "",
            "[dim]Custom base URL support may require Gemini CLI v2+.[/dim]",
            "[dim]Check: https://github.com/google-gemini/gemini-cli[/dim]",
        ],
        "steps_win": [
            "Gemini CLI uses settings files for configuration.",
            "Edit [bold]%USERPROFILE%\\.gemini\\settings.json[/bold] and add:",
            "",
            "  [cyan]{{[/cyan]",
            "    [cyan]\"model\": {{[/cyan]",
            "      [cyan]\"name\": \"{model}\"[/cyan]",
            "    [cyan]}}[/cyan]",
            "  [cyan]}}[/cyan]",
            "",
            "Then set the API endpoint via environment variable:",
            "",
            "  [cyan]$env:GEMINI_API_BASE_URL = \"{endpoint}/v1\"[/cyan]",
            "  [cyan]$env:GEMINI_API_KEY = \"your-key\"[/cyan]",
            "  [cyan]gemini[/cyan]",
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
            "  [cyan]{{[/cyan]",
            "    [cyan]\"model_provider\": \"openai\",[/cyan]",
            "    [cyan]\"model\": \"{model}\",[/cyan]",
            "    [cyan]\"base_url\": \"{endpoint}/v1\",[/cyan]",
            "    [cyan]\"api_key\": \"cvc\"[/cyan]",
            "  [cyan]}}[/cyan]",
            "",
            "Or use the Kiro Gateway for OpenAI-compatible routing:",
            "",
            "  [cyan]export OPENAI_API_BASE=\"{endpoint}/v1\"[/cyan]",
            "  [cyan]export OPENAI_API_KEY=\"cvc\"[/cyan]",
            "  [cyan]kiro[/cyan]",
            "",
            "[dim]See: https://kiro.dev/docs/cli/[/dim]",
        ],
        "steps_win": [
            "Kiro CLI from Amazon uses custom agents + MCP servers.",
            "Create a custom agent config to route through CVC:",
            "",
            "  Edit [bold]%USERPROFILE%\\.kiro\\settings.json[/bold]:",
            "",
            "  [cyan]{{[/cyan]",
            "    [cyan]\"model_provider\": \"openai\",[/cyan]",
            "    [cyan]\"model\": \"{model}\",[/cyan]",
            "    [cyan]\"base_url\": \"{endpoint}/v1\",[/cyan]",
            "    [cyan]\"api_key\": \"cvc\"[/cyan]",
            "  [cyan]}}[/cyan]",
            "",
            "Or use environment variables:",
            "",
            "  [cyan]$env:OPENAI_API_BASE = \"{endpoint}/v1\"[/cyan]",
            "  [cyan]$env:OPENAI_API_KEY = \"cvc\"[/cyan]",
            "  [cyan]kiro[/cyan]",
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
            "  [cyan]export OPENAI_API_BASE={endpoint}/v1[/cyan]",
            "  [cyan]export OPENAI_API_KEY=cvc[/cyan]",
            "",
            "Then start Aider:",
            "",
            "  [cyan]aider --model openai/{model}[/cyan]",
        ],
        "steps_win": [
            "Set the environment variables:",
            "",
            "  [cyan]$env:OPENAI_API_BASE = \"{endpoint}/v1\"[/cyan]",
            "  [cyan]$env:OPENAI_API_KEY = \"cvc\"[/cyan]",
            "",
            "Then start Aider:",
            "",
            "  [cyan]aider --model openai/{model}[/cyan]",
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
            "URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "API Key → [cyan]cvc[/cyan]  [dim](any non-empty string)[/dim]",
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
            "     Base URL → [bold cyan]{endpoint}/v1[/bold cyan]",
            "     API Key  → [cyan]cvc[/cyan]",
            "     Model    → [cyan]{model}[/cyan]",
            "",
            "[bold cyan]Alternative: MCP Server[/bold cyan]",
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
            "[bold cyan]Option 1: Environment variables[/bold cyan]",
            "",
            "  [cyan]export OPENAI_API_BASE={endpoint}/v1[/cyan]",
            "  [cyan]export OPENAI_API_KEY=cvc[/cyan]",
            "  [cyan]codex[/cyan]",
            "",
            "[bold cyan]Option 2: Config file (~/.codex/config.toml)[/bold cyan]",
            "",
            "  [cyan]model_provider = \"cvc\"[/cyan]",
            "",
            "  [cyan][model_providers.cvc][/cyan]",
            "  [cyan]name = \"CVC Proxy\"[/cyan]",
            '  [cyan]base_url = "{endpoint}"[/cyan]',
            '  [cyan]env_key = "OPENAI_API_KEY"[/cyan]',
            "",
            "Your API key is passed through to the upstream provider.",
            "",
            "[dim]Works with: codex, codex --provider openai, and custom providers.[/dim]",
        ],
        "steps_win": [
            "[bold]Codex CLI supports custom model providers.[/bold]",
            "",
            "[bold cyan]Option 1: Environment variables[/bold cyan]",
            "",
            "  [cyan]$env:OPENAI_API_BASE = \"{endpoint}/v1\"[/cyan]",
            "  [cyan]$env:OPENAI_API_KEY = \"cvc\"[/cyan]",
            "  [cyan]codex[/cyan]",
            "",
            "[bold cyan]Option 2: Config file (~/.codex/config.toml)[/bold cyan]",
            "",
            "  [cyan]model_provider = \"cvc\"[/cyan]",
            "",
            "  [cyan][model_providers.cvc][/cyan]",
            "  [cyan]name = \"CVC Proxy\"[/cyan]",
            '  [cyan]base_url = "{endpoint}"[/cyan]',
            '  [cyan]env_key = "OPENAI_API_KEY"[/cyan]',
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
        f"  Endpoint   [bold cyan]{endpoint}[/bold cyan]",
        f"  Chat API   [bold cyan]{endpoint}/v1/chat/completions[/bold cyan]",
        f"  Models     [bold cyan]{endpoint}/v1/models[/bold cyan]",
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
            key_status = "[green]● env var[/green]"
        elif has_stored:
            key_status = "[green]● saved[/green]"
        else:
            key_status = "[red]● missing[/red]"
        info_lines.append(f"  API Key    {key_status}  [dim]({env_key})[/dim]")
    elif config.provider == "ollama":
        info_lines.append(f"  API Key    [dim]not needed (local)[/dim]")

    console.print(
        Panel(
            "\n".join(info_lines),
            border_style="green",
            title="[bold green]Starting[/bold green]",
            padding=(1, 2),
        )
    )

    # Quick connection reference
    console.print()
    console.print(
        Panel(
            "  [bold white]Connect your tools:[/bold white]\n\n"
            f"  Base URL   [bold cyan]{endpoint}/v1[/bold cyan]\n"
            f"  API Key    [cyan]cvc[/cyan]  [dim](any non-empty string works)[/dim]\n"
            f"  Model      [cyan]{config.model}[/cyan]\n\n"
            f"  [bold white]Claude Code CLI:[/bold white]\n"
            f"  [cyan]export ANTHROPIC_BASE_URL={endpoint}[/cyan]\n\n"
            "  [bold white]Auth-based IDEs (Antigravity, Windsurf, native Copilot):[/bold white]\n"
            "  Run [bold]cvc mcp[/bold] to start the MCP server instead.\n\n"
            "  [dim]Works with: VS Code, Antigravity, Cursor, Windsurf, Cline,\n"
            "  Continue.dev, Claude Code, Codex CLI, Gemini CLI, Kiro CLI,\n"
            "  Aider, Open WebUI, Firebase Studio, and any OpenAI-compatible tool.[/dim]\n\n"
            "  [dim]Run[/dim] [bold]cvc connect[/bold] [dim]for tool-specific setup instructions.[/dim]",
            border_style="blue",
            title="[bold blue]Connect Your Tools[/bold blue]",
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
            f"  Base URL   [bold cyan]{endpoint}/v1[/bold cyan]\n"
            f"  API Key    [cyan]cvc[/cyan]  [dim](any non-empty string — CVC handles auth)[/dim]\n"
            f"  Model      [cyan]{model}[/cyan]\n\n"
            f"  [dim]CVC exposes a fully OpenAI-compatible API.[/dim]\n"
            f"  [dim]Any tool that supports custom OpenAI endpoints will work.[/dim]",
            border_style="cyan",
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
    colors = {"IDE": "cyan", "IDE Extension": "green", "CLI Tool": "yellow", "Web Interface": "magenta", "Cloud IDE": "red"}

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
    ContextDatabase(config)

    console.print(
        Panel(
            f"  Directory  [bold]{config.cvc_root}[/bold]\n"
            f"  Database   [dim]{config.db_path}[/dim]\n"
            f"  Objects    [dim]{config.objects_dir}[/dim]",
            border_style="green",
            title="[bold green]✓ Initialised[/bold green]",
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
    ctx_size = len(engine.context_window)

    # Header info
    console.print(
        Panel(
            f"  Agent      [bold]{config.agent_id}[/bold]\n"
            f"  Branch     [bold cyan]{engine.active_branch}[/bold cyan]\n"
            f"  HEAD       [bold yellow]{head_short}[/bold yellow]\n"
            f"  Context    [bold]{ctx_size}[/bold] messages\n"
            f"  Provider   [dim]{config.provider} / {config.model}[/dim]",
            border_style="cyan",
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
            header_style="bold cyan",
        )
        table.add_column("", width=3)
        table.add_column("Branch", style="bold")
        table.add_column("HEAD", style="yellow")
        table.add_column("Status")
        for b in branches:
            is_active = b.name == engine.active_branch
            marker = "[bold green]●[/bold green]" if is_active else "[dim]○[/dim]"
            name_style = "bold cyan" if is_active else "white"
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
        header_style="bold cyan",
        title=f"[bold white]Commit Log[/bold white] [dim]— {engine.active_branch}[/dim]",
        title_style="",
    )
    table.add_column("", width=2)
    table.add_column("Hash", style="yellow", width=12)
    table.add_column("Type", style="cyan", width=12)
    table.add_column("Message", ratio=1)
    table.add_column("D", width=3, justify="center")

    for i, e in enumerate(entries):
        icon = TYPE_ICONS.get(e["type"], ">")
        delta = "[dim]d[/dim]" if e["is_delta"] else "[green]●[/green]"
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
                f"  Hash     [yellow]{short_hash}[/yellow]\n"
                f"  Type     [cyan]{commit_type}[/cyan]\n"
                f"  Branch   [dim]{engine.active_branch}[/dim]",
                border_style="green",
                title="[bold green]✓ Committed[/bold green]",
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
                f"  [bold cyan]{name}[/bold cyan]\n"
                f"  From     [dim]{engine.active_branch}[/dim]\n"
                f"  HEAD     [yellow]{(result.commit_hash or '')[:12]}[/yellow]",
                border_style="green",
                title="[bold green]✓ Branch Created[/bold green]",
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
                f"  [bold]{source_branch}[/bold] → [bold cyan]{target}[/bold cyan]\n"
                f"  Commit   [yellow]{(result.commit_hash or '')[:12]}[/yellow]",
                border_style="green",
                title="[bold green]✓ Merged[/bold green]",
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
                f"  Restored to [yellow]{commit_hash[:12]}[/yellow]\n"
                f"  Branch   [dim]{engine.active_branch}[/dim]",
                border_style="green",
                title="[bold green]✓ Time-Travelled[/bold green]",
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
            border_style="green",
            title="[bold green]✓ Hooks Installed[/bold green]",
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
                f"  CVC    [yellow]{result['cvc_hash'][:12]}[/yellow]",
                border_style="green",
                title="[bold green]✓ Snapshot Captured[/bold green]",
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
            _success(f"Restored CVC state: [yellow]{cvc_hash[:12]}[/yellow]")

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
                f"  Transport  [bold cyan]SSE[/bold cyan]\n"
                f"  Endpoint   [bold cyan]http://{host}:{port}/sse[/bold cyan]\n"
                f"  Messages   [bold cyan]http://{host}:{port}/messages[/bold cyan]",
                border_style="green",
                title="[bold green]MCP Server[/bold green]",
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
        header_style="bold cyan",
    )
    table.add_column("", width=3)
    table.add_column("Check", style="bold")
    table.add_column("Status")

    for name, ok, detail in checks:
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
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
            console.print("  [bold cyan]CLI Tools[/bold cyan]")
            for t in cli_tools:
                status = "[green]●[/green]" if t["installed"] else "[red]○[/red]"
                console.print(
                    f"    [cyan]{idx}[/cyan]  {status}  [bold]{t['name']}[/bold]  "
                    f"[dim]({t['binary']})[/dim]"
                )
                index_map[idx] = t["key"]
                idx += 1
            console.print()

        if ide_tools:
            console.print("  [bold yellow]IDEs[/bold yellow]")
            for t in ide_tools:
                status = "[green]●[/green]" if t["installed"] else "[red]○[/red]"
                console.print(
                    f"    [yellow]{idx}[/yellow]  {status}  [bold]{t['name']}[/bold]  "
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

    console.print(f"  [bold]Launching[/bold] [cyan]{resolved}[/cyan] through CVC…")
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
        _success(f"CVC proxy running at [bold cyan]{result['endpoint']}[/bold cyan]")

    if time_machine:
        _success("Time Machine mode: [bold]ON[/bold] (auto-commit every 3 turns)")

    # Show env overrides
    env_overrides = result.get("env_overrides", {})
    if env_overrides:
        for k, v in env_overrides.items():
            _info(f"[dim]{k}[/dim] = [cyan]{v}[/cyan]")

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
                border_style="green",
                title="[bold green]Time Machine Active[/bold green]",
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
                border_style="green",
                title="[bold green]Time Machine Active[/bold green]",
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
        console.print("  [yellow]First-time setup required.[/yellow]")
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
    tm_status = "[bold green]ON[/bold green]" if data.get("time_machine") else "[dim]OFF[/dim]"
    interval = data.get("auto_commit_interval", "?")
    console.print(
        Panel(
            f"  Time Machine    {tm_status}\n"
            f"  Auto-commit     every [bold]{interval}[/bold] assistant turns\n"
            f"  Session timeout [dim]{data.get('session_timeout_seconds', '?')}s[/dim]",
            border_style="cyan",
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
        header_style="bold cyan",
    )
    table.add_column("#", width=4)
    table.add_column("Tool", style="cyan", width=12)
    table.add_column("Started", width=20)
    table.add_column("Messages", justify="right", width=10)
    table.add_column("Commits", justify="right", width=10)
    table.add_column("Status", width=10)

    for s in session_list:
        started = datetime.fromtimestamp(s["started_at"]).strftime("%Y-%m-%d %H:%M") if s.get("started_at") else "?"
        status_str = "[bold green]active[/bold green]" if s.get("active") else "[dim]ended[/dim]"
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
