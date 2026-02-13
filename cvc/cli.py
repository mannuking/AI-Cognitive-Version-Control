"""
cvc.cli — Command-line interface for the Cognitive Version Control system.

Usage:
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
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_config():
    from cvc.core.models import CVCConfig
    from cvc.proxy import _load_config
    return _load_config()


def _get_engine():
    from cvc.core.database import ContextDatabase
    from cvc.operations.engine import CVCEngine
    config = _get_config()
    config.ensure_dirs()
    db = ContextDatabase(config)
    return CVCEngine(config, db), db


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def main(verbose: bool) -> None:
    """CVC — Cognitive Version Control: Git for the AI Mind."""
    _setup_logging(verbose)


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

    console.print(f"[bold green]Starting CVC Proxy[/] on {host}:{port}")
    config = _get_config()
    console.print(f"[dim]Agent: {config.agent_id} | Provider: {config.provider} | Model: {config.model}[/dim]")
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
    root = Path(path) / ".cvc"
    config.cvc_root = root
    config.db_path = root / "cvc.db"
    config.objects_dir = root / "objects"
    config.branches_dir = root / "branches"
    config.ensure_dirs()

    from cvc.core.database import ContextDatabase
    ContextDatabase(config)

    console.print(f"[green]✓[/green] Initialised CVC in [bold]{root}[/bold]")
    console.print(f"  Database: {config.db_path}")
    console.print(f"  Objects:  {config.objects_dir}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@main.command()
def status() -> None:
    """Show CVC status: active branch, HEAD, branches."""
    engine, db = _get_engine()

    table = Table(title="CVC Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Agent", engine.config.agent_id)
    table.add_row("Branch", engine.active_branch)
    table.add_row("HEAD", (engine.head_hash or "—")[:12])
    table.add_row("Context size", str(len(engine.context_window)))
    console.print(table)

    branches = db.index.list_branches()
    if branches:
        bt = Table(title="Branches")
        bt.add_column("Name", style="cyan")
        bt.add_column("HEAD", style="dim")
        bt.add_column("Status")
        for b in branches:
            bt.add_row(b.name, b.head_hash[:12], b.status.value)
        console.print(bt)

    db.close()


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------

@main.command()
@click.option("-n", "--limit", default=20, type=int, help="Max commits to show.")
def log(limit: int) -> None:
    """Show commit history for the active branch."""
    engine, db = _get_engine()
    entries = engine.log(limit=limit)

    table = Table(title=f"Commit Log — {engine.active_branch}")
    table.add_column("Hash", style="yellow", width=12)
    table.add_column("Type", style="cyan", width=12)
    table.add_column("Message")
    table.add_column("Delta", width=5)

    for e in entries:
        table.add_row(
            e["short"],
            e["type"],
            e["message"][:60],
            "δ" if e["is_delta"] else "●",
        )

    console.print(table)
    db.close()


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

@main.command()
@click.option("-m", "--message", required=True, help="Commit message.")
@click.option("-t", "--type", "commit_type", default="checkpoint", help="Commit type.")
def commit(message: str, commit_type: str) -> None:
    """Create a cognitive commit."""
    from cvc.core.models import CVCCommitRequest
    engine, db = _get_engine()
    result = engine.commit(CVCCommitRequest(message=message, commit_type=commit_type))
    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
    db.close()


# ---------------------------------------------------------------------------
# branch
# ---------------------------------------------------------------------------

@main.command()
@click.argument("name")
@click.option("-d", "--description", default="", help="Branch description.")
def branch(name: str, description: str) -> None:
    """Create and switch to a new branch."""
    from cvc.core.models import CVCBranchRequest
    engine, db = _get_engine()
    result = engine.branch(CVCBranchRequest(name=name, description=description))
    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
    db.close()


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

@main.command()
@click.argument("source_branch")
@click.option("--target", default="main", help="Target branch (default: main).")
def merge(source_branch: str, target: str) -> None:
    """Merge a branch into the target."""
    from cvc.core.models import CVCMergeRequest
    engine, db = _get_engine()
    result = engine.merge(CVCMergeRequest(source_branch=source_branch, target_branch=target))
    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
    db.close()


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------

@main.command()
@click.argument("commit_hash")
def restore(commit_hash: str) -> None:
    """Restore context to a previous commit (time-travel)."""
    from cvc.core.models import CVCRestoreRequest
    engine, db = _get_engine()
    result = engine.restore(CVCRestoreRequest(commit_hash=commit_hash))
    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
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
    for hook, path in result.items():
        console.print(f"[green]✓[/green] {hook}: {path}")
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
        console.print(f"[red]✗[/red] {result['error']}")
    else:
        console.print(f"[green]✓[/green] Snapshot: git={result['git_sha'][:8]} ↔ cvc={result['cvc_hash'][:12]}")
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
            console.print(f"[green]✓[/green] Restored CVC state: {cvc_hash[:12]}")
    db.close()


# ---------------------------------------------------------------------------
# setup (guided first-time configuration)
# ---------------------------------------------------------------------------

@main.command()
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai", "google", "ollama"], case_sensitive=False),
    prompt="LLM Provider",
    help="Which LLM provider to use.",
)
@click.option("--model", default="", help="Model override (uses provider default if empty).")
def setup(provider: str, model: str) -> None:
    """Interactive first-time setup — configures provider and initialises .cvc/."""
    from cvc.adapters import PROVIDER_DEFAULTS

    defaults = PROVIDER_DEFAULTS[provider]
    chosen_model = model or defaults["model"]

    # Show model choices
    model_table = {
        "anthropic": [
            ("claude-opus-4-6", "Most intelligent — agents & coding"),
            ("claude-opus-4-5", "Previous flagship — excellent reasoning"),
            ("claude-sonnet-4-5", "Best speed / intelligence balance"),
            ("claude-haiku-4-5", "Fastest & cheapest"),
        ],
        "openai": [
            ("gpt-5.2", "Best for coding & agentic tasks"),
            ("gpt-5.2-codex", "Optimized for long-horizon agentic coding"),
            ("gpt-5-mini", "Fast & cost-efficient"),
        ],
        "google": [
            ("gemini-3-pro", "Most powerful multimodal & agentic model"),
            ("gemini-3-flash", "Balanced speed & intelligence"),
            ("gemini-2.5-flash", "Best price-performance"),
        ],
        "ollama": [
            ("qwen2.5-coder:7b", "Best coding model — 11M+ pulls"),
            ("qwen3-coder:30b", "Latest agentic coding model"),
            ("devstral:24b", "Mistral's best open-source coding agent"),
        ],
    }

    table = Table(title=f"Available {provider.title()} Models")
    table.add_column("Model ID", style="cyan")
    table.add_column("Description")
    table.add_column("Default", width=7)
    for mid, desc in model_table.get(provider, []):
        is_default = "  ●" if mid == chosen_model else ""
        table.add_row(mid, desc, f"[green]{is_default}[/green]")
    console.print(table)

    # Check API key
    env_key = defaults["env_key"]
    if env_key:
        key_val = os.environ.get(env_key, "")
        if key_val:
            console.print(f"[green]✓[/green] {env_key} is set")
        else:
            console.print(f"[yellow]![/yellow] Set [bold]{env_key}[/bold] before running [cyan]cvc serve[/cyan]")

    if provider == "ollama":
        console.print(
            "\n[dim]Make sure Ollama is running: [bold]ollama serve[/bold]\n"
            f"Pull your model: [bold]ollama pull {chosen_model}[/bold][/dim]"
        )

    # Initialise .cvc
    from cvc.core.models import CVCConfig
    config = CVCConfig(provider=provider, model=chosen_model)
    config.ensure_dirs()

    from cvc.core.database import ContextDatabase
    ContextDatabase(config)

    console.print(f"\n[green]✓[/green] Initialised CVC in [bold].cvc/[/bold]")
    console.print(f"  Provider:  [cyan]{provider}[/cyan]")
    console.print(f"  Model:     [cyan]{chosen_model}[/cyan]")
    console.print(f"\nStart the proxy:  [bold]CVC_PROVIDER={provider} cvc serve[/bold]")


if __name__ == "__main__":
    main()
