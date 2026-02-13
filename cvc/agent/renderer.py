"""
cvc.agent.renderer — Rich terminal rendering for the CVC agent.

Handles all visual output: banners, streaming text, tool call displays,
status bars, and the input prompt. Themed with the CVC color palette.

Features:
  - Token-by-token streaming display
  - Cost tracking display
  - Git status integration
  - Tab completion for slash commands
"""

from __future__ import annotations

import asyncio
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
    table.add_column("Command", style=f"bold {THEME['accent']}", width=22)
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
        ("/undo", "Undo the last file change"),
        ("/web <query>", "Search the web for docs/answers"),
        ("/git", "Show Git status and recent commits"),
        ("/git commit <msg>", "Create a Git commit"),
        ("/cost", "Show session cost summary"),
        ("/image <path>", "Analyze an image file"),
        ("/memory", "Show persistent memory from past sessions"),
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


def render_token_usage(
    prompt_tokens: int,
    completion_tokens: int,
    cached: int = 0,
    turn_cost: float = 0.0,
    session_cost: float = 0.0,
) -> None:
    """Show token usage and cost after a response."""
    parts = [f"[{THEME['text_dim']}]tokens: {prompt_tokens} in"]
    if cached > 0:
        pct = (cached / max(prompt_tokens, 1)) * 100
        parts.append(f" ({cached} cached, {pct:.0f}%)")
    parts.append(f" → {completion_tokens} out")
    if session_cost > 0:
        parts.append(f"  │  turn: ${turn_cost:.4f}  │  session: ${session_cost:.4f}")
    parts.append(f"[/{THEME['text_dim']}]")
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
        "patch_file": "🩹",
        "bash": "💻",
        "glob": "🔍",
        "grep": "🔎",
        "list_dir": "📁",
        "web_search": "🌐",
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


# ---------------------------------------------------------------------------
# Streaming Response Renderer
# ---------------------------------------------------------------------------

class StreamingRenderer:
    """
    Renders streaming LLM responses token-by-token using Rich Live display.
    
    Usage:
        renderer = StreamingRenderer()
        renderer.start()
        renderer.add_text("Hello ")
        renderer.add_text("world!")
        response_text = renderer.finish()
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._live: Live | None = None
        self._started = False

    def start(self) -> None:
        """Start the streaming display."""
        console.print(
            f"\n[{THEME['primary_dim']}]┌─[/{THEME['primary_dim']}]"
            f"[bold {THEME['primary_bright']}] Agent[/bold {THEME['primary_bright']}]"
            f"[{THEME['primary_dim']}] ──────────────────────────────────────[/{THEME['primary_dim']}]"
        )
        self._buffer = ""
        self._live = Live(
            Text("▌", style=THEME["text_dim"]),
            console=console,
            refresh_per_second=15,
            transient=True,
        )
        self._live.start()
        self._started = True

    def add_text(self, text: str) -> None:
        """Add streamed text to the display."""
        if not self._started or self._live is None:
            return
        self._buffer += text
        try:
            md = Markdown(self._buffer + "▌")
            self._live.update(md)
        except Exception:
            self._live.update(Text(self._buffer + "▌"))

    def finish(self) -> str:
        """Finish streaming and render the final response. Returns full text."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._started = False

        # Render the final response as a proper panel
        if self._buffer.strip():
            try:
                md = Markdown(self._buffer)
            except Exception:
                md = self._buffer
            console.print(
                Panel(
                    md,
                    border_style=THEME["primary_dim"],
                    title=f"[bold {THEME['primary_bright']}]Agent[/bold {THEME['primary_bright']}]",
                    title_align="left",
                    padding=(1, 2),
                )
            )

        result = self._buffer
        self._buffer = ""
        return result

    def is_active(self) -> bool:
        return self._started


def render_cost_summary(summary: str) -> None:
    """Display cost tracking summary."""
    console.print(
        Panel(
            summary,
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Cost Summary[/bold {THEME['primary_bright']}]",
            padding=(0, 2),
        )
    )


