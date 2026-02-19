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
    logo.append(" ██████╗ ██╗   ██╗  ██████╗\n", style=THEME["primary_bright"])
    logo.append("██╔════╝ ██║   ██║ ██╔════╝\n", style=THEME["primary_bright"])
    logo.append("██║      ██║   ██║ ██║\n", style=THEME["primary"])
    logo.append("██║      ╚██╗ ██╔╝ ██║\n", style=THEME["primary"])
    logo.append("╚██████╗  ╚████╔╝  ╚██████╗\n", style=THEME["primary_dim"])
    logo.append(" ╚═════╝   ╚═══╝    ╚═════╝", style=THEME["primary_dim"])

    tagline = Text("Cognitive Version Control Agent", style=THEME["text_dim"])
    subtitle = Text("Time Machine for AI Agents — Now in YOUR Terminal", style=f"bold {THEME['accent_soft']}")

    content = Text()
    content.append_text(logo)
    content.append("\n\n")
    content.append_text(tagline)
    content.append("\n")
    content.append_text(subtitle)

    # Banner box with dual top labels:
    #   "Meena" center, version right, "Time Machine for AI Agents" bottom center
    # We draw the top border manually for dual-position labels, then use
    # a Panel (without title) for the body + subtitle.
    tw = console.width or 80
    ver = f" v{version} "
    meena = " Meena "
    # positions on the top border (between the ╭ and ╮ corners)
    inner = tw - 2
    center = inner // 2
    m_start = max(center - len(meena) // 2, 1)
    m_end = m_start + len(meena)
    v_start = max(inner - len(ver), m_end + 1)

    top = Text()
    top.append("╭", style=THEME["primary"])
    top.append("─" * m_start, style=THEME["primary"])
    top.append(meena, style=f"bold {THEME['primary_bright']}")
    gap = v_start - m_end
    top.append("─" * max(gap, 1), style=THEME["primary"])
    top.append(ver, style=f"bold {THEME['accent']}")
    remaining = inner - v_start - len(ver)
    top.append("─" * max(remaining, 0), style=THEME["primary"])
    top.append("╮", style=THEME["primary"])
    console.print(top)

    # Body + bottom border via Panel with no top (custom box)
    from rich.box import Box
    _NO_TOP_BOX = Box(
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
            border_style=THEME["primary"],
            padding=(1, 4),
            width=tw,
            subtitle=f"[{THEME['text_dim']}]Time Machine for AI Agents[/{THEME['text_dim']}]",
            subtitle_align="center",
        ),
        highlight=False,
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
        ("/branch <name>", "Create a new branch (creates & switches)"),
        ("/checkout <name>", "Switch to an existing branch"),
        ("/branches", "List all branches"),
        ("/merge <source>", "Merge source branch into current branch"),
        ("/restore <hash>", "Time-travel to a previous commit"),
        ("/search <query>", "Search commit history for context"),
        ("/files [pattern]", "List files in workspace (optional filter)"),
        ("/summary", "Get codebase structure summary"),
        ("/diff [file]", "Show recent diffs or specific file changes"),
        ("/continue", "Continue AI response from last point"),
        ("/model", "Switch model interactively (or /model <name>)"),
        ("/provider", "Switch LLM provider interactively"),
        ("/undo", "Undo the last file change"),
        ("/web <query>", "Search the web for docs/answers"),
        ("/git", "Show Git status and recent commits"),
        ("/git commit <msg>", "Create a Git commit"),
        ("/cost", "Show session cost summary"),
        ("/analytics", "Show detailed session & usage analytics"),
        ("/image <path> [prompt]", "Load image file (+ send prompt inline)"),
        ("/paste [prompt]", "Paste clipboard image (+ send prompt inline)"),
        ("/memory", "Show persistent memory from past sessions"),
        ("/serve", "Start the CVC proxy in a new terminal"),
        ("/init", "Initialize CVC in the current workspace"),
        ("/compact", "Summarize and compact the conversation"),
        ("/health", "Context Autopilot health dashboard"),
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


def print_input_prompt(branch: str, turn: int, health_bar: str = "") -> str:
    """Print the input prompt and return user input."""
    health_suffix = f"  {health_bar}" if health_bar else ""
    prompt_text = (
        f"[{THEME['primary_dim']}]╭─[/{THEME['primary_dim']}]"
        f"[bold {THEME['accent_soft']}] CVC[/bold {THEME['accent_soft']}]"
        f"[{THEME['text_dim']}]@[/{THEME['text_dim']}]"
        f"[{THEME['branch']}]{branch}[/{THEME['branch']}]"
        f"[{THEME['text_dim']}] (turn {turn})[/{THEME['text_dim']}]"
        f"{health_suffix}"
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
    """Show that a tool is being called — clean, professional, human-readable."""
    label, icon = _tool_display(tool_name)
    # args_summary is already a human-friendly description (built by chat.py)
    desc = args_summary if args_summary else ""
    console.print(
        f"\n  [{THEME['primary_dim']}]⟫[/{THEME['primary_dim']}] "
        f"{icon} [{THEME['tool_name']}]{label}[/{THEME['tool_name']}]"
        f"{'  ' if desc else ''}"
        f"[{THEME['text_dim']}]{desc}[/{THEME['text_dim']}]",
        end="",
    )


def render_tool_call_result(tool_name: str, result: str, elapsed: float) -> None:
    """Append result info on the SAME line as the tool start — ultra minimal."""
    elapsed_str = f"{elapsed:.1f}s" if elapsed >= 0.1 else f"{elapsed * 1000:.0f}ms"

    # Build a compact inline summary (shown in parentheses)
    summary = _smart_result_summary(tool_name, result)
    suffix = f"  ({summary})" if summary else ""

    console.print(
        f"  [{THEME['success']}]\u2713[/{THEME['success']}] "
        f"[{THEME['text_dim']}]{elapsed_str}{suffix}[/{THEME['text_dim']}]"
    )


def render_tool_error(tool_name: str, error: str) -> None:
    """Show a tool error with professional label."""
    label, _ = _tool_display(tool_name)
    console.print(
        f"  [{THEME['error']}]✗ {label} failed:[/{THEME['error']}] "
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


# Track when the last thinking indicator started (for elapsed time display)
_thinking_start_time: float = 0.0
_thinking_model: str = ""


def _print_thinking_line(elapsed: float = 0.0) -> None:
    """Overwrite the current terminal line with the thinking indicator + elapsed time."""
    model_hint = (
        f" [{THEME['text_dim']}]({_thinking_model})[/{THEME['text_dim']}]"
        if _thinking_model else ""
    )
    elapsed_hint = (
        f" [{THEME['warning']}]({elapsed:.0f}s)[/{THEME['warning']}]"
        if elapsed >= 5 else ""
    )
    console.print(
        f"  [{THEME['primary_dim']}]⟫[/{THEME['primary_dim']}] "
        f"[italic {THEME['text_dim']}]Reasoning…[/italic {THEME['text_dim']}]{model_hint}{elapsed_hint}",
        end="\r",
    )


def render_thinking(model: str = "") -> None:
    """Show a polished thinking indicator with model name."""
    global _thinking_start_time, _thinking_model
    _thinking_start_time = time.time()
    _thinking_model = model
    _print_thinking_line(0.0)


async def animate_thinking() -> None:
    """Background task: update the thinking line with live elapsed time every second.

    Start with ``asyncio.create_task(animate_thinking())`` right after
    ``render_thinking()``.  Cancel the task as soon as the first token arrives
    so the elapsed counter disappears cleanly.
    """
    try:
        while True:
            await asyncio.sleep(1.0)
            elapsed = time.time() - _thinking_start_time
            _print_thinking_line(elapsed)
    except asyncio.CancelledError:
        pass


def render_slow_model_warning(model: str) -> None:
    """Display a notice when the user picks an inherently slow thinking model."""
    console.print(
        Panel(
            f"  [{THEME['warning']}]⚠  {model}[/{THEME['warning']}] is a server-side thinking model.\n"
            f"  [bold]Expected response time: 60 – 120 s[/bold] even for simple queries.\n"
            f"  This is a Google API constraint — the model reasons before streaming any tokens.\n\n"
            f"  [{THEME['text_dim']}]Faster alternatives:[/{THEME['text_dim']}]\n"
            f"  [{THEME['text_dim']}]  • [bold]cvc agent --model gemini-2.5-flash[/bold]       ← recommended for daily use[/{THEME['text_dim']}]\n"
            f"  [{THEME['text_dim']}]  • [bold]cvc agent --model gemini-3-flash-preview[/bold]  ← Gemini 3 speed variant[/{THEME['text_dim']}]\n"
            f"  [{THEME['text_dim']}]  • [bold]cvc agent --no-think[/bold]                       ← disable thinking (fastest, lower quality)[/{THEME['text_dim']}]",
            border_style=THEME["warning"],
            title=f"[bold {THEME['warning']}] Slow Model Notice [/bold {THEME['warning']}]",
            padding=(0, 2),
        )
    )
    console.print()


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


# ---------------------------------------------------------------------------
# Tool Display System — human-readable labels, icons, and smart summaries
# ---------------------------------------------------------------------------

# Maps raw tool function names to (Human Label, Icon)
_TOOL_DISPLAY: dict[str, tuple[str, str]] = {
    # File operations
    "read_file":    ("Reading file",          "📄"),
    "write_file":   ("Writing file",          "✏️"),
    "edit_file":    ("Editing file",           "🔧"),
    "patch_file":   ("Patching file",          "🩹"),
    # Shell
    "bash":         ("Running command",        "⚡"),
    # Search & discovery
    "glob":         ("Finding files",          "📂"),
    "grep":         ("Searching code",         "🔍"),
    "list_dir":     ("Listing directory",      "📁"),
    "web_search":   ("Searching the web",      "🌐"),
    # CVC Time Machine
    "cvc_status":   ("Checking CVC status",    "📊"),
    "cvc_log":      ("Viewing commit history", "📜"),
    "cvc_commit":   ("Saving checkpoint",      "💾"),
    "cvc_branch":   ("Creating branch",        "🌿"),
    "cvc_restore":  ("Time-traveling",         "⏪"),
    "cvc_merge":    ("Merging branches",       "🔀"),
    "cvc_search":   ("Searching history",      "🔮"),
    "cvc_diff":     ("Comparing contexts",     "📐"),
}


def _tool_display(name: str) -> tuple[str, str]:
    """Return (human_label, icon) for a tool name."""
    return _TOOL_DISPLAY.get(name, (name, "🔧"))


def _tool_icon(name: str) -> str:
    """Get an icon for a tool (legacy helper)."""
    _, icon = _tool_display(name)
    return icon


def _smart_result_summary(tool_name: str, result: str) -> str:
    """
    Build a smart, human-readable result summary based on the tool type.
    Instead of showing raw output, show meaningful context.
    """
    if not result:
        return ""

    lines = [l.strip() for l in result.split("\n") if l.strip()]
    if not lines:
        return ""

    first = lines[0]

    if tool_name == "read_file":
        # Extract file path & line count from typical result
        # Result usually starts with "File: path (N lines)"
        if first.startswith("File:"):
            return first
        # Count lines as fallback
        line_count = len(lines)
        return f"{line_count} lines read"

    elif tool_name == "write_file":
        if "Created" in first or "Wrote" in first:
            return first[:80]
        return "File saved successfully"

    elif tool_name == "edit_file":
        if "Applied" in first or "Edited" in first:
            return first[:80]
        if first.startswith("Error"):
            return first[:80]
        return "Edit applied"

    elif tool_name == "patch_file":
        return first[:80] if first else "Patch applied"

    elif tool_name == "bash":
        # Show first meaningful line of output, skip empties
        output = first[:80]
        if len(lines) > 1:
            output += f"  (+{len(lines) - 1} more lines)"
        return output

    elif tool_name == "glob":
        # Count matches
        match_count = len(lines)
        return f"{match_count} file(s) found"

    elif tool_name == "grep":
        # Result often has "Found N match(es)" or just matching lines
        if "Found" in first and "match" in first:
            return first[:80]
        match_count = len(lines)
        return f"{match_count} match(es) found"

    elif tool_name == "list_dir":
        item_count = len(lines)
        dirs = sum(1 for l in lines if l.endswith("/"))
        files = item_count - dirs
        return f"{files} files, {dirs} directories"

    elif tool_name == "web_search":
        result_count = sum(1 for l in lines if l.startswith("[" ) or l.startswith("1") or l.startswith("• "))
        if result_count:
            return f"{result_count} results — {first[:60]}"
        return first[:80]

    elif tool_name.startswith("cvc_"):
        # CVC tools — show the first line (usually a status or hash)
        return first[:80]

    # Fallback: first meaningful line
    return first[:80]


# ---------------------------------------------------------------------------
# Streaming Response Renderer
# ---------------------------------------------------------------------------

class StreamingRenderer:
    """
    Renders streaming LLM responses token-by-token using Rich Live display.
    
    PERF: Optimized for minimal time-to-first-visible-token:
    - Live display starts with minimal overhead (12fps, no initial render)
    - First few tokens rendered immediately via direct console write
    - Markdown parsing only kicks in after enough content accumulates
    
    Usage:
        renderer = StreamingRenderer()
        renderer.start()
        renderer.add_text("Hello ")
        renderer.add_text("world!")
        response_text = renderer.finish()
    """

    # Number of characters to accumulate before switching from raw text to markdown
    _MD_THRESHOLD = 80

    def __init__(self) -> None:
        self._buffer = ""
        self._live: Live | None = None
        self._started = False
        self._first_token_time: float = 0

    def start(self) -> None:
        """Start the streaming display."""
        console.print()  # blank line before the streaming panel
        self._buffer = ""
        self._first_token_time = time.time()
        self._live = Live(
            Text("", style=THEME["text_dim"]),
            console=console,
            refresh_per_second=12,
            transient=True,
            vertical_overflow="visible",
        )
        self._live.start()
        self._started = True

    def add_text(self, text: str) -> None:
        """Add streamed text to the display."""
        if not self._started or self._live is None:
            return
        self._buffer += text
        try:
            # PERF: For the first few tokens, skip markdown parsing
            # to get text on screen as fast as possible.
            if len(self._buffer) < self._MD_THRESHOLD:
                self._live.update(Text(self._buffer + "▌"))
            else:
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
# Tab Completion for Slash Commands + Ctrl+V Image Paste
# ---------------------------------------------------------------------------

SLASH_COMMANDS = [
    "/help", "/status", "/log", "/commit", "/branch", "/restore",
    "/search", "/model", "/provider", "/undo", "/web", "/git",
    "/cost", "/image", "/paste", "/memory", "/serve", "/init", "/compact",
    "/health", "/clear", "/exit", "/quit",
]

# Module-level list to pass pasted images from the Ctrl+V key binding
# back to the REPL loop.  Each entry is (base64_data, mime_type).
_pending_paste_images: list[tuple[str, str]] = []


def get_pending_paste_images() -> list[tuple[str, str]]:
    """Return and clear any images pasted via Ctrl+V during input."""
    imgs = list(_pending_paste_images)
    _pending_paste_images.clear()
    return imgs


async def get_input_with_completion(branch: str, turn: int, health_bar: str = "") -> str:
    """
    Get user input with tab completion for slash commands.
    Falls back to basic input if prompt_toolkit is not available.
    Uses prompt_async() to avoid nested asyncio.run() errors.

    Ctrl+V is intercepted: if the system clipboard contains an image,
    the image is grabbed and a 📎 marker is inserted into the input
    buffer. The actual image data is stored in _pending_paste_images
    for the REPL loop to consume.  If the clipboard contains text,
    normal paste behaviour is preserved.
    """
    # Clear any stale images from a previous prompt
    _pending_paste_images.clear()

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.styles import Style as PTStyle
        from prompt_toolkit.key_binding import KeyBindings

        completer = WordCompleter(
            SLASH_COMMANDS,
            sentence=True,
        )

        style = PTStyle.from_dict({
            "prompt": "#CC5555",
            "branch": "#CC5555",
            "turn": "#8B7070",
        })

        # ── Custom key bindings ──────────────────────────────────────
        kb = KeyBindings()

        @kb.add("c-v")
        def _ctrl_v(event):
            """Intercept Ctrl+V: if clipboard has an image, grab it;
            otherwise fall through to normal text paste."""
            # Lazy-import to avoid circular deps
            from cvc.agent.chat import _grab_clipboard_images

            images = _grab_clipboard_images()
            if images:
                # Store images for the REPL loop
                _pending_paste_images.extend(images)

                # Insert a visible marker into the text buffer so the
                # user sees that an image was attached
                buf = event.app.current_buffer
                count = len(images)
                marker = f" 📎[{count} image{'s' if count > 1 else ''}] "
                buf.insert_text(marker)
            else:
                # No image — paste text from system clipboard
                import sys as _sys
                _text = ""
                if _sys.platform == "win32":
                    try:
                        import ctypes
                        CF_UNICODETEXT = 13
                        u32 = ctypes.windll.user32
                        k32 = ctypes.windll.kernel32
                        if u32.OpenClipboard(0):
                            try:
                                h = u32.GetClipboardData(CF_UNICODETEXT)
                                if h:
                                    k32.GlobalLock.restype = ctypes.c_wchar_p
                                    _text = k32.GlobalLock(h) or ""
                                    k32.GlobalUnlock(h)
                            finally:
                                u32.CloseClipboard()
                    except Exception:
                        pass
                else:
                    # macOS / Linux: try pyperclip or subprocess
                    try:
                        import subprocess
                        if _sys.platform == "darwin":
                            _text = subprocess.run(
                                ["pbpaste"], capture_output=True, text=True, timeout=2,
                            ).stdout
                        else:
                            _text = subprocess.run(
                                ["xclip", "-selection", "clipboard", "-o"],
                                capture_output=True, text=True, timeout=2,
                            ).stdout
                    except Exception:
                        pass

                if _text:
                    event.app.current_buffer.insert_text(_text)
                else:
                    # Final fallback: prompt_toolkit's internal clipboard
                    event.app.current_buffer.paste_clipboard_data(
                        event.app.clipboard.get_data(),
                    )

        session = PromptSession(
            completer=completer,
            style=style,
            complete_while_typing=True,
            key_bindings=kb,
        )

        # Show the CVC prompt header (with optional health bar)
        health_suffix = f"  {health_bar}" if health_bar else ""
        console.print(
            f"[{THEME['primary_dim']}]╭─[/{THEME['primary_dim']}]"
            f"[bold {THEME['accent_soft']}] CVC[/bold {THEME['accent_soft']}]"
            f"[{THEME['text_dim']}]@[/{THEME['text_dim']}]"
            f"[{THEME['branch']}]{branch}[/{THEME['branch']}]"
            f"[{THEME['text_dim']}] (turn {turn})[/{THEME['text_dim']}]"
            f"{health_suffix}"
        )

        line = await session.prompt_async("╰─▸ ")
        return line.strip()

    except ImportError:
        # Fall back to basic Rich input
        return await asyncio.to_thread(print_input_prompt, branch, turn, health_bar)
    except (EOFError, KeyboardInterrupt):
        return "/exit"


# ---------------------------------------------------------------------------
# Context Autopilot Rendering
# ---------------------------------------------------------------------------

def render_autopilot_action(actions: list[str]) -> None:
    """Show Context Autopilot actions taken during a turn."""
    if not actions:
        return
    console.print()
    console.print(
        f"  [{THEME['primary_dim']}]⟫[/{THEME['primary_dim']}] "
        f"[bold #CC7733]Context Autopilot[/bold #CC7733]"
    )
    for action in actions:
        console.print(f"    [{THEME['text_dim']}]→ {action}[/{THEME['text_dim']}]")


def render_context_health(report) -> None:
    """
    Render a detailed context health dashboard for /health command.
    Accepts a ContextHealthReport object.
    """
    from cvc.agent.context_autopilot import HealthLevel

    color_map = {
        HealthLevel.GREEN: THEME["success"],
        HealthLevel.YELLOW: THEME["warning"],
        HealthLevel.ORANGE: "#CC7733",
        HealthLevel.RED: THEME["error"],
    }
    label_map = {
        HealthLevel.GREEN: "HEALTHY",
        HealthLevel.YELLOW: "THINNING",
        HealthLevel.ORANGE: "COMPACTING",
        HealthLevel.RED: "CRITICAL",
    }
    color = color_map.get(report.health_level, THEME["text"])
    label = label_map.get(report.health_level, "UNKNOWN")

    # Build the health bar
    bar = report.format_bar_rich(width=30)

    content = (
        f"  Status    [{color}]● {label}[/{color}]\n"
        f"  Context   {bar}\n"
        f"  Tokens    [bold]{report.estimated_tokens:,}[/bold] / {report.context_limit:,}\n"
        f"  Remaining [bold]{report.remaining_tokens:,}[/bold] tokens ({report.remaining_pct:.0f}%)\n"
        f"\n"
        f"  [{THEME['text_dim']}]Breakdown:[/{THEME['text_dim']}]\n"
        f"    System     {report.system_tokens:>8,} tokens\n"
        f"    User       {report.user_tokens:>8,} tokens\n"
        f"    Assistant  {report.assistant_tokens:>8,} tokens\n"
        f"    Tool       {report.tool_result_tokens:>8,} tokens "
        f"({report.tool_result_count} results)\n"
        f"\n"
        f"  [{THEME['text_dim']}]Messages: {report.message_count}  │  "
        f"Thinnable: {report.thinning_candidates}  │  "
        f"Compactable: {'Yes' if report.compaction_available else 'No'}[/{THEME['text_dim']}]"
    )

    if report.actions_taken:
        content += f"\n\n  [{THEME['warning']}]Actions taken this turn:[/{THEME['warning']}]"
        for action in report.actions_taken:
            content += f"\n    → {action}"

    console.print(
        Panel(
            content,
            border_style=color,
            title=f"[bold {color}]Context Autopilot — Health Dashboard[/bold {color}]",
            padding=(1, 2),
        )
    )


def render_autopilot_diagnostics(diagnostics: dict) -> None:
    """Render full autopilot diagnostics for /health verbose."""
    content = (
        f"  Enabled     [bold]{diagnostics['enabled']}[/bold]\n"
        f"  Model       {diagnostics['model']}\n"
        f"  Limit       {diagnostics['context_limit']:,} tokens\n"
        f"\n"
        f"  [{THEME['text_dim']}]Thresholds:[/{THEME['text_dim']}]\n"
        f"    Thin       {diagnostics['thresholds']['thin']}\n"
        f"    Compact    {diagnostics['thresholds']['compact']}\n"
        f"    Critical   {diagnostics['thresholds']['critical']}\n"
        f"\n"
        f"  [{THEME['text_dim']}]Session Stats:[/{THEME['text_dim']}]\n"
        f"    Compactions  {diagnostics['session_stats']['compactions_performed']}\n"
        f"    Thinnings    {diagnostics['session_stats']['thinnings_performed']}\n"
        f"    Tokens Saved {diagnostics['session_stats']['tokens_saved']:,}\n"
    )

    actions = diagnostics["session_stats"].get("actions_log", [])
    if actions:
        content += f"\n  [{THEME['text_dim']}]Recent Actions:[/{THEME['text_dim']}]"
        for entry in actions[-5:]:
            for action in entry.get("actions", []):
                content += f"\n    → {action}"

    console.print(
        Panel(
            content,
            border_style=THEME["primary_dim"],
            title=f"[bold {THEME['primary_bright']}]Autopilot Diagnostics[/bold {THEME['primary_bright']}]",
            padding=(1, 2),
        )
    )
