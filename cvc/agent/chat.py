"""
cvc.agent.chat — The main agentic REPL loop.

This is the heart of the CVC Agent — a Claude Code-style interactive
coding assistant that runs in your terminal with Time Machine capabilities.

The loop:
  1. Accept user input (or slash command)
  2. Add to conversation history
  3. Send to LLM with tool definitions
  4. If LLM returns tool calls → execute each, send results back → goto 3
  5. If LLM returns text → stream and wait for next input
  6. Auto-commit at configurable intervals
  7. Push all messages to CVC context window

Features (v0.9):
  - Token-by-token streaming responses
  - Multi-file auto-context on startup
  - Diff-based editing with fuzzy matching
  - Automatic error recovery / retry loop
  - /undo command for file changes
  - Per-session cost tracking
  - Image/screenshot support
  - Persistent memory across sessions
  - Parallel tool execution
  - Tab completion for slash commands
  - .cvcignore file support
  - Session resume
  - /web command for web search
  - Git integration
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any

from cvc.agent.context_autopilot import ContextAutopilot, AutopilotConfig
from cvc.agent.cost_tracker import CostTracker
from cvc.agent.executor import ToolExecutor
from cvc.agent.llm import AgentLLM, StreamEvent
from cvc.agent.renderer import (
    StreamingRenderer,
    agent_banner,
    console,
    get_input_with_completion,
    get_pending_paste_images,
    print_help,
    print_input_prompt,
    render_auto_commit,
    render_autopilot_action,
    render_autopilot_diagnostics,
    render_context_health,
    render_cost_summary,
    render_error,
    render_git_startup_info,
    render_git_status,
    render_goodbye,
    render_info,
    render_markdown_response,
    render_memory,
    render_session_resume_prompt,
    render_status,
    render_success,
    render_thinking,
    render_token_usage,
    render_tool_call_result,
    render_tool_call_start,
    render_tool_error,
    render_undo_result,
    render_web_results,
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

# Auto-commit every N assistant turns (CLI optimized for automatic persistence)
AUTO_COMMIT_INTERVAL = int(os.environ.get("CVC_AGENT_AUTO_COMMIT", "2"))  # Changed from 5 to 2 for aggressive auto-save
MAX_TOOL_ITERATIONS = 25  # Safety limit for tool loops
MAX_RETRY_ATTEMPTS = 2    # Retry failed tool calls


# ---------------------------------------------------------------------------
# Human-readable argument formatting for each tool type
# ---------------------------------------------------------------------------

def _humanize_tool_args(tool_name: str, args: dict[str, Any]) -> str:
    """
    Turn raw tool arguments into a concise, human-readable description.

    Instead of  grep(pattern='mode', path='src/')
    Shows       'mode' in src/
    """
    def _short(val: Any, limit: int = 40) -> str:
        s = str(val)
        return s if len(s) <= limit else s[:limit - 1] + "…"

    def _basename(path: str) -> str:
        """Short basename or last 2 path components."""
        p = Path(path)
        parts = p.parts
        if len(parts) <= 2:
            return str(p)
        return str(Path(*parts[-2:]))

    try:
        if tool_name == "read_file":
            path = args.get("path", "")
            return _basename(path)

        elif tool_name == "write_file":
            path = args.get("path", "")
            return _basename(path)

        elif tool_name == "edit_file":
            path = args.get("path", "")
            return _basename(path)

        elif tool_name == "patch_file":
            path = args.get("path", "")
            return _basename(path)

        elif tool_name == "bash":
            cmd = args.get("command", "")
            return f"`{_short(cmd, 50)}`"

        elif tool_name == "glob":
            pattern = args.get("pattern", "")
            path = args.get("path", ".")
            if path and path != ".":
                return f"'{pattern}' in {_basename(path)}"
            return f"'{pattern}'"

        elif tool_name == "grep":
            pattern = args.get("pattern", "")
            path = args.get("path", "")
            if path:
                return f"'{_short(pattern, 30)}' in {_basename(path)}"
            return f"'{_short(pattern, 40)}'"

        elif tool_name == "list_dir":
            path = args.get("path", ".")
            return _basename(path)

        elif tool_name == "web_search":
            query = args.get("query", "")
            return f"'{_short(query, 50)}'"

        elif tool_name == "cvc_commit":
            msg = args.get("message", "")
            return f"'{_short(msg, 40)}'"

        elif tool_name == "cvc_branch":
            name = args.get("name", "")
            return name

        elif tool_name == "cvc_restore":
            ref = args.get("ref", args.get("commit", ""))
            return _short(str(ref), 20)

        elif tool_name == "cvc_merge":
            src = args.get("source", args.get("branch", ""))
            return src

        elif tool_name == "cvc_search":
            query = args.get("query", "")
            return f"'{_short(query, 40)}'"

        elif tool_name == "cvc_diff":
            return ""

        elif tool_name in ("cvc_status", "cvc_log"):
            return ""

        # Fallback: show first arg value only
        if args:
            first_val = next(iter(args.values()))
            return _short(first_val, 40)
        return ""
    except Exception:
        return ""


def _grab_clipboard_images() -> list[tuple[str, str]]:
    """
    Grab image(s) from the system clipboard.

    Returns a list of (base64_data, mime_type) tuples.
    Uses Pillow (PIL) if available, falls back to native Windows API via ctypes.
    Returns an empty list if no image is in the clipboard.
    """
    images: list[tuple[str, str]] = []

    # Try Pillow first (cross-platform)
    try:
        from PIL import ImageGrab
        import io

        img = ImageGrab.grabclipboard()
        if img is not None:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            images.append((b64, "image/png"))
            return images
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: Windows native clipboard via ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            CF_DIB = 8
            GHND = 0x0042

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            if not user32.OpenClipboard(0):
                return images

            try:
                if not user32.IsClipboardFormatAvailable(CF_DIB):
                    return images

                h_data = user32.GetClipboardData(CF_DIB)
                if not h_data:
                    return images

                kernel32.GlobalLock.restype = ctypes.c_void_p
                ptr = kernel32.GlobalLock(h_data)
                if not ptr:
                    return images

                try:
                    size = kernel32.GlobalSize(h_data)
                    dib_data = ctypes.string_at(ptr, size)

                    # Convert DIB to BMP by prepending BMP file header
                    # BMP header: 'BM' + file_size(4) + reserved(4) + offset(4) = 14 bytes
                    import struct
                    bmp_file_size = 14 + len(dib_data)
                    # offset to pixel data: 14 (file header) + BITMAPINFOHEADER size
                    bih_size = struct.unpack_from("<I", dib_data, 0)[0]
                    # Simple approach: bits_per_pixel at offset 14 in DIB
                    bits_pp = struct.unpack_from("<H", dib_data, 14)[0] if bih_size >= 16 else 24
                    # Color table size
                    if bits_pp <= 8:
                        clr_used = struct.unpack_from("<I", dib_data, 32)[0] if bih_size >= 36 else 0
                        color_table = (clr_used or (1 << bits_pp)) * 4
                    else:
                        color_table = 0
                    offset = 14 + bih_size + color_table

                    bmp_header = struct.pack("<2sIHHI", b"BM", bmp_file_size, 0, 0, offset)
                    bmp_data = bmp_header + dib_data

                    # Convert BMP to PNG via PIL if available, else use raw BMP
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(bmp_data))
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                        images.append((b64, "image/png"))
                    except ImportError:
                        # Send as BMP
                        b64 = base64.b64encode(bmp_data).decode("utf-8")
                        images.append((b64, "image/bmp"))

                finally:
                    kernel32.GlobalUnlock(h_data)
            finally:
                user32.CloseClipboard()

        except Exception as e:
            logger.debug("Clipboard image grab failed: %s", e)

    return images


def _build_image_message(
    messages: list[dict[str, Any]],
    provider: str,
    b64_data: str,
    mime_type: str,
    text: str,
) -> None:
    """Append a multimodal user message with an image to the conversation."""
    if provider == "anthropic":
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_data,
                    },
                },
                {"type": "text", "text": text},
            ],
        })
    elif provider == "openai":
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}",
                    },
                },
                {"type": "text", "text": text},
            ],
        })
    else:
        # Google and others use the Anthropic-style format
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_data,
                    },
                },
                {"type": "text", "text": text},
            ],
        })


class AgentSession:
    """
    Manages a single interactive coding session.

    Holds the conversation history, CVC engine, tool executor,
    and LLM client. Handles the agentic loop including tool calling,
    streaming, cost tracking, and error recovery.
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
        self.cost_tracker = CostTracker(model=config.model)

        # Conversation history (OpenAI format for portability)
        self.messages: list[dict[str, Any]] = []

        # Session tracking
        self.turn_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self._assistant_turns_since_commit = 0

        # Clipboard image dedup — track hash of the last clipboard image
        # we attached so we don't re-send the same screenshot on every prompt
        self._last_clipboard_hash: str | None = None

        # Context Autopilot — self-healing context engine
        self.autopilot = ContextAutopilot(
            model=config.model,
            config=AutopilotConfig(
                enabled=os.environ.get("CVC_AUTOPILOT", "1") != "0",
            ),
        )
        self._health_bar: str = ""  # Cached health bar for the prompt

        # Build auto-context
        auto_ctx = ""
        memory_ctx = ""
        git_ctx = ""
        try:
            from cvc.agent.auto_context import build_auto_context
            auto_ctx = build_auto_context(workspace)
        except Exception as e:
            logger.debug("Auto-context failed: %s", e)

        try:
            from cvc.agent.memory import build_memory_context
            memory_ctx = build_memory_context(str(workspace))
        except Exception as e:
            logger.debug("Memory context failed: %s", e)

        try:
            from cvc.agent.git_integration import git_status, format_git_status
            gs = git_status(workspace)
            if gs.get("is_git"):
                git_ctx = format_git_status(gs)
        except Exception as e:
            logger.debug("Git context failed: %s", e)

        # Build and set the system prompt
        system_prompt = build_system_prompt(
            workspace=workspace,
            provider=config.provider,
            model=config.model,
            branch=engine.active_branch,
            agent_id=config.agent_id,
            auto_context=auto_ctx,
            memory_context=memory_ctx,
            git_context=git_ctx,
        )
        self.messages.append({"role": "system", "content": system_prompt})

        # Load existing CVC context if available
        self._load_existing_context()

    def _load_existing_context(self) -> None:
        """
        If there's existing context in the CVC engine (from a previous session
        or from a cross-mode restore — e.g. MCP / Proxy → CLI), inject the
        full conversation history into the LLM message list so the agent has
        complete memory of everything that was discussed.

        This is the core feature of CVC: every message ever exchanged in this
        directory — regardless of provider, model, or mode — is preserved and
        restored automatically.
        """
        existing = self.engine.context_window
        if not existing:
            return

        # Only restore user/assistant messages.
        # Tool messages CANNOT be restored as role="tool" because the
        # preceding assistant message lacks the structured tool_calls
        # field (CVC stores it as plain text like "[Tool calls: ...]").
        # Injecting orphan tool results breaks Gemini (functionResponse
        # without functionCall) and Anthropic (tool_result without
        # tool_use), causing 0 output tokens or API errors.
        # Tool result info is already captured in the assistant message
        # summaries anyway, so no context is lost.
        conversation_msgs = [
            m for m in existing
            if m.role in ("user", "assistant")
        ]

        if not conversation_msgs:
            return

        # For large histories, inject a summary of older messages
        # and the full recent messages to stay within token limits
        MAX_FULL_MESSAGES = 40  # Keep last N messages in full

        if len(conversation_msgs) > MAX_FULL_MESSAGES:
            # Summarize older messages
            older = conversation_msgs[:-MAX_FULL_MESSAGES]
            recent = conversation_msgs[-MAX_FULL_MESSAGES:]

            summary_parts = []
            for msg in older:
                if msg.role in ("user", "assistant") and msg.content:
                    preview = msg.content[:150].replace("\n", " ")
                    summary_parts.append(f"[{msg.role}]: {preview}")

            if summary_parts:
                # Limit summary to avoid token explosion
                summary_text = "\n".join(summary_parts[-30:])
                self.messages.append({
                    "role": "system",
                    "content": (
                        f"[CVC Time Machine] Previous session restored. "
                        f"{len(existing)} total messages in context history.\n"
                        f"Summary of older conversation ({len(older)} messages):\n\n"
                        f"{summary_text}\n\n"
                        f"Full recent conversation follows."
                    ),
                })

            # Inject recent messages as actual conversation turns
            for msg in recent:
                self.messages.append({"role": msg.role, "content": msg.content})
        else:
            # Small enough to inject everything
            self.messages.append({
                "role": "system",
                "content": (
                    f"[CVC Time Machine] Previous session restored. "
                    f"{len(existing)} messages in context history. "
                    f"Full conversation follows."
                ),
            })
            for msg in conversation_msgs:
                self.messages.append({"role": msg.role, "content": msg.content})

    async def run_turn(self, user_input: str) -> None:
        """
        Process one user turn through the agentic loop.

        This may involve multiple LLM calls if the model uses tools.
        Uses streaming for text responses and parallel execution for
        multiple tool calls.
        """
        self.turn_count += 1

        # Add user message
        self.messages.append({"role": "user", "content": user_input})

        # Push to CVC context
        self.engine.push_message(ContextMessage(role="user", content=user_input))

        await self._agentic_loop()

    async def run_turn_no_append(self, user_input: str) -> None:
        """
        Like run_turn but does NOT append the user message (already added,
        e.g. with image data attached). Still increments turn count and
        pushes a text summary to CVC context.
        """
        self.turn_count += 1

        # Push plain text to CVC context (image data not stored)
        self.engine.push_message(ContextMessage(role="user", content=user_input))

        await self._agentic_loop()

    async def _agentic_loop(self) -> None:
        """Core agentic loop — streams LLM responses, handles tool calls."""
        # Agentic loop
        iterations = 0
        _empty_retries = 0  # Track retries for empty responses
        _MAX_EMPTY_RETRIES = 1
        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1

            render_thinking()

            try:
                # Use streaming for the response
                response_text = ""
                tool_calls = []
                prompt_tokens = 0
                completion_tokens = 0
                cache_read_tokens = 0
                gemini_parts = None
                finish_reason = ""

                streamer = StreamingRenderer()
                streaming_started = False

                # Use higher max_tokens for post-tool-call iterations
                # because the model needs room for thinking + analysis
                max_tok = 16384 if iterations > 1 else 8192

                async for event in self.llm.chat_stream(
                    messages=self.messages,
                    tools=AGENT_TOOLS,
                    temperature=0.7,
                    max_tokens=max_tok,
                ):
                    if event.type == "text_delta":
                        if not streaming_started:
                            streamer.start()
                            streaming_started = True
                        streamer.add_text(event.text)
                        response_text += event.text

                    elif event.type == "tool_call_start":
                        if streaming_started:
                            streamer.finish()
                            streaming_started = False
                        if event.tool_call:
                            tool_calls.append(event.tool_call)

                    elif event.type == "done":
                        prompt_tokens = event.prompt_tokens
                        completion_tokens = event.completion_tokens
                        cache_read_tokens = event.cache_read_tokens
                        finish_reason = event._provider_meta.get("finish_reason", "")
                        if event._provider_meta.get("gemini_parts"):
                            gemini_parts = event._provider_meta["gemini_parts"]

                if streaming_started:
                    response_text = streamer.finish()

            except Exception as exc:
                # Show clean error to user (no traceback)
                error_msg = str(exc)
                # Extract just the first meaningful line for display
                first_line = error_msg.split('\n')[0]
                render_error(first_line)
                logger.debug("LLM call failed: %s", exc, exc_info=True)

                # Auto-retry on transient errors
                if iterations == 1 and ("timeout" in str(exc).lower() or "connection" in str(exc).lower()):
                    render_info("Retrying...")
                    await asyncio.sleep(1)
                    continue
                break

            # Track costs
            turn_cost = self.cost_tracker.add_usage(
                prompt_tokens, completion_tokens, cache_read_tokens
            )
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens

            if tool_calls:
                # Add assistant message with tool calls to history
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response_text or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in tool_calls
                    ],
                }

                # Store raw Gemini parts — preserves thoughtSignature for Gemini 3
                if gemini_parts:
                    assistant_msg["_gemini_parts"] = gemini_parts

                self.messages.append(assistant_msg)

                # ── Push assistant tool-call message to CVC context ──
                tool_summary = ", ".join(tc.name for tc in tool_calls)
                self.engine.push_message(
                    ContextMessage(
                        role="assistant",
                        content=(
                            (response_text + "\n\n" if response_text else "")
                            + f"[Tool calls: {tool_summary}]"
                        ),
                    )
                )

                # Show any text the model produced before tool calls
                if response_text and not streamer.is_active():
                    render_markdown_response(response_text)

                # Execute tool calls — parallel when possible
                tool_results = await self._execute_tools_parallel(tool_calls)

                for tc, result in zip(tool_calls, tool_results):
                    # Truncate tool results for the LLM context to prevent
                    # overwhelming the model (especially Gemini thinking models
                    # which can exhaust output budgets on massive inputs).
                    # CVC storage uses a separate, smaller limit.
                    llm_result = result[:15000] if len(result) > 15000 else result
                    if len(result) > 15000:
                        llm_result += f"\n\n... (truncated, {len(result) - 15000:,} chars omitted for LLM)"

                    # Add tool result to conversation
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": llm_result,
                    })

                    # ── Push tool result to CVC context ──
                    # Truncate very large tool outputs for storage
                    stored_result = result[:4000] if len(result) > 4000 else result
                    self.engine.push_message(
                        ContextMessage(
                            role="tool",
                            content=f"[{tc.name}] {stored_result}",
                            name=tc.name,
                            tool_call_id=tc.id,
                        )
                    )

                    # Auto-read files from error messages
                    if result.startswith("Error:"):
                        await self._auto_context_from_error(result)

                # Continue the loop — the model needs to process tool results
                continue

            else:
                # No tool calls — this is a final text response

                # ── Empty response detection & retry ──
                # If the model returned 0 output tokens (common with Gemini
                # thinking models exhausting their budget), retry once with
                # a higher token limit before giving up.
                if not response_text and not tool_calls and _empty_retries < _MAX_EMPTY_RETRIES:
                    _empty_retries += 1
                    # Silent retry — don't alarm the user
                    logger.debug(
                        "Empty response from LLM (finish_reason=%s), retrying (%d/%d)",
                        finish_reason or "unknown", _empty_retries, _MAX_EMPTY_RETRIES,
                    )
                    continue

                if response_text:
                    # Already rendered via streaming above
                    # Add to conversation history
                    self.messages.append({
                        "role": "assistant",
                        "content": response_text,
                    })

                    # Push to CVC context
                    self.engine.push_message(
                        ContextMessage(role="assistant", content=response_text)
                    )

                # Show token usage with cost
                render_token_usage(
                    prompt_tokens,
                    completion_tokens,
                    cache_read_tokens,
                    turn_cost,
                    self.cost_tracker.total_cost_usd,
                )

                break  # Done with this turn

        # Auto-commit check
        self._assistant_turns_since_commit += 1
        if self._assistant_turns_since_commit >= AUTO_COMMIT_INTERVAL:
            self._auto_commit()

        # ── Context Autopilot: self-healing context management ───────────
        # Runs after every turn. Monitors context health and takes
        # graduated actions (thin → compact → aggressive compact) based
        # on utilization thresholds. CVC commits before any compaction
        # so nothing is ever lost.
        self.messages, health = self.autopilot.run(
            self.messages, engine=self.engine
        )

        # Show autopilot actions if any were taken
        if health.actions_taken:
            render_autopilot_action(health.actions_taken)

        # Cache the health bar for the input prompt
        self._health_bar = health.format_bar_rich(width=15)

    async def _execute_tools_parallel(self, tool_calls: list) -> list[str]:
        """
        Execute tool calls — in parallel when there are multiple independent
        read-only operations, sequentially otherwise.
        """
        if len(tool_calls) <= 1:
            # Single tool call — execute directly
            results = []
            for tc in tool_calls:
                result = await self._execute_single_tool(tc)
                results.append(result)
            return results

        # Check if all tool calls are read-only (safe for parallel execution)
        read_only_tools = {"read_file", "glob", "grep", "list_dir", "cvc_status",
                          "cvc_log", "cvc_search", "cvc_diff", "web_search"}
        all_read_only = all(tc.name in read_only_tools for tc in tool_calls)

        if all_read_only:
            # Execute in parallel using asyncio
            tasks = [self._execute_single_tool(tc) for tc in tool_calls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [
                str(r) if isinstance(r, Exception) else r
                for r in results
            ]
        else:
            # Execute sequentially for safety
            results = []
            for tc in tool_calls:
                result = await self._execute_single_tool(tc)
                results.append(result)
            return results

    async def _execute_single_tool(self, tc) -> str:
        """Execute a single tool call with error recovery."""
        args_summary = _humanize_tool_args(tc.name, tc.arguments)
        render_tool_call_start(tc.name, args_summary)

        start_time = time.time()
        retry_count = 0
        result = ""

        while retry_count <= MAX_RETRY_ATTEMPTS:
            try:
                result = self.executor.execute(tc.name, tc.arguments)
                elapsed = time.time() - start_time

                # Check if the result indicates a recoverable error
                if result.startswith("Error:") and retry_count < MAX_RETRY_ATTEMPTS:
                    if tc.name == "edit_file" and "not found in" in result:
                        # Re-read the file and update the arguments for retry
                        render_tool_error(tc.name, f"Retrying with fuzzy match... ({result[:80]})")
                        retry_count += 1
                        # The fuzzy matching is already built in, so if it failed
                        # with fuzzy matching too, don't retry
                        break
                    elif "File not found" in result:
                        render_tool_error(tc.name, f"File not found, cannot retry")
                        break
                    else:
                        # Generic error — don't retry
                        break

                render_tool_call_result(tc.name, result, elapsed)
                break

            except Exception as exc:
                retry_count += 1
                if retry_count <= MAX_RETRY_ATTEMPTS:
                    render_tool_error(tc.name, f"Retrying ({retry_count}/{MAX_RETRY_ATTEMPTS}): {exc}")
                    await asyncio.sleep(0.5)
                else:
                    result = f"Error: {exc}"
                    render_tool_error(tc.name, str(exc))

        return result

    async def _auto_context_from_error(self, error_text: str) -> None:
        """Auto-read files mentioned in error messages."""
        try:
            from cvc.agent.auto_context import extract_files_from_error
            files = extract_files_from_error(error_text, self.workspace)
            for fpath in files[:3]:  # Limit to 3 files
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    rel = fpath.relative_to(self.workspace) if fpath.is_relative_to(self.workspace) else fpath
                    # Inject as a system hint (don't pollute conversation)
                    self.messages.append({
                        "role": "system",
                        "content": (
                            f"[Auto-context] File mentioned in error: {rel}\n"
                            f"Content (first 2000 chars):\n{content[:2000]}"
                        ),
                    })
                except OSError:
                    pass
        except Exception:
            pass

    def _auto_commit(self) -> None:
        """Auto-commit the current context as a checkpoint."""
        msg = f"Auto-checkpoint at turn {self.turn_count}"
        result = self.engine.commit(CVCCommitRequest(message=msg))
        if result.success:
            render_auto_commit(msg, result.commit_hash or "")
            self._assistant_turns_since_commit = 0

    async def handle_slash_command(self, command: str) -> bool:
        """
        Handle a slash command. Returns True if the command was handled,
        False if we should exit.
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit", "/q"):
            # Save session memory before exit
            self._save_session_memory()
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
                    self._rebuild_system_prompt()
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
            self.messages = [self.messages[0]]
            self.turn_count = 0
            render_success("Conversation cleared. CVC state preserved.")

        elif cmd == "/compact":
            msg_count = len(self.messages)
            if msg_count <= 3:
                render_info("Conversation too short to compact.")
            else:
                keep_start = self.messages[:1]
                keep_end = self.messages[-6:]
                removed = msg_count - len(keep_start) - len(keep_end)
                self.messages = keep_start + [{
                    "role": "system",
                    "content": f"[CVC] Conversation compacted. {removed} earlier messages summarized. Recent context preserved.",
                }] + keep_end
                render_success(f"Compacted: removed {removed} messages, keeping recent context.")

        elif cmd == "/health":
            # Context Autopilot health dashboard
            health = self.autopilot.assess_health(self.messages)
            render_context_health(health)
            if arg and arg.lower() in ("verbose", "v", "diag", "diagnostics"):
                render_autopilot_diagnostics(self.autopilot.get_diagnostics())

        elif cmd == "/model":
            if arg:
                self.config.model = arg
                self.llm.model = arg
                self.cost_tracker.model = arg
                self.autopilot.update_model(arg)
                render_success(f"Model changed to: {arg}")
            else:
                self._interactive_model_switch()

        elif cmd == "/provider":
            self._interactive_provider_switch()

        elif cmd == "/init":
            self._run_cvc_init()

        elif cmd == "/serve":
            self._start_proxy_background()

        # ── New commands ─────────────────────────────────────────────────

        elif cmd == "/undo":
            result = self.executor.undo_last()
            render_undo_result(result)

        elif cmd == "/cost":
            summary = self.cost_tracker.format_summary()
            render_cost_summary(summary)

        elif cmd == "/analytics":
            self._handle_analytics_command()

        elif cmd == "/web":
            if not arg:
                render_error("Usage: /web <search query>")
            else:
                await self._handle_web_search(arg)

        elif cmd == "/checkout":
            if not arg:
                render_error("Usage: /checkout <branch_name>")
            else:
                self._handle_checkout_command(arg)

        elif cmd == "/branches":
            self._handle_branches_command()

        elif cmd == "/merge":
            if not arg:
                render_error("Usage: /merge <source_branch>")
            else:
                self._handle_merge_command(arg)

        elif cmd == "/git":
            self._handle_git_command(arg)

        elif cmd == "/image":
            if not arg:
                render_error("Usage: /image <file_path> [prompt text]")
            else:
                await self._handle_image(arg)

        elif cmd == "/paste":
            await self._handle_paste(arg)

        elif cmd == "/memory":
            self._handle_memory()

        elif cmd == "/files":
            self._handle_files_command(arg)

        elif cmd == "/summary":
            self._handle_summary_command()

        elif cmd == "/diff":
            self._handle_diff_command(arg)

        elif cmd == "/continue":
            self._handle_continue_command()

        else:
            render_error(f"Unknown command: {cmd}. Type /help for available commands.")

        return True

    def _rebuild_system_prompt(self) -> None:
        """Rebuild the system prompt (e.g., after branch switch)."""
        auto_ctx = ""
        try:
            from cvc.agent.auto_context import build_auto_context
            auto_ctx = build_auto_context(self.workspace)
        except Exception:
            pass

        self.messages[0]["content"] = build_system_prompt(
            workspace=self.workspace,
            provider=self.config.provider,
            model=self.config.model,
            branch=self.engine.active_branch,
            agent_id=self.config.agent_id,
            auto_context=auto_ctx,
        )

    async def _handle_web_search(self, query: str) -> None:
        """Run a web search and display results."""
        render_info(f"Searching the web for: {query}")
        try:
            from cvc.agent.web_search import web_search, format_search_results
            results = await web_search(query)
            text = format_search_results(results, query)
            render_web_results(text)
        except Exception as e:
            render_error(f"Web search failed: {e}")

    def _handle_git_command(self, arg: str) -> None:
        """Handle /git subcommands."""
        from cvc.agent.git_integration import (
            git_status,
            format_git_status,
            git_commit,
            git_log,
            git_diff_summary,
        )

        sub_parts = arg.strip().split(maxsplit=1) if arg else []
        sub_cmd = sub_parts[0].lower() if sub_parts else ""
        sub_arg = sub_parts[1] if len(sub_parts) > 1 else ""

        if sub_cmd == "commit":
            msg = sub_arg or f"CVC agent commit at turn {self.turn_count}"
            success, result = git_commit(self.workspace, msg)
            if success:
                render_success(f"Git commit: {result} — {msg}")
            else:
                render_error(f"Git commit failed: {result}")

        elif sub_cmd == "log":
            commits = git_log(self.workspace)
            if commits:
                console.print()
                for c in commits:
                    console.print(
                        f"  [{THEME['hash']}]{c['hash']}[/{THEME['hash']}]  "
                        f"{c['message'][:50]}  "
                        f"[{THEME['text_dim']}]{c['author']} • {c['time']}[/{THEME['text_dim']}]"
                    )
                console.print()
            else:
                render_info("No Git commits found.")

        elif sub_cmd == "diff":
            diff_text = git_diff_summary(self.workspace)
            console.print()
            for line in diff_text.split("\n"):
                console.print(f"  [{THEME['text']}]{line}[/{THEME['text']}]")
            console.print()

        else:
            # Default: show status
            status = git_status(self.workspace)
            render_git_status(format_git_status(status))

    async def _handle_image(self, arg_str: str) -> None:
        """Handle /image command — load image file and optionally send with prompt.

        Usage:
            /image screenshot.png                → loads image, waits for next prompt
            /image screenshot.png fix this bug   → loads image + sends prompt together
        """
        # Split: first token is the file path, rest is the prompt text
        parts = arg_str.strip().split(maxsplit=1)
        path_str = parts[0]
        prompt_text = parts[1].strip() if len(parts) > 1 else ""

        path = Path(path_str)
        if not path.is_absolute():
            path = self.workspace / path
        path = path.resolve()

        if not path.exists():
            render_error(f"Image file not found: {path}")
            return

        # Read and encode the image
        try:
            image_data = path.read_bytes()
            b64_data = base64.b64encode(image_data).decode("utf-8")
            mime_type = mimetypes.guess_type(str(path))[0] or "image/png"

            text = prompt_text or f"I've attached an image from {path.name}. Please analyze it."
            _build_image_message(
                self.messages, self.config.provider,
                b64_data, mime_type, text,
            )

            render_success(f"Image loaded: {path.name} ({len(image_data) / 1024:.0f}KB)")

            if prompt_text:
                # Send immediately — no second prompt needed
                await self.run_turn_no_append(prompt_text)
            else:
                render_info(
                    "Image ready. Type your prompt, or just say what you need — "
                    "the image will be sent along with it."
                )

        except OSError as e:
            render_error(f"Failed to read image: {e}")

    async def _handle_paste(self, prompt_text: str = "") -> None:
        """Handle /paste command — grab clipboard image and optionally send with prompt.

        Usage:
            /paste                           → loads clipboard image, waits for next prompt
            /paste analyze this screenshot   → loads image + sends prompt in one action
        """
        images = _grab_clipboard_images()
        if not images:
            render_error("No image found in clipboard. Copy an image or screenshot first.")
            return

        for idx, (b64_data, mime_type) in enumerate(images):
            label = f"image {idx}"
            size_kb = len(b64_data) * 3 / 4 / 1024  # approx decoded size

            text = prompt_text or f"I've pasted {label} from my clipboard. Please analyze it."
            _build_image_message(
                self.messages, self.config.provider,
                b64_data, mime_type, text,
            )

            render_success(f"📎 Clipboard {label} attached ({size_kb:.0f}KB, {mime_type})")

        # Update clipboard hash so auto-detect doesn't re-send the same image
        import hashlib
        self._last_clipboard_hash = hashlib.sha256(images[0][0].encode()).hexdigest()

        if prompt_text:
            # Send immediately — image + prompt in one action, no second prompt needed
            render_info(f"📎 {len(images)} image(s) + prompt → sending…")
            await self.run_turn_no_append(prompt_text)
        else:
            render_info(
                f"{len(images)} image(s) loaded. "
                "Type your prompt — the image will be sent with it automatically."
            )

    def _handle_memory(self) -> None:
        """Show persistent memory from past sessions."""
        try:
            from cvc.agent.memory import load_memory
            memory = load_memory()
            render_memory(memory)
        except Exception as e:
            render_error(f"Failed to load memory: {e}")

    def _handle_files_command(self, arg: str | None = None) -> None:
        """List files in the workspace with optional filtering."""
        try:
            from pathlib import Path
            import os
            
            workspace = self.workspace or Path.cwd()
            
            # Build exclude list
            exclude_dirs = {'.git', '.cvc', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'env', 'dist', 'build', '.egg-info'}
            exclude_extensions = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe'}
            
            files_found = []
            
            for root, dirs, files in os.walk(workspace):
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for file in files:
                    # Skip excluded extensions
                    if any(file.endswith(ext) for ext in exclude_extensions):
                        continue
                    
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(workspace)
                    
                    # Filter by pattern if provided
                    if arg and arg.lower() not in str(rel_path).lower():
                        continue
                    
                    files_found.append(str(rel_path))
            
            if not files_found:
                render_info("No files found" + (f" matching '{arg}'" if arg else ""))
                return
            
            # Sort and display
            files_found.sort()
            
            from rich.panel import Panel
            file_list = "\n".join([f"  {f}" for f in files_found[:50]])
            if len(files_found) > 50:
                file_list += f"\n  ... and {len(files_found) - 50} more files"
            
            console.print(Panel(
                file_list,
                title=f"[bold]Files in {self.workspace.name}[/bold] ({len(files_found)} total)",
                border_style=THEME['primary'],
                padding=(1, 2)
            ))
        except Exception as e:
            render_error(f"Failed to list files: {e}")

    def _handle_summary_command(self) -> None:
        """Get a summary of the codebase structure."""
        try:
            from pathlib import Path
            import os
            
            workspace = self.workspace or Path.cwd()
            
            exclude_dirs = {'.git', '.cvc', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'env', 'dist', 'build', '.egg-info'}
            
            # Count files by type
            file_counts = {}
            total_size = 0
            total_lines = 0
            
            for root, dirs, files in os.walk(workspace):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for file in files:
                    full_path = Path(root) / file
                    ext = full_path.suffix or "no_ext"
                    
                    file_counts[ext] = file_counts.get(ext, 0) + 1
                    
                    try:
                        size = full_path.stat().st_size
                        total_size += size
                        
                        # Count lines for text files
                        if ext in {'.py', '.ts', '.js', '.go', '.rs', '.java', '.c', '.cpp', '.h', '.md', '.txt', '.json', '.yaml', '.yml'}:
                            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                total_lines += len(f.readlines())
                    except:
                        pass
            
            # Format output
            summary_lines = []
            summary_lines.append(f"[bold]📁 {self.workspace.name}[/bold]")
            summary_lines.append(f"  Total size: {total_size / (1024*1024):.1f} MB")
            summary_lines.append(f"  Total lines of code: {total_lines:,}")
            summary_lines.append("")
            summary_lines.append("[bold]File Types:[/bold]")
            
            for ext, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
                summary_lines.append(f"  {ext:15} {count:5} files")
            
            from rich.panel import Panel
            console.print(Panel(
                "\n".join(summary_lines),
                title="[bold]Codebase Summary[/bold]",
                border_style=THEME['primary'],
                padding=(1, 2)
            ))
        except Exception as e:
            render_error(f"Failed to summarize codebase: {e}")

    def _handle_diff_command(self, arg: str | None = None) -> None:
        """Show recent diffs or specific file diffs."""
        try:
            from cvc.agent.git_integration import git_diff_summary
            
            # Get diffs for workspace
            diffs = git_diff_summary(self.workspace or Path.cwd())
            if not diffs or diffs.strip() == "":
                render_info("No recent changes found.")
                return
            
            from rich.syntax import Syntax
            from rich.panel import Panel
            
            # Show as formatted output
            console.print(Panel(
                diffs,
                title="[bold]Git Changes[/bold]",
                border_style=THEME['primary'],
                padding=(1, 2)
            ))
        except Exception as e:
            render_error(f"Failed to show diffs: {e}")

    def _handle_continue_command(self) -> None:
        """Continue with the AI from the last point in conversation."""
        if len(self.messages) <= 2:
            render_info("Continue: No previous conversation to continue from.")
            return
        
        # Find the last user or assistant message
        last_user_msg = None
        for msg in reversed(self.messages[1:]):  # Skip system message
            if msg['role'] in ('user', 'assistant'):
                last_user_msg = msg
                break
        
        if not last_user_msg:
            render_info("Continue: No previous messages to continue from.")
            return
        
        # Show last context
        from rich.panel import Panel
        context_preview = last_user_msg['content'][:200]
        if len(last_user_msg['content']) > 200:
            context_preview += "..."
        
        console.print(Panel(
            f"Last {last_user_msg['role']}: {context_preview}",
            title="[bold]Continuing from...[/bold]",
            border_style=THEME['primary_dim'],
            padding=(1, 2)
        ))
        
        render_success("Ready to continue. Send your next message.")

    def _handle_checkout_command(self, branch_name: str) -> None:
        """Switch to an existing branch."""
        try:
            # Get all available branches
            branches = self.engine.db.index.list_branches()
            branch_names = [b.name for b in branches]
            
            if branch_name not in branch_names:
                render_error(f"Branch '{branch_name}' not found. Available branches:\n  " + "\n  ".join(branch_names))
                return
            
            # Switch to the branch
            branch_ptr = self.engine.db.index.get_branch(branch_name)
            if branch_ptr:
                self.engine._active_branch = branch_name
                render_success(f"Switched to branch '{branch_name}'")
                self._rebuild_system_prompt()
            else:
                render_error(f"Failed to switch to branch '{branch_name}'")
        except Exception as e:
            render_error(f"Failed to checkout branch: {e}")

    def _handle_branches_command(self) -> None:
        """List all available branches."""
        try:
            branches = self.engine.db.index.list_branches()
            
            if not branches:
                render_info("No branches found.")
                return
            
            from rich.table import Table
            
            table = Table(
                title="[bold]Branches[/bold]",
                border_style=THEME['primary'],
                show_header=True,
                header_style=f"bold {THEME['primary_bright']}",
            )
            table.add_column("Branch", style=THEME['branch'], width=30)
            table.add_column("HEAD", style=THEME['hash'], width=15)
            table.add_column("Status", style=THEME['text_dim'])
            
            active = self.engine.active_branch
            for b in branches:
                status = "● current" if b.name == active else ""
                head_display = b.head_hash[:12] if b.head_hash else "none"
                table.add_row(b.name, head_display, status)
            
            console.print(table)
            console.print()
        except Exception as e:
            render_error(f"Failed to list branches: {e}")

    def _handle_merge_command(self, source_branch: str) -> None:
        """Merge source branch into current branch."""
        try:
            from cvc.core.models import CVCMergeRequest
            
            target_branch = self.engine.active_branch
            
            if source_branch == target_branch:
                render_error("Cannot merge a branch into itself.")
                return
            
            # Verify source branch exists
            branches = self.engine.db.index.list_branches()
            branch_names = [b.name for b in branches]
            
            if source_branch not in branch_names:
                render_error(f"Source branch '{source_branch}' not found. Available branches:\n  " + "\n  ".join(branch_names))
                return
            
            render_info(f"Merging '{source_branch}' into '{target_branch}'...")
            
            # Create merge request
            request = CVCMergeRequest(
                source_branch=source_branch,
                target_branch=target_branch,
            )
            
            # Perform the merge
            result = self.engine.merge(request)
            
            if result.success:
                render_success(f"✓ Merged '{source_branch}' into '{target_branch}'")
                render_success(f"Merge commit: {result.commit_hash[:12]}")
                # Rebuild system prompt with merged context
                self._rebuild_system_prompt()
                # Add merge notification to conversation
                self.messages.append({
                    "role": "system",
                    "content": f"[CVC] Successfully merged branch '{source_branch}' into '{target_branch}' (commit {result.commit_hash[:12]}). Context has been unified.",
                })
            else:
                render_error(f"Merge failed: {result.message}")
                
        except Exception as e:
            render_error(f"Failed to merge branches: {e}")


    def _save_session_memory(self) -> None:
        """Save a summary of this session to persistent memory."""
        if self.turn_count < 1:
            return
        try:
            from cvc.agent.memory import save_memory_entry, generate_session_summary
            summary, topics = generate_session_summary(self.messages)
            save_memory_entry(
                workspace=str(self.workspace),
                summary=summary,
                topics=topics,
                model=self.config.model,
                turn_count=self.turn_count,
                cost_usd=self.cost_tracker.total_cost_usd,
            )
        except Exception as e:
            logger.debug("Failed to save session memory: %s", e)

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

        if choice.isdigit() and 1 <= int(choice) <= len(catalog):
            new_model = catalog[int(choice) - 1][0]
        else:
            new_model = choice

        self.config.model = new_model
        self.llm.model = new_model
        self.cost_tracker.model = new_model
        self.autopilot.update_model(new_model)

        try:
            from cvc.core.models import GlobalConfig
            gc = GlobalConfig.load()
            gc.model = new_model
            gc.save()
        except Exception:
            pass

        render_success(f"Model switched to [bold]{new_model}[/bold]")

    def _handle_analytics_command(self) -> None:
        """Show detailed analytics for the current session and historical usage."""
        try:
            from rich.table import Table
            
            # Current session analytics
            session_cost = self.cost_tracker.total_cost_usd
            input_tokens = self.cost_tracker.total_input_tokens
            output_tokens = self.cost_tracker.total_output_tokens
            cache_tokens = self.cost_tracker.total_cache_read_tokens
            total_tokens = input_tokens + output_tokens + cache_tokens
            
            analytics = []
            analytics.append("[bold]📊 Session Analytics[/bold]")
            analytics.append("")
            analytics.append(f"  Total Tokens:     {total_tokens:,}")
            analytics.append(f"  Input Tokens:     {input_tokens:,}")
            analytics.append(f"  Output Tokens:    {output_tokens:,}")
            analytics.append(f"  Cache Tokens:     {cache_tokens:,}")
            analytics.append(f"  Session Cost:     ${session_cost:.4f}")
            analytics.append(f"  Turns:            {self.turn_count}")
            analytics.append(f"  Messages:         {len(self.messages)}")
            analytics.append(f"  Provider:         {self.config.provider}")
            analytics.append(f"  Model:            {self.config.model}")
            analytics.append(f"  Branch:           {self.engine.active_branch}")
            analytics.append(f"  Workspace:        {self.workspace.name}")
            analytics.append("")
            
            # Per-turn average
            if self.turn_count > 0:
                avg_cost = session_cost / self.turn_count
                avg_tokens = total_tokens / self.turn_count if total_tokens > 0 else 0
                analytics.append(f"  Avg Cost/Turn:    ${avg_cost:.4f}")
                analytics.append(f"  Avg Tokens/Turn:  {avg_tokens:.0f}")
                analytics.append("")
            
            # Commits
            try:
                commits = self.engine.db.index.list_commits(self.engine.active_branch)
                analytics.append(f"  Commits:          {len(commits)}")
            except:
                pass
            
            from rich.panel import Panel
            console.print(Panel(
                "\n".join(analytics),
                title="[bold]Session & Usage Analytics[/bold]",
                border_style=THEME['primary'],
                padding=(1, 2)
            ))
            
        except Exception as e:
            render_error(f"Failed to show analytics: {e}")

    def _interactive_provider_switch(self) -> None:
        """Let the user switch provider + model interactively."""
        providers = [
            ("anthropic", "Anthropic", "Claude Opus, Sonnet, Haiku"),
            ("openai", "OpenAI", "GPT-5.2, Codex, GPT-4.1"),
            ("google", "Google", "Gemini 2.5 Flash/Pro, Gemini 3"),
            ("ollama", "Ollama", "Local models — no API key"),
            ("lmstudio", "LM Studio", "Local models via LM Studio server — no API key"),
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

        from cvc.core.models import GlobalConfig
        gc = GlobalConfig.load()
        key = gc.api_keys.get(new_provider, "")

        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": "",
            "lmstudio": "",
        }
        env_key = env_map.get(new_provider, "")
        if env_key:
            key = key or os.getenv(env_key, "")

        if not key and new_provider not in ("ollama", "lmstudio"):
            render_error(
                f"No API key for {new_provider}. "
                f"Run [bold]cvc setup[/bold] to configure it first."
            )
            return

        self.config.provider = new_provider
        self.llm.provider = new_provider
        self.llm.api_key = key

        base_url_map = {
            "anthropic": "https://api.anthropic.com",
            "openai": "https://api.openai.com",
            "google": "https://generativelanguage.googleapis.com",
            "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            "lmstudio": os.getenv("LMSTUDIO_HOST", "http://localhost:1234"),
        }
        self.llm._api_url = base_url_map.get(new_provider, "")

        render_success(f"Provider switched to [bold]{new_provider}[/bold]")
        self._interactive_model_switch()

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
                mode="cli",
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

        if self._is_proxy_running():
            render_info("CVC Proxy is already running on [bold]http://127.0.0.1:8000[/bold]")
            return

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
            render_success("CVC Proxy starting in a new terminal window…")
            render_info("Connect your IDE to [bold]http://127.0.0.1:8000/v1[/bold]")
        except Exception as exc:
            render_error(f"Failed to start proxy: {exc}")
            render_info("Start it manually: [bold]cvc serve[/bold]")

    @staticmethod
    def _is_proxy_running(host: str = "127.0.0.1", port: int = 8000) -> bool:
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
            "lmstudio": "",
        }
        env_key = env_map.get(provider, "")
        api_key = os.getenv(env_key, "") if env_key else ""
        if not api_key:
            api_key = gc.api_keys.get(provider, "")

    if not api_key and provider not in ("ollama", "lmstudio"):
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
        mode="cli",
    )
    config.ensure_dirs()
    db = ContextDatabase(config)
    engine = CVCEngine(config, db)

    # The CVCEngine.__init__ now auto-hydrates context from the HEAD commit
    # and/or persistent cache, so the context_window is already populated.
    # Log cross-mode detection for the user.
    if engine.context_window:
        try:
            bp = db.index.get_branch(engine.active_branch)
            if bp:
                head_commit = db.index.get_commit(bp.head_hash)
                if head_commit and head_commit.metadata.mode and head_commit.metadata.mode != "cli":
                    logger.info(
                        "Cross-mode restore: %d messages from %s -> CLI (commit %s)",
                        len(engine.context_window),
                        head_commit.metadata.mode.upper(),
                        bp.head_hash[:12],
                    )
        except Exception:
            pass

    # Build LLM client
    base_url_map = {
        "anthropic": "https://api.anthropic.com",
        "openai": "https://api.openai.com",
        "google": "https://generativelanguage.googleapis.com",
        "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "lmstudio": os.getenv("LMSTUDIO_HOST", "http://localhost:1234"),
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
        version = "0.9.0"

    # Show banner
    agent_banner(
        version=version,
        provider=provider,
        model=model,
        branch=engine.active_branch,
        workspace=str(workspace),
    )

    # ── Git status on startup ────────────────────────────────────────────
    try:
        from cvc.agent.git_integration import git_status
        gs = git_status(workspace)
        render_git_startup_info(gs)
    except Exception:
        pass

    # ── Smart onboarding: check CVC init & proxy status ──────────────────
    _smart_onboarding(workspace, config)

    # ── Session resume check ─────────────────────────────────────────────
    _session_resume = False
    existing_context = engine.context_window
    if existing_context and len(existing_context) > 2:
        resume = render_session_resume_prompt()
        if resume == "resume":
            _session_resume = True
            render_success(f"Resuming session with {len(existing_context)} messages of context.")
            console.print()

    # ── Memory recall ────────────────────────────────────────────────────
    try:
        from cvc.agent.memory import get_relevant_memories
        memories = get_relevant_memories(str(workspace), limit=3)
        if memories and not _session_resume:
            recent = memories[-1]
            # Format the date nicely: "2026-02-17T20:23" → "Feb 17, 2026 at 20:23"
            raw_date = recent.get('date', '?')[:16]
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(raw_date)
                nice_date = dt.strftime("%b %d, %Y at %H:%M")
            except Exception:
                nice_date = raw_date.replace("T", " at ")
            render_info(
                f"Last session: {nice_date} — "
                f"{recent.get('summary', '')[:80]}"
            )
            console.print()
    except Exception:
        pass

    # Create session
    session = AgentSession(
        workspace=workspace,
        config=config,
        engine=engine,
        db=db,
        llm=llm,
    )

    # ── Check for prompt_toolkit availability ────────────────────────────
    _has_prompt_toolkit = False
    try:
        import prompt_toolkit
        _has_prompt_toolkit = True
    except ImportError:
        pass

    # REPL loop
    try:
        while True:
            try:
                if _has_prompt_toolkit:
                    user_input = await get_input_with_completion(
                        branch=engine.active_branch,
                        turn=session.turn_count + 1,
                        health_bar=session._health_bar,
                    )
                else:
                    user_input = await asyncio.to_thread(
                        print_input_prompt,
                        engine.active_branch,
                        session.turn_count + 1,
                        session._health_bar,
                    )
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                should_continue = await session.handle_slash_command(user_input)
                if not should_continue:
                    break
                continue

            # ── Ctrl+V pasted images (from prompt_toolkit keybinding) ──
            # If the user pressed Ctrl+V during input and there was an
            # image in the clipboard, it's now in _pending_paste_images.
            _ctrlv_images = get_pending_paste_images()
            if _ctrlv_images:
                import hashlib as _hlv
                for idx, (b64_data, mime_type) in enumerate(_ctrlv_images):
                    label = f"image {idx}"
                    size_kb = len(b64_data) * 3 / 4 / 1024
                    # Strip the 📎 marker from user text for the LLM
                    clean_input = user_input
                    for _marker_pattern in [" 📎[1 image] ", " 📎[2 images] ", " 📎[3 images] "]:
                        clean_input = clean_input.replace(_marker_pattern, " ").strip()
                    _build_image_message(
                        session.messages, session.config.provider,
                        b64_data, mime_type,
                        clean_input or "Please analyze this image.",
                    )
                    render_success(
                        f"📎 Pasted clipboard {label} ({size_kb:.0f}KB, {mime_type})"
                    )
                session._last_clipboard_hash = _hlv.sha256(
                    _ctrlv_images[0][0].encode()
                ).hexdigest()
                # Send immediately
                clean_input = user_input
                for _marker_pattern in [" 📎[1 image] ", " 📎[2 images] ", " 📎[3 images] "]:
                    clean_input = clean_input.replace(_marker_pattern, " ").strip()
                try:
                    await session.run_turn_no_append(clean_input or "analyze this image")
                except KeyboardInterrupt:
                    render_info("Interrupted. Type /exit to quit.")
                except Exception as exc:
                    render_error(f"Unexpected error: {exc}")
                    logger.error("Turn error: %s", exc, exc_info=True)
                continue

            # ── Smart clipboard image detection ─────────────────────
            # Clipboard images are attached ONLY when the user
            # explicitly signals intent:
            #   1. Ctrl+V         → handled above (prompt_toolkit)
            #   2. /paste         → slash command
            #   3. Keyword-based  → prompt mentions "screenshot",
            #      "paste", "clipboard", "look at this", etc.
            #   4. File path      → prompt contains e.g. screenshot.png
            #
            # We intentionally do NOT auto-attach based on a new
            # clipboard hash alone — that could leak accidental or
            # private screenshots the user never intended to share.
            import hashlib as _hl

            _image_keywords = {
                "screenshot", "image", "pasted", "paste", "clipboard",
                "this picture", "this photo", "attached", "look at this",
                "see this", "check this",
            }
            _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
            _lower_input = user_input.lower()
            _auto_pasted = False

            # Strategy A: detect inline image file paths in the prompt
            _path_attached = False
            for token in user_input.split():
                _p = Path(token)
                if _p.suffix.lower() in _IMAGE_EXTS:
                    candidate = _p if _p.is_absolute() else (session.workspace / _p)
                    if candidate.exists():
                        try:
                            _idata = candidate.read_bytes()
                            _b64 = base64.b64encode(_idata).decode("utf-8")
                            _mime = mimetypes.guess_type(str(candidate))[0] or "image/png"
                            _build_image_message(
                                session.messages, session.config.provider,
                                _b64, _mime, user_input,
                            )
                            render_success(
                                f"📎 Auto-attached {candidate.name} "
                                f"({len(_idata) / 1024:.0f}KB)"
                            )
                            _path_attached = True
                        except OSError:
                            pass

            if _path_attached:
                _auto_pasted = True
            else:
                # Strategy B: clipboard image — ONLY when user explicitly
                # mentions image-related keywords.  We do NOT auto-attach
                # based on "new hash" alone because the user may have taken
                # an accidental or private screenshot that they never
                # intended to share with the LLM.
                _has_keyword = any(kw in _lower_input for kw in _image_keywords)
                if _has_keyword:
                    clip_images = _grab_clipboard_images()
                    if clip_images:
                        _clip_hash = _hl.sha256(clip_images[0][0].encode()).hexdigest()
                        for idx, (b64_data, mime_type) in enumerate(clip_images):
                            label = f"image {idx}"
                            size_kb = len(b64_data) * 3 / 4 / 1024
                            _build_image_message(
                                session.messages, session.config.provider,
                                b64_data, mime_type, user_input,
                            )
                            render_success(
                                f"📎 Auto-attached clipboard {label} ({size_kb:.0f}KB)"
                            )
                        session._last_clipboard_hash = _clip_hash
                        _auto_pasted = True

            # Run ordinary turn (skip if images were auto-pasted — run_turn for the text)
            try:
                if _auto_pasted:
                    # Image messages already appended with user text;
                    # run the agentic loop without re-adding user message
                    await session.run_turn_no_append(user_input)
                else:
                    await session.run_turn(user_input)
            except KeyboardInterrupt:
                render_info("Interrupted. Type /exit to quit.")
                continue
            except Exception as exc:
                render_error(f"Unexpected error: {exc}")
                logger.error("Turn error: %s", exc, exc_info=True)
                continue

    finally:
        # Save session memory
        session._save_session_memory()
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
    """
    import subprocess as _sp

    cvc_dir = workspace / ".cvc"
    hints_shown = False

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

    if not _is_proxy_running_standalone():
        console.print(
            f"  [{THEME['text_dim']}]Tip: The CVC Proxy is not needed for the agent, "
            f"but your IDE needs it to connect to CVC.[/{THEME['text_dim']}]"
        )
        console.print(
            f"  [{THEME['text_dim']}]Run [bold]/serve[/bold] or [bold]cvc serve[/bold] "
            f"in another terminal if you want IDE integration.[/{THEME['text_dim']}]"
        )
        console.print()
        hints_shown = True

    if not hints_shown:
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