def render_git_status(status_text: str) -> None:
    """Display Git status information."""
    console.print(
        Panel(
            status_text,
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Git Status[/bold {THEME['primary_bright']}]",
            padding=(0, 2),
        )
    )


def render_memory(memory_text: str) -> None:
    """Display memory from past sessions."""
    if not memory_text.strip():
        render_info("No persistent memory found from previous sessions.")
        return
    try:
        md = Markdown(memory_text)
    except Exception:
        md = memory_text
    console.print(
        Panel(
            md,
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Session Memory[/bold {THEME['primary_bright']}]",
            padding=(1, 2),
        )
    )


def render_undo_result(message: str) -> None:
    """Display undo result."""
    if message.startswith("Undone"):
        render_success(message)
    else:
        render_info(message)


def render_web_results(results_text: str) -> None:
    """Display web search results."""
    console.print(
        Panel(
            results_text,
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Web Search[/bold {THEME['primary_bright']}]",
            padding=(0, 2),
        )
    )


def render_session_resume_prompt() -> str | None:
    """
    Ask the user if they want to resume the previous session.
    Returns 'resume' or None.
    """
    console.print(
        f"  [{THEME['text_dim']}]A previous session was found in this workspace.[/{THEME['text_dim']}]"
    )
    try:
        answer = console.input(
            f"  [{THEME['accent']}]Resume previous session? (Y/n):[/{THEME['accent']}] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if answer in ("", "y", "yes"):
        return "resume"
    return None


def render_git_startup_info(status: dict) -> None:
    """Show Git info on startup."""
    if not status.get("is_git"):
        return

    parts = [f"[{THEME['success']}]●[/{THEME['success']}] Git: {status['branch']}"]

    if not status.get("clean"):
        changes = len(status.get("modified", [])) + len(status.get("staged", []))
        untracked = len(status.get("untracked", []))
        change_parts = []
        if changes:
            change_parts.append(f"{changes} changed")
        if untracked:
            change_parts.append(f"{untracked} untracked")
        parts.append(f"  [{THEME['warning']}]({', '.join(change_parts)})[/{THEME['warning']}]")
    else:
        parts.append(f"  [{THEME['text_dim']}](clean)[/{THEME['text_dim']}]")

    console.print("  " + "".join(parts))


# ---------------------------------------------------------------------------
# Tab Completion for Slash Commands
# ---------------------------------------------------------------------------

SLASH_COMMANDS = [
    "/help", "/status", "/log", "/commit", "/branch", "/restore",
    "/search", "/model", "/provider", "/undo", "/web", "/git",
    "/cost", "/image", "/memory", "/serve", "/init", "/compact",
    "/clear", "/exit", "/quit",
]


async def get_input_with_completion(branch: str, turn: int) -> str:
    """
    Get user input with tab completion for slash commands.
    Falls back to basic input if prompt_toolkit is not available.
    Uses prompt_async() to avoid nested asyncio.run() errors.
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style as PTStyle

        completer = WordCompleter(
            SLASH_COMMANDS,
            sentence=True,
        )

        style = PTStyle.from_dict({
            "prompt": "#CC5555",
            "branch": "#CC5555",
            "turn": "#8B7070",
        })

        session = PromptSession(
            completer=completer,
            style=style,
            complete_while_typing=True,
        )

        # Show the CVC prompt header
        console.print(
            f"[{THEME['primary_dim']}]╭─[/{THEME['primary_dim']}]"
            f"[bold {THEME['accent_soft']}] CVC[/bold {THEME['accent_soft']}]"
            f"[{THEME['text_dim']}]@[/{THEME['text_dim']}]"
            f"[{THEME['branch']}]{branch}[/{THEME['branch']}]"
            f"[{THEME['text_dim']}] (turn {turn})[/{THEME['text_dim']}]"
        )

        line = await session.prompt_async("╰─▸ ")
        return line.strip()

    except ImportError:
        # Fall back to basic Rich input
        return await asyncio.to_thread(print_input_prompt, branch, turn)
    except (EOFError, KeyboardInterrupt):
        return "/exit"

