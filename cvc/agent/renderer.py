"""
cvc.agent.renderer — Rich terminal rendering for the CVC agent.

Handles all visual output: banners, streaming text, tool call displays,
status bars, and the input prompt. Themed with the CVC color palette.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich import box

# ---------------------------------------------------------------------------
# CVC Dark Red Theme — #2C0000 and close colors
# ---------------------------------------------------------------------------

# Rich doesn't support all hex as style names, but we can use them directly
THEME = {
    "primary": "#8B0000",       # Dark red — borders, accents
    "primary_dim": "#5C1010",   # Muted red — secondary borders
    "primary_bright": "#CC3333",  # Bright red — highlights
    "accent": "#FF4444",        # Vivid red — user input, important
    "accent_soft": "#FF6B6B",   # Soft red — prompts
    "text": "#E8D0D0",          # Warm light — readable text
    "text_dim": "#8B7070",      # Dimmed warm text
    "success": "#55AA55",       # Green for success
    "warning": "#CCAA33",       # Yellow for warnings
    "error": "#FF3333",         # Bright red for errors
    "tool_name": "#CC6666",     # Tool name color
    "tool_result": "#AA8888",   # Tool result color
    "branch": "#CC5555",        # Branch name color
    "hash": "#BB8844",          # Commit hash color
    "bg": "#2C0000",            # Deep maroon background ref
}

# Use force_terminal=True on Windows to ensure proper unicode rendering
console = Console(force_terminal=sys.stdout.isatty())


def agent_banner(version: str, provider: str, model: str, branch: str, workspace: str) -> None:
    """Print the CVC Agent startup banner."""
    logo = Text()
    logo.append("   ██████ ██    ██  ██████\n", style=THEME["primary_bright"])
    logo.append("  ██      ██    ██ ██\n", style=THEME["primary_bright"])
    logo.append("  ██      ██    ██ ██\n", style=THEME["primary"])
    logo.append("  ██       ██  ██  ██\n", style=THEME["primary"])
    logo.append("   ██████   ████    ██████", style=THEME["primary_dim"])

    tagline = Text("Cognitive Version Control Agent", style=THEME["text_dim"])
    subtitle = Text("Time Machine for AI Agents — Now in YOUR Terminal", style=f"bold {THEME['accent_soft']}")

    content = Text()
    content.append_text(logo)
    content.append("\n\n")
    content.append_text(tagline)
    content.append("\n")
    content.append_text(subtitle)

    console.print(
        Panel(
            content,
            border_style=THEME["primary"],
            padding=(1, 4),
            title=f"[bold {THEME['accent']}]v{version}[/bold {THEME['accent']}]",
            title_align="right",
            subtitle=f"[{THEME['text_dim']}]Time Machine for AI Agents[/{THEME['text_dim']}]",
            subtitle_align="center",
        )
    )

    # Config bar
    config_text = Text()
    config_text.append("  Provider  ", style=THEME["text_dim"])
    config_text.append(provider, style=f"bold {THEME['accent']}")
    config_text.append("  │  ", style=THEME["primary_dim"])
    config_text.append("Model  ", style=THEME["text_dim"])
    config_text.append(model, style=f"bold {THEME['accent']}")
    config_text.append("  │  ", style=THEME["primary_dim"])
    config_text.append("Branch  ", style=THEME["text_dim"])
    config_text.append(branch, style=f"bold {THEME['branch']}")

    console.print(
        Panel(
            config_text,
            border_style=THEME["primary_dim"],
            padding=(0, 2),
        )
    )

    # Workspace
    console.print(
        f"  [{THEME['text_dim']}]Workspace:[/{THEME['text_dim']}] "
        f"[bold {THEME['text']}]{workspace}[/bold {THEME['text']}]"
    )
    console.print()
    console.print(
        f"  [{THEME['text_dim']}]Type your request, or use[/{THEME['text_dim']}] "
        f"[bold {THEME['accent']}]/help[/bold {THEME['accent']}] "
        f"[{THEME['text_dim']}]for commands.[/{THEME['text_dim']}] "
        f"[{THEME['text_dim']}]Ctrl+C to exit.[/{THEME['text_dim']}]"
    )
    console.print()


def print_help() -> None:
    """Show the slash commands help."""
    table = Table(
        box=box.ROUNDED,
        border_style=THEME["primary_dim"],
        show_header=True,
        header_style=f"bold {THEME['primary_bright']}",
    )
    table.add_column("Command", style=f"bold {THEME['accent']}", width=20)
    table.add_column("Description", style=THEME["text"])

    cmds = [
        ("/help", "Show this help message"),
        ("/status", "Show CVC status (branch, HEAD, context)"),
        ("/log", "Show CVC commit history"),
        ("/commit <msg>", "Create a cognitive checkpoint"),
        ("/branch <name>", "Create and switch to a new branch"),
        ("/restore <hash>", "Time-travel to a previous commit"),
        ("/search <query>", "Search commit history for context"),
        ("/model", "Switch model interactively (or /model <name>)"),
        ("/provider", "Switch LLM provider interactively"),
        ("/serve", "Start the CVC proxy in a new terminal"),
        ("/init", "Initialize CVC in the current workspace"),
        ("/compact", "Summarize and compact the conversation"),
        ("/clear", "Clear the conversation (keeps CVC state)"),
        ("/exit, /quit", "Exit the agent"),
    ]
    for cmd, desc in cmds:
        table.add_row(cmd, desc)

    console.print(
        Panel(
            table,
            border_style=THEME["primary"],
            title=f"[bold {THEME['accent']}]Commands[/bold {THEME['accent']}]",
            padding=(1, 1),
        )
    )
    console.print()


def print_input_prompt(branch: str, turn: int) -> str:
    """Print the input prompt and return user input."""
    prompt_text = (
        f"[{THEME['primary_dim']}]╭─[/{THEME['primary_dim']}]"
        f"[bold {THEME['accent_soft']}] CVC[/bold {THEME['accent_soft']}]"
        f"[{THEME['text_dim']}]@[/{THEME['text_dim']}]"
        f"[{THEME['branch']}]{branch}[/{THEME['branch']}]"
        f"[{THEME['text_dim']}] (turn {turn})[/{THEME['text_dim']}]"
    )
    console.print(prompt_text)

    try:
        # Multi-line input support: first line is regular input
        line = console.input(
            f"[{THEME['primary_dim']}]╰─▸[/{THEME['primary_dim']}] "
        )
        return line.strip()
    except EOFError:
        return "/exit"


def render_streaming_start() -> None:
    """Print the assistant response header."""
    console.print(
        f"\n[{THEME['primary_dim']}]┌─[/{THEME['primary_dim']}]"
        f"[bold {THEME['primary_bright']}] Agent[/bold {THEME['primary_bright']}]"
        f"[{THEME['primary_dim']}] ──────────────────────────────────────[/{THEME['primary_dim']}]"
    )


def render_streaming_text(text: str) -> None:
    """Render a chunk of streaming text."""
    console.print(f"[{THEME['primary_dim']}]│[/{THEME['primary_dim']}] ", end="")
    # Render the accumulated text as markdown
    try:
        md = Markdown(text)
        console.print(md)
    except Exception:
        console.print(text)


def render_response_text(text: str) -> None:
    """Render the full assistant response text."""
    if not text.strip():
        return
    console.print(
        f"\n[{THEME['primary_dim']}]┌─[/{THEME['primary_dim']}]"
        f"[bold {THEME['primary_bright']}] Agent[/bold {THEME['primary_bright']}]"
        f"[{THEME['primary_dim']}] ──────────────────────────────────────[/{THEME['primary_dim']}]"
    )
    # Render as markdown within a bordered area
    for line in text.split("\n"):
        console.print(
            f"[{THEME['primary_dim']}]│[/{THEME['primary_dim']}]  {line}"
        )
    console.print(
        f"[{THEME['primary_dim']}]└──────────────────────────────────────────────[/{THEME['primary_dim']}]"
    )


def render_markdown_response(text: str) -> None:
    """Render the assistant response as a Rich Markdown panel."""
    if not text.strip():
        return
    try:
        md = Markdown(text)
    except Exception:
        md = text

    console.print()
    console.print(
        Panel(
            md,
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Agent[/bold {THEME['primary_bright']}]",
            title_align="left",
            padding=(1, 2),
        )
    )


def render_tool_call_start(tool_name: str, args_summary: str) -> None:
    """Show that a tool is being called."""
    icon = _tool_icon(tool_name)
    console.print(
        f"\n  [{THEME['primary_dim']}]⟫[/{THEME['primary_dim']}] "
        f"{icon} [{THEME['tool_name']}]{tool_name}[/{THEME['tool_name']}]"
        f"[{THEME['text_dim']}]({args_summary})[/{THEME['text_dim']}]",
        end="",
    )


def render_tool_call_result(tool_name: str, result: str, elapsed: float) -> None:
    """Show the result of a tool call."""
    # Truncate for display
    display = result
    if len(display) > 500:
        display = display[:500] + f"\n    ... ({len(result) - 500} more chars)"

    elapsed_str = f"{elapsed:.1f}s" if elapsed >= 0.1 else f"{elapsed * 1000:.0f}ms"

    console.print(
        f"  [{THEME['success']}]✓[/{THEME['success']}] "
        f"[{THEME['text_dim']}]{elapsed_str}[/{THEME['text_dim']}]"
    )

    # Show a compact result
    if display.count("\n") <= 5:
        for line in display.split("\n"):
            console.print(f"    [{THEME['tool_result']}]{line}[/{THEME['tool_result']}]")
    else:
        # Show first and last few lines
        lines = display.split("\n")
        for line in lines[:3]:
            console.print(f"    [{THEME['tool_result']}]{line}[/{THEME['tool_result']}]")
        if len(lines) > 6:
            console.print(f"    [{THEME['text_dim']}]... ({len(lines) - 6} more lines)[/{THEME['text_dim']}]")
        for line in lines[-3:]:
            console.print(f"    [{THEME['tool_result']}]{line}[/{THEME['tool_result']}]")


def render_tool_error(tool_name: str, error: str) -> None:
    """Show a tool error."""
    console.print(
        f"  [{THEME['error']}]✗ {tool_name} failed:[/{THEME['error']}] "
        f"[{THEME['text_dim']}]{error[:200]}[/{THEME['text_dim']}]"
    )


def render_auto_commit(message: str, commit_hash: str) -> None:
    """Show an auto-commit notification."""
    console.print(
        f"\n  [{THEME['primary_dim']}]⟫[/{THEME['primary_dim']}] "
        f"[{THEME['success']}]Auto-committed:[/{THEME['success']}] "
        f"[{THEME['hash']}]{commit_hash[:12]}[/{THEME['hash']}] "
        f"[{THEME['text_dim']}]{message}[/{THEME['text_dim']}]"
    )


def render_status(branch: str, head: str, ctx_size: int, provider: str, model: str) -> None:
    """Show CVC status."""
    console.print(
        Panel(
            f"  Branch    [{THEME['branch']}]{branch}[/{THEME['branch']}]\n"
            f"  HEAD      [{THEME['hash']}]{head[:12] if head else '—'}[/{THEME['hash']}]\n"
            f"  Context   [bold]{ctx_size}[/bold] messages\n"
            f"  Provider  [{THEME['text_dim']}]{provider} / {model}[/{THEME['text_dim']}]",
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]CVC Status[/bold {THEME['primary_bright']}]",
            padding=(0, 2),
        )
    )


def render_error(msg: str) -> None:
    """Show an error message."""
    console.print(f"  [{THEME['error']}]✗[/{THEME['error']}] {msg}")


def render_success(msg: str) -> None:
    """Show a success message."""
    console.print(f"  [{THEME['success']}]✓[/{THEME['success']}] {msg}")


def render_info(msg: str) -> None:
    """Show an info message."""
    console.print(f"  [{THEME['text_dim']}]→[/{THEME['text_dim']}] {msg}")


def render_thinking() -> None:
    """Show a thinking indicator."""
    console.print(
        f"  [{THEME['primary_dim']}]⟫[/{THEME['primary_dim']}] "
        f"[{THEME['text_dim']}]Thinking…[/{THEME['text_dim']}]",
        end="\r",
    )


def render_token_usage(prompt_tokens: int, completion_tokens: int, cached: int = 0) -> None:
    """Show token usage after a response."""
    parts = [f"[{THEME['text_dim']}]tokens: {prompt_tokens} in"]
    if cached > 0:
        pct = (cached / max(prompt_tokens, 1)) * 100
        parts.append(f" ({cached} cached, {pct:.0f}%)")
    parts.append(f" → {completion_tokens} out[/{THEME['text_dim']}]")
    console.print(f"  {''.join(parts)}")


def render_goodbye() -> None:
    """Show the goodbye message."""
    console.print()
    console.print(
        Panel(
            f"  [{THEME['text']}]Session ended. Your context is preserved in CVC.[/{THEME['text']}]\n"
            f"  [{THEME['text_dim']}]Run [bold]cvc agent[/bold] to continue where you left off.[/{THEME['text_dim']}]",
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Goodbye[/bold {THEME['primary_bright']}]",
            padding=(0, 2),
        )
    )
    console.print()


def _tool_icon(name: str) -> str:
    """Get an icon for a tool."""
    icons = {
        "read_file": "📄",
        "write_file": "✏️",
        "edit_file": "🔧",
        "bash": "💻",
        "glob": "🔍",
        "grep": "🔎",
        "list_dir": "📁",
        "cvc_status": "📊",
        "cvc_log": "📜",
        "cvc_commit": "💾",
        "cvc_branch": "🌿",
        "cvc_restore": "⏪",
        "cvc_merge": "🔀",
        "cvc_search": "🔮",
        "cvc_diff": "📐",
    }
    return icons.get(name, "🔧")
