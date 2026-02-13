"""
cvc.agent.chat — The main agentic REPL loop.

This is the heart of the CVC Agent — a Claude Code-style interactive
coding assistant that runs in your terminal with Time Machine capabilities.

The loop:
  1. Accept user input (or slash command)
  2. Add to conversation history
  3. Send to LLM with tool definitions
  4. If LLM returns tool calls → execute each, send results back → goto 3
  5. If LLM returns text → render and wait for next input
  6. Auto-commit at configurable intervals
  7. Push all messages to CVC context window
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from cvc.agent.executor import ToolExecutor
from cvc.agent.llm import AgentLLM
from cvc.agent.renderer import (
    agent_banner,
    console,
    print_help,
    print_input_prompt,
    render_auto_commit,
    render_error,
    render_goodbye,
    render_info,
    render_markdown_response,
    render_status,
    render_success,
    render_thinking,
    render_token_usage,
    render_tool_call_result,
    render_tool_call_start,
    render_tool_error,
    THEME,
)
from cvc.agent.system_prompt import build_system_prompt
from cvc.agent.tools import AGENT_TOOLS, MODEL_CATALOG_AGENT
from cvc.core.database import ContextDatabase
from cvc.core.models import (
    CVCCommitRequest,
    CVCConfig,
    ContextMessage,
    GlobalConfig,
)
from cvc.operations.engine import CVCEngine

logger = logging.getLogger("cvc.agent")

# Auto-commit every N assistant turns
AUTO_COMMIT_INTERVAL = int(os.environ.get("CVC_AGENT_AUTO_COMMIT", "5"))
MAX_TOOL_ITERATIONS = 25  # Safety limit for tool loops


class AgentSession:
    """
    Manages a single interactive coding session.

    Holds the conversation history, CVC engine, tool executor,
    and LLM client. Handles the agentic loop including tool calling.
    """

    def __init__(
        self,
        workspace: Path,
        config: CVCConfig,
        engine: CVCEngine,
        db: ContextDatabase,
        llm: AgentLLM,
    ) -> None:
        self.workspace = workspace
        self.config = config
        self.engine = engine
        self.db = db
        self.llm = llm
        self.executor = ToolExecutor(workspace, engine)

        # Conversation history (OpenAI format for portability)
        self.messages: list[dict[str, Any]] = []

        # Session tracking
        self.turn_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self._assistant_turns_since_commit = 0

        # Build and set the system prompt
        system_prompt = build_system_prompt(
            workspace=workspace,
            provider=config.provider,
            model=config.model,
            branch=engine.active_branch,
            agent_id=config.agent_id,
        )
        self.messages.append({"role": "system", "content": system_prompt})

        # Load existing CVC context if available
        self._load_existing_context()

    def _load_existing_context(self) -> None:
        """
        If there's existing context in the CVC engine (from a previous session),
        inject it as context-setting messages so the agent has memory.
        """
        existing = self.engine.context_window
        if existing and len(existing) > 0:
            # Add a context restoration notice
            summary_parts = []
            for msg in existing[-10:]:  # Last 10 messages as context
                if msg.role in ("user", "assistant") and msg.content:
                    preview = msg.content[:200]
                    summary_parts.append(f"[{msg.role}]: {preview}")

            if summary_parts:
                context_summary = "\n".join(summary_parts)
                self.messages.append({
                    "role": "system",
                    "content": (
                        "[CVC Time Machine] Previous session context restored. "
                        f"Here's a summary of the recent conversation:\n\n{context_summary}\n\n"
                        "Continue from where you left off."
                    ),
                })

    async def run_turn(self, user_input: str) -> None:
        """
        Process one user turn through the agentic loop.

        This may involve multiple LLM calls if the model uses tools.
        """
        self.turn_count += 1

        # Add user message
        self.messages.append({"role": "user", "content": user_input})

        # Push to CVC context
        self.engine.push_message(ContextMessage(role="user", content=user_input))

        # Agentic loop
        iterations = 0
        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1

            render_thinking()

            try:
                response = await self.llm.chat(
                    messages=self.messages,
                    tools=AGENT_TOOLS,
                    temperature=0.7,
                    max_tokens=8192,
                )
            except Exception as exc:
                render_error(f"LLM error: {exc}")
                logger.error("LLM call failed: %s", exc, exc_info=True)
                # Remove the failed state
                break

            self.total_prompt_tokens += response.prompt_tokens
            self.total_completion_tokens += response.completion_tokens

            if response.has_tool_calls:
                # Add assistant message with tool calls to history
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.text or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }

                # Preserve raw Gemini parts (includes thoughtSignature
                # required by Gemini 3 for multi-turn function calling).
                gemini_parts = response._provider_meta.get("gemini_parts")
                if gemini_parts:
                    assistant_msg["_gemini_parts"] = gemini_parts

                self.messages.append(assistant_msg)

                # Show any text the model produced before tool calls
                if response.text:
                    render_markdown_response(response.text)

                # Execute each tool call
                for tc in response.tool_calls:
                    args_summary = ", ".join(
                        f"{k}={repr(v)[:30]}" for k, v in list(tc.arguments.items())[:3]
                    )
                    render_tool_call_start(tc.name, args_summary)

                    start_time = time.time()
                    try:
                        result = self.executor.execute(tc.name, tc.arguments)
                        elapsed = time.time() - start_time
                        render_tool_call_result(tc.name, result, elapsed)
                    except Exception as exc:
                        result = f"Error: {exc}"
                        render_tool_error(tc.name, str(exc))

                    # Add tool result to conversation
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result,
                    })

                # Continue the loop — the model needs to process tool results
                continue

            else:
                # No tool calls — this is a final text response
                if response.text:
                    render_markdown_response(response.text)

                    # Add to conversation history
                    self.messages.append({
                        "role": "assistant",
                        "content": response.text,
                    })

                    # Push to CVC context
                    self.engine.push_message(
                        ContextMessage(role="assistant", content=response.text)
                    )

                # Show token usage
                render_token_usage(
                    response.prompt_tokens,
                    response.completion_tokens,
                    response.cache_read_tokens,
                )

                break  # Done with this turn

        # Auto-commit check
        self._assistant_turns_since_commit += 1
        if self._assistant_turns_since_commit >= AUTO_COMMIT_INTERVAL:
            self._auto_commit()

    def _auto_commit(self) -> None:
        """Auto-commit the current context as a checkpoint."""
        msg = f"Auto-checkpoint at turn {self.turn_count}"
        result = self.engine.commit(CVCCommitRequest(message=msg))
        if result.success:
            render_auto_commit(msg, result.commit_hash or "")
            self._assistant_turns_since_commit = 0

    def handle_slash_command(self, command: str) -> bool:
        """
        Handle a slash command. Returns True if the command was handled,
        False if we should exit.
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit", "/q"):
            # Final commit before exit
            if self._assistant_turns_since_commit > 0:
                msg = f"Session end at turn {self.turn_count}"
                result = self.engine.commit(CVCCommitRequest(message=msg))
                if result.success:
                    render_success(f"Final commit: {result.commit_hash[:12]}")
            return False

        elif cmd == "/help":
            print_help()

        elif cmd == "/status":
            render_status(
                self.engine.active_branch,
                self.engine.head_hash or "(none)",
                len(self.engine.context_window),
                self.config.provider,
                self.config.model,
            )

        elif cmd == "/log":
            entries = self.engine.log(limit=20)
            if entries:
                console.print()
                for e in entries:
                    console.print(
                        f"  [{THEME['hash']}]{e['short']}[/{THEME['hash']}]  "
                        f"[{THEME['text_dim']}]{e['type']}[/{THEME['text_dim']}]  "
                        f"{e['message'][:60]}"
                    )
                console.print()
            else:
                render_info("No commits yet.")

        elif cmd == "/commit":
            msg = arg or f"Manual checkpoint at turn {self.turn_count}"
            result = self.engine.commit(CVCCommitRequest(message=msg))
            if result.success:
                render_success(f"Committed: {result.commit_hash[:12]} — {msg}")
                self._assistant_turns_since_commit = 0
            else:
                render_error(result.message)

        elif cmd == "/branch":
            if not arg:
                render_error("Usage: /branch <name>")
            else:
                from cvc.core.models import CVCBranchRequest
                result = self.engine.branch(CVCBranchRequest(name=arg))
                if result.success:
                    render_success(f"Switched to branch '{arg}'")
                    # Update system prompt with new branch
                    self.messages[0]["content"] = build_system_prompt(
                        workspace=self.workspace,
                        provider=self.config.provider,
                        model=self.config.model,
                        branch=self.engine.active_branch,
                        agent_id=self.config.agent_id,
                    )
                else:
                    render_error(result.message)

        elif cmd == "/restore":
            if not arg:
                render_error("Usage: /restore <commit_hash>")
            else:
                from cvc.core.models import CVCRestoreRequest
                result = self.engine.restore(CVCRestoreRequest(commit_hash=arg))
                if result.success:
                    render_success(f"Restored to {arg[:12]}")
                    # Inject context restoration message
                    self.messages.append({
                        "role": "system",
                        "content": (
                            f"[CVC] Context has been restored to commit {arg[:12]}. "
                            "You now have the conversation state from that point in time."
                        ),
                    })
                else:
                    render_error(result.message)

        elif cmd == "/search":
            if not arg:
                render_error("Usage: /search <query>")
            else:
                result = self.executor.execute("cvc_search", {"query": arg})
                console.print()
                for line in result.split("\n"):
                    console.print(f"  [{THEME['text']}]{line}[/{THEME['text']}]")
                console.print()

        elif cmd == "/clear":
            # Keep system prompt, clear everything else
            self.messages = [self.messages[0]]
            self.turn_count = 0
            render_success("Conversation cleared. CVC state preserved.")

        elif cmd == "/compact":
            # Compact the conversation by summarizing
            msg_count = len(self.messages)
            if msg_count <= 3:
                render_info("Conversation too short to compact.")
            else:
                # Keep system prompt, first user message, and last 6 messages
                keep_start = self.messages[:1]
                keep_end = self.messages[-6:]
                removed = msg_count - len(keep_start) - len(keep_end)
                self.messages = keep_start + [{
                    "role": "system",
                    "content": f"[CVC] Conversation compacted. {removed} earlier messages summarized. Recent context preserved.",
                }] + keep_end
                render_success(f"Compacted: removed {removed} messages, keeping recent context.")

        elif cmd == "/model":
            if arg:
                self.config.model = arg
                self.llm.model = arg
                render_success(f"Model changed to: {arg}")
            else:
                self._interactive_model_switch()

        elif cmd == "/provider":
            self._interactive_provider_switch()

        elif cmd == "/init":
            self._run_cvc_init()

        elif cmd == "/serve":
            self._start_proxy_background()

        else:
            render_error(f"Unknown command: {cmd}. Type /help for available commands.")

        return True

    # ── Interactive helpers ───────────────────────────────────────────────

    def _interactive_model_switch(self) -> None:
        """Show current model and let user pick a new one interactively."""
        from rich.table import Table
        from rich import box

        provider = self.config.provider
        current = self.config.model
        catalog = MODEL_CATALOG_AGENT.get(provider, [])

        console.print()
        render_info(f"Current model: [bold]{provider}[/bold] / [bold]{current}[/bold]")
        console.print()

        if not catalog:
            console.print(f"  [{THEME['text_dim']}]No model catalog for {provider}. "
                          f"Type [bold]/model <name>[/bold] to set manually.[/{THEME['text_dim']}]")
            return

        table = Table(
            box=box.ROUNDED,
            border_style=THEME["primary_dim"],
            show_header=True,
            header_style=f"bold {THEME['primary_bright']}",
        )
        table.add_column("#", style="bold", width=3)
        table.add_column("Model", style=THEME["accent"])
        table.add_column("Description", style=THEME["text"])
        table.add_column("Tier", style=THEME["text_dim"], justify="right")
        table.add_column("", width=3)

        for i, (mid, desc, tier) in enumerate(catalog, 1):
            marker = f"[{THEME['success']}]●[/{THEME['success']}]" if mid == current else " "
            table.add_row(str(i), mid, desc, tier, marker)

        console.print(table)
        console.print()

        try:
            choice = console.input(
                f"  [{THEME['primary_dim']}]Pick a model (number or name, Enter to keep current):[/{THEME['primary_dim']}] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return

        if not choice:
            render_info("Keeping current model.")
            return

        # Resolve the choice
        if choice.isdigit() and 1 <= int(choice) <= len(catalog):
            new_model = catalog[int(choice) - 1][0]
        else:
            new_model = choice

        self.config.model = new_model
        self.llm.model = new_model

        # Also save to global config so it persists
        try:
            from cvc.core.models import GlobalConfig
            gc = GlobalConfig.load()
            gc.model = new_model
            gc.save()
        except Exception:
            pass  # Non-critical

        render_success(f"Model switched to [bold]{new_model}[/bold]")

    def _interactive_provider_switch(self) -> None:
        """Let the user switch provider + model interactively."""
        providers = [
            ("anthropic", "Anthropic", "Claude Opus, Sonnet, Haiku"),
            ("openai", "OpenAI", "GPT-5.2, Codex, GPT-4.1"),
            ("google", "Google", "Gemini 2.5 Flash/Pro, Gemini 3"),
            ("ollama", "Ollama", "Local models — no API key"),
        ]

        console.print()
        render_info(f"Current provider: [bold]{self.config.provider}[/bold]")
        console.print()

        for i, (key, name, desc) in enumerate(providers, 1):
            marker = f"[{THEME['success']}]●[/{THEME['success']}]" if key == self.config.provider else " "
            console.print(
                f"  {marker} [{THEME['accent']}]{i}[/{THEME['accent']}]  "
                f"[bold]{name}[/bold]  [{THEME['text_dim']}]— {desc}[/{THEME['text_dim']}]"
            )
        console.print()

        try:
            choice = console.input(
                f"  [{THEME['primary_dim']}]Pick a provider (number, Enter to keep):[/{THEME['primary_dim']}] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return

        if not choice:
            render_info("Keeping current provider.")
            return

        if choice.isdigit() and 1 <= int(choice) <= len(providers):
            new_provider = providers[int(choice) - 1][0]
        else:
            new_provider = choice.lower()

        if new_provider not in MODEL_CATALOG_AGENT:
            render_error(f"Unknown provider: {new_provider}")
            return

        # Check for API key
        from cvc.core.models import GlobalConfig
        gc = GlobalConfig.load()
        key = gc.api_keys.get(new_provider, "")

        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": "",
        }
        env_key = env_map.get(new_provider, "")
        if env_key:
            key = key or os.getenv(env_key, "")

        if not key and new_provider != "ollama":
            render_error(
                f"No API key for {new_provider}. "
                f"Run [bold]cvc setup[/bold] to configure it first."
            )
            return

        # Switch provider — need new LLM client
        self.config.provider = new_provider
        self.llm.provider = new_provider
        self.llm.api_key = key

        # Update API URL
        base_url_map = {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com",
            "google": "https://generativelanguage.googleapis.com",
            "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        }
        self.llm._api_url = base_url_map.get(new_provider, "")

        render_success(f"Provider switched to [bold]{new_provider}[/bold]")

        # Now pick a model for the new provider
        self._interactive_model_switch()

        # Save
        try:
            gc.provider = new_provider
            gc.model = self.config.model
            gc.save()
        except Exception:
            pass

    def _run_cvc_init(self) -> None:
        """Initialize CVC in the current workspace."""
        cvc_dir = self.workspace / ".cvc"
        if cvc_dir.exists():
            render_info(f"CVC already initialized at [bold]{cvc_dir}[/bold]")
            return
        try:
            config = CVCConfig.for_project(
                project_root=self.workspace,
                provider=self.config.provider,
                model=self.config.model,
            )
            config.ensure_dirs()
            from cvc.core.database import ContextDatabase as DB
            DB(config)
            render_success(f"CVC initialized at [bold]{cvc_dir}[/bold]")
        except Exception as exc:
            render_error(f"Failed to initialize CVC: {exc}")

    def _start_proxy_background(self) -> None:
        """Start the CVC proxy server in a background process."""
        import subprocess as _sp
        import socket

        # Check if proxy is already running
        if self._is_proxy_running():
            render_info("CVC Proxy is already running on [bold]http://127.0.0.1:8000[/bold]")
            return

        try:
            if sys.platform == "win32":
                # On Windows, use START to open a new terminal window
                _sp.Popen(
                    ["cmd", "/c", "start", "CVC Proxy", "cvc", "serve"],
                    creationflags=_sp.CREATE_NEW_CONSOLE,
                )
            else:
                # On Unix, launch in background
                _sp.Popen(
                    ["cvc", "serve"],
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    start_new_session=True,
                )
            render_success("CVC Proxy starting in a new terminal window…")
            render_info("Connect your IDE to [bold]http://127.0.0.1:8000/v1[/bold]")
        except Exception as exc:
            render_error(f"Failed to start proxy: {exc}")
            render_info("Start it manually: [bold]cvc serve[/bold]")

    @staticmethod
    def _is_proxy_running(host: str = "127.0.0.1", port: int = 8000) -> bool:
        """Check if the CVC proxy is listening."""
        import socket
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            return False


async def _run_agent_async(
    workspace: Path,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> None:
    """Async implementation of the agent REPL."""
    # Load configuration
    gc = GlobalConfig.load()

    provider = provider or os.getenv("CVC_PROVIDER", gc.provider)
    model = model or os.getenv("CVC_MODEL", gc.model)

    # Resolve API key
    if not api_key:
        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": "",
        }
        env_key = env_map.get(provider, "")
        api_key = os.getenv(env_key, "") if env_key else ""
        if not api_key:
            api_key = gc.api_keys.get(provider, "")

    if not api_key and provider != "ollama":
        render_error(
            f"No API key found for {provider}. "
            "Run [bold]cvc setup[/bold] or set the environment variable."
        )
        return

    # Build CVC engine
    config = CVCConfig.for_project(
        project_root=workspace,
        provider=provider,
        model=model,
    )
    config.ensure_dirs()
    db = ContextDatabase(config)
    engine = CVCEngine(config, db)

    # Build LLM client
    base_url_map = {
        "anthropic": "https://api.anthropic.com",
        "openai": "https://api.openai.com",
        "google": "https://generativelanguage.googleapis.com",
        "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    }
    base_url = base_url_map.get(provider, "")

    llm = AgentLLM(
        provider=provider,
        api_key=api_key or "",
        model=model,
        base_url=base_url,
    )

    try:
        from cvc import __version__ as version
    except ImportError:
        version = "0.5.0"

    # Show banner
    agent_banner(
        version=version,
        provider=provider,
        model=model,
        branch=engine.active_branch,
        workspace=str(workspace),
    )

    # ── Smart onboarding: check CVC init & proxy status ──────────────────
    _smart_onboarding(workspace, config)

    # Create session
    session = AgentSession(
        workspace=workspace,
        config=config,
        engine=engine,
        db=db,
        llm=llm,
    )

    # REPL loop
    try:
        while True:
            try:
                user_input = print_input_prompt(
                    branch=engine.active_branch,
                    turn=session.turn_count + 1,
                )
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                should_continue = session.handle_slash_command(user_input)
                if not should_continue:
                    break
                continue

            # Run ordinary turn
            try:
                await session.run_turn(user_input)
            except KeyboardInterrupt:
                render_info("Interrupted. Type /exit to quit.")
                continue
            except Exception as exc:
                render_error(f"Unexpected error: {exc}")
                logger.error("Turn error: %s", exc, exc_info=True)
                continue

    finally:
        # Cleanup
        render_goodbye()
        await llm.close()
        db.close()


def _is_proxy_running_standalone(host: str = "127.0.0.1", port: int = 8000) -> bool:
    """Check if the CVC proxy is listening on the given port."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _smart_onboarding(workspace: Path, config: CVCConfig) -> None:
    """
    Run at agent startup to check readiness and offer to fix issues inline.

    Checks:
      1. Is CVC initialized in this workspace?
      2. Is the proxy running? (needed for IDE integration)
    """
    import subprocess as _sp

    cvc_dir = workspace / ".cvc"
    hints_shown = False

    # ── 1. CVC init check ────────────────────────────────────────────────
    if not cvc_dir.exists():
        console.print(
            f"  [{THEME['warning']}]![/{THEME['warning']}] "
            f"CVC is not initialized in this workspace."
        )
        console.print(
            f"  [{THEME['text_dim']}]Without init, time-travel features (commit, branch, restore) "
            f"won't persist.[/{THEME['text_dim']}]"
        )

        try:
            answer = console.input(
                f"  [{THEME['accent']}]Initialize CVC here now? (Y/n):[/{THEME['accent']}] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer in ("", "y", "yes"):
            try:
                config.ensure_dirs()
                from cvc.core.database import ContextDatabase as _DB
                _DB(config)
                render_success(f"CVC initialized at [bold]{cvc_dir}[/bold]")
            except Exception as exc:
                render_error(f"Failed to initialize: {exc}")
        else:
            render_info(
                "Skipped. You can run [bold]/init[/bold] anytime, or [bold]cvc init[/bold] from your shell."
            )
        console.print()
        hints_shown = True

    # ── 2. Proxy check ───────────────────────────────────────────────────
    if not _is_proxy_running_standalone():
        console.print(
            f"  [{THEME['text_dim']}]Tip: The CVC Proxy is not running. "
            f"Your IDE won't connect to CVC without it.[/{THEME['text_dim']}]"
        )

        try:
            answer = console.input(
                f"  [{THEME['accent']}]Start the proxy in a new terminal? (Y/n):[/{THEME['accent']}] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer in ("", "y", "yes"):
            try:
                if sys.platform == "win32":
                    _sp.Popen(
                        ["cmd", "/c", "start", "CVC Proxy", "cvc", "serve"],
                        creationflags=_sp.CREATE_NEW_CONSOLE,
                    )
                else:
                    _sp.Popen(
                        ["cvc", "serve"],
                        stdout=_sp.DEVNULL,
                        stderr=_sp.DEVNULL,
                        start_new_session=True,
                    )
                render_success("CVC Proxy starting in a new terminal…")
                render_info("IDE endpoint: [bold]http://127.0.0.1:8000/v1[/bold]")
            except Exception as exc:
                render_error(f"Failed to start proxy: {exc}")
                render_info("Start it manually: [bold]cvc serve[/bold]")
        else:
            render_info(
                "Skipped. Run [bold]/serve[/bold] anytime, or [bold]cvc serve[/bold] in another terminal."
            )
        console.print()
        hints_shown = True

    if not hints_shown:
        # Everything is ready — show a quick status line
        proxy_status = (
            f"[{THEME['success']}]●[/{THEME['success']}] Proxy running"
            if _is_proxy_running_standalone()
            else f"[{THEME['text_dim']}]○ Proxy off[/{THEME['text_dim']}]"
        )
        console.print(
            f"  [{THEME['success']}]●[/{THEME['success']}] CVC ready  "
            f"│  {proxy_status}  "
            f"│  [{THEME['text_dim']}]Type [bold]/help[/bold] for commands[/{THEME['text_dim']}]"
        )
        console.print()


def run_agent(
    workspace: Path | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> None:
    """
    Start the CVC Agent interactive REPL.

    This is the main entry point called by the CLI.
    """
    if workspace is None:
        workspace = Path.cwd()
    workspace = workspace.resolve()

    try:
        asyncio.run(_run_agent_async(workspace, provider, model, api_key))
    except KeyboardInterrupt:
        pass
