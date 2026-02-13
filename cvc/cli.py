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

VERSION = "0.1.0"


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
    from cvc.proxy import _load_config
    return _load_config()


def _get_engine():
    from cvc.core.database import ContextDatabase
    from cvc.operations.engine import CVCEngine
    config = _get_config()
    config.ensure_dirs()
    db = ContextDatabase(config)
    return CVCEngine(config, db), db


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
            ("setup", "Interactive first-time setup"),
            ("serve", "Start the Cognitive Proxy server"),
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
                "[bold white]Get started in 30 seconds:[/bold white]\n\n"
                "  [cyan]$[/cyan] cvc setup              [dim]# Pick your provider & model[/dim]\n"
                "  [cyan]$[/cyan] cvc serve              [dim]# Start the proxy[/dim]\n"
                "  [cyan]$[/cyan] [dim]Point your agent → http://127.0.0.1:8000[/dim]",
                border_style="green",
                title="[bold green]Quick Start[/bold green]",
                padding=(1, 2),
            )
        )

        console.print(
            "\n  [dim]Run[/dim] [bold]cvc <command> --help[/bold] [dim]for details on any command.[/dim]\n"
        )


@click.group(cls=CvcGroup)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.version_option(VERSION, prog_name="cvc")
def main(verbose: bool) -> None:
    """CVC — Cognitive Version Control: Git for the AI Mind."""
    _setup_logging(verbose)


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
def setup(provider: str | None, model: str) -> None:
    """Interactive first-time setup — pick your provider, model, and go."""
    from cvc.adapters import PROVIDER_DEFAULTS

    _banner("Setup Wizard")

    # --- Provider selection -----------------------------------------------
    if not provider:
        console.print(
            Panel(
                "[bold white]Choose your LLM provider:[/bold white]",
                border_style="cyan",
                padding=(0, 2),
            )
        )
        console.print()

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
        console.print()

    defaults = PROVIDER_DEFAULTS[provider]
    chosen_model = model or defaults["model"]

    # --- Model selection --------------------------------------------------
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
    console.print(f"  [dim]Default model:[/dim] [bold cyan]{chosen_model}[/bold cyan]")
    console.print()

    # --- API key check ----------------------------------------------------
    env_key = defaults["env_key"]
    if env_key:
        key_val = os.environ.get(env_key, "")
        if key_val:
            masked = key_val[:8] + "…" + key_val[-4:]
            _success(f"[bold]{env_key}[/bold] is set ({masked})")
        else:
            _warn(f"[bold]{env_key}[/bold] is not set")
            _hint(
                f"Set your API key before starting the proxy:\n\n"
                f"  [cyan]export {env_key}=\"your-key-here\"[/cyan]  [dim]# Bash / macOS[/dim]\n"
                f"  [cyan]$env:{env_key} = \"your-key-here\"[/cyan]   [dim]# PowerShell[/dim]"
            )
    elif provider == "ollama":
        _success("No API key needed for Ollama")
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

    console.print()

    # --- Initialise .cvc --------------------------------------------------
    from cvc.core.models import CVCConfig
    config = CVCConfig(provider=provider, model=chosen_model)
    config.ensure_dirs()

    from cvc.core.database import ContextDatabase
    ContextDatabase(config)

    console.print(
        Panel(
            f"  Provider   [bold cyan]{provider}[/bold cyan]\n"
            f"  Model      [bold cyan]{chosen_model}[/bold cyan]\n"
            f"  Database   [dim]{config.db_path}[/dim]\n"
            f"  Objects    [dim]{config.objects_dir}[/dim]",
            border_style="green",
            title="[bold green]✓ CVC Initialised[/bold green]",
            padding=(1, 2),
        )
    )

    # --- Next steps -------------------------------------------------------
    console.print()
    if sys.platform == "win32":
        env_cmd = f'$env:CVC_PROVIDER = "{provider}"'
    else:
        env_cmd = f'export CVC_PROVIDER="{provider}"'

    console.print(
        Panel(
            f"  [cyan]$[/cyan] {env_cmd}\n"
            f"  [cyan]$[/cyan] cvc serve\n"
            f"  [cyan]$[/cyan] [dim]Then point your agent → http://127.0.0.1:8000[/dim]",
            border_style="blue",
            title="[bold blue]Next Steps[/bold blue]",
            padding=(1, 2),
        )
    )
    console.print()


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
        f"  Provider   [bold]{config.provider}[/bold]",
        f"  Model      [bold]{config.model}[/bold]",
        f"  Agent      [dim]{config.agent_id}[/dim]",
    ]

    env_key_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
    env_key = env_key_map.get(config.provider, "")
    if env_key:
        has_key = bool(os.environ.get(env_key))
        key_status = "[green]● set[/green]" if has_key else "[red]● missing[/red]"
        info_lines.append(f"  API Key    {key_status}  [dim]({env_key})[/dim]")

    console.print(
        Panel(
            "\n".join(info_lines),
            border_style="green",
            title="[bold green]Starting[/bold green]",
            padding=(1, 2),
        )
    )

    console.print(
        f"\n  [dim]Point your agent to[/dim] [bold underline]{endpoint}/v1/chat/completions[/bold underline]\n"
        f"  [dim]Press[/dim] [bold]Ctrl+C[/bold] [dim]to stop.[/dim]\n"
    )

    uvicorn.run(
        "cvc.proxy:app",
        host=host,
        port=port,
        reload=do_reload,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@main.command()
@click.option("--path", default=".", help="Project root to initialise.")
def init(path: str) -> None:
    """Initialise a .cvc/ directory in the project."""
    config = _get_config()
    root = Path(path).resolve() / ".cvc"
    config.cvc_root = root
    config.db_path = root / "cvc.db"
    config.objects_dir = root / "objects"
    config.branches_dir = root / "branches"
    config.ensure_dirs()

    from cvc.core.database import ContextDatabase
    ContextDatabase(config)

    console.print(
        Panel(
            f"  Directory  [bold]{root}[/bold]\n"
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
# doctor (system health check)
# ---------------------------------------------------------------------------

@main.command()
def doctor() -> None:
    """Check your CVC installation and environment."""
    from cvc.adapters import PROVIDER_DEFAULTS

    _banner("System Check")

    checks: list[tuple[str, bool, str]] = []

    # Python version
    py = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python", py_ok, f"{py}  {'✓ 3.11+' if py_ok else '✗ Need 3.11+'}"))

    # .cvc directory
    cvc_exists = Path(".cvc").exists()
    checks.append((".cvc/ directory", cvc_exists, "Found" if cvc_exists else "Not found — run: cvc init"))

    # Git
    try:
        import subprocess
        subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, check=True)
        checks.append(("Git repository", True, "Found"))
    except Exception:
        checks.append(("Git repository", False, "Not a Git repo (VCS bridge won't work)"))

    # Provider API keys
    for prov, defaults in PROVIDER_DEFAULTS.items():
        env_key_name = defaults["env_key"]
        if env_key_name:
            has_key = bool(os.environ.get(env_key_name))
            checks.append((f"{prov.title()} key", has_key, f"{env_key_name} {'● set' if has_key else '○ not set'}"))

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

    all_ok = all(ok for _, ok, _ in checks[:2])  # Only Python + .cvc are required
    if all_ok:
        _success("CVC is ready to go!")
    else:
        _warn("Some checks failed. See details above.")

    console.print()


if __name__ == "__main__":
    main()
