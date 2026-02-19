"""
cvc.agent.llm — Unified LLM client with tool calling for all providers.

Handles the API specifics of tool calling for each provider:
  - Anthropic: Messages API with tools
  - OpenAI: Chat Completions with function calling
  - Google: Gemini generateContent with function declarations
  - Ollama: OpenAI-compatible chat with tools

Supports both blocking and streaming responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger("cvc.agent.llm")

# ---------------------------------------------------------------------------
# Performance constants
# ---------------------------------------------------------------------------
# Granular timeouts: fast connect, generous read for streaming
_CONNECT_TIMEOUT = 10.0    # TCP + TLS handshake (seconds)
_READ_TIMEOUT = 180.0      # Streaming read (seconds) — default for most models
_READ_TIMEOUT_SLOW = 360.0 # Streaming read for slow thinking models (Gemini 3 Pro)
_WRITE_TIMEOUT = 30.0      # Request body upload
_POOL_TIMEOUT = 10.0       # Waiting for a connection from the pool

# Transient error retry settings
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503}  # Rate-limit, server errors
_MAX_TRANSIENT_RETRIES = 3
_TRANSIENT_RETRY_BASE_DELAY = 1.0  # seconds, doubles each retry

_TIMEOUT = httpx.Timeout(
    connect=_CONNECT_TIMEOUT,
    read=_READ_TIMEOUT,
    write=_WRITE_TIMEOUT,
    pool=_POOL_TIMEOUT,
)

# Connection pool limits — keep connections alive to skip TLS on subsequent requests
_POOL_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=120,  # seconds
)

# Whether to try HTTP/2 (requires httpx[http2] / h2 package)
try:
    import h2  # noqa: F401
    _HTTP2_AVAILABLE = True
except ImportError:
    _HTTP2_AVAILABLE = False


@dataclass
class ToolCall:
    """A single tool call from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Unified response from any provider."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    _provider_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class StreamEvent:
    """A single event from a streaming LLM response."""
    type: str          # "text_delta", "tool_call_start", "tool_call_delta", "done", "usage"
    text: str = ""
    tool_call: ToolCall | None = None
    tool_call_index: int = 0
    args_delta: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    _provider_meta: dict[str, Any] = field(default_factory=dict)


class AgentLLM:
    """
    Unified LLM client that supports tool calling across all providers.

    Handles the translation between each provider's tool calling format
    and a common interface used by the agent loop.
    """

    # Common model name corrections (typo / shorthand → actual API name)
    _MODEL_ALIASES: dict[str, str] = {
        # Google Gemini aliases
        "gemini-3-pro": "gemini-3-pro-preview",
        "gemini-3-flash": "gemini-3-flash-preview",
        "gemini-3": "gemini-3-pro-preview",
        "gemini-2.5": "gemini-2.5-flash",
        "gemini-2.5-flash-preview": "gemini-2.5-flash",
        "gemini-2.5-pro-preview": "gemini-2.5-pro",
        "gemini-pro": "gemini-2.5-pro",
        "gemini-flash": "gemini-2.5-flash",
        # Anthropic aliases
        "claude-opus": "claude-opus-4-6",
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-haiku": "claude-haiku-4-5",
        "opus": "claude-opus-4-6",
        "opus-4.5": "claude-opus-4-5",
        "opus-4.6": "claude-opus-4-6",
        "sonnet": "claude-sonnet-4-6",
        "sonnet-4.5": "claude-sonnet-4-5",
        "sonnet-4.6": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5",
        # OpenAI aliases
        "gpt5": "gpt-5.2",
        "gpt-5": "gpt-5.2",
        "gpt5.2": "gpt-5.2",
        "gpt5.3": "gpt-5.3",
        "gpt-5-mini": "gpt-5-mini",
    }

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str = "",
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.base_url = base_url

        # Auto-correct common model name mistakes
        corrected = self._MODEL_ALIASES.get(model)
        if corrected:
            logger.info("Auto-corrected model name '%s' → '%s'", model, corrected)
            model = corrected
        self.model = model

        # Build the httpx client for the provider
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.provider == "anthropic":
            self._api_url = base_url or "https://api.anthropic.com"
            headers.update({
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
            })
        elif self.provider == "openai":
            self._api_url = base_url or "https://api.openai.com"
            headers["Authorization"] = f"Bearer {api_key}"
        elif self.provider == "google":
            self._api_url = base_url or "https://generativelanguage.googleapis.com"
        elif self.provider == "ollama":
            self._api_url = base_url or "http://localhost:11434"
        elif self.provider == "lmstudio":
            # LM Studio exposes a full OpenAI-compatible API at localhost:1234
            # No API key required — set a placeholder so the Authorization header
            # doesn't cause a rejection on stricter LM Studio builds.
            self._api_url = base_url or "http://localhost:1234"
            headers["Authorization"] = f"Bearer {api_key or 'lm-studio'}"
        else:
            raise ValueError(f"Unknown provider: {provider}")

        # Use HTTP/2 for cloud providers (reduces latency via multiplexing)
        # Local providers (Ollama, LM Studio) stay on HTTP/1.1
        _use_http2 = _HTTP2_AVAILABLE and self.provider in ("anthropic", "openai", "google")

        # Gemini 3 Pro Preview is an extremely slow thinking model (~2+ min
        # even for simple prompts).  Use a much longer read timeout so it
        # doesn't get cut off mid-thought and return 0 output tokens.
        _is_slow_model = (
            self.provider == "google" and "gemini-3-pro" in self.model
        )
        _read_timeout = _READ_TIMEOUT_SLOW if _is_slow_model else _READ_TIMEOUT
        _timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_read_timeout,
            write=_WRITE_TIMEOUT,
            pool=_POOL_TIMEOUT,
        )

        self._client = httpx.AsyncClient(
            base_url=self._api_url,
            headers=headers,
            timeout=_timeout,
            limits=_POOL_LIMITS,
            http2=_use_http2,
        )

        # Flag: has the TCP+TLS connection been warmed up?
        self._connection_warmed = False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """
        Send a chat request with tool definitions and return a unified response.
        """
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, tools, temperature, max_tokens)
        elif self.provider == "openai":
            return await self._chat_openai(messages, tools, temperature, max_tokens)
        elif self.provider == "google":
            return await self._chat_google(messages, tools, temperature, max_tokens)
        elif self.provider == "ollama":
            return await self._chat_ollama(messages, tools, temperature, max_tokens)
        elif self.provider == "lmstudio":
            # LM Studio is fully OpenAI-compatible — reuse the same code path
            return await self._chat_openai(messages, tools, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream a chat response token-by-token. Yields StreamEvent objects.
        Falls back to non-streaming for providers that don't support it well.
        """
        if self.provider == "anthropic":
            async for event in self._stream_anthropic(messages, tools, temperature, max_tokens):
                yield event
        elif self.provider == "openai":
            async for event in self._stream_openai(messages, tools, temperature, max_tokens):
                yield event
        elif self.provider == "google":
            async for event in self._stream_google(messages, tools, temperature, max_tokens):
                yield event
        elif self.provider == "ollama":
            async for event in self._stream_ollama(messages, tools, temperature, max_tokens):
                yield event
        elif self.provider == "lmstudio":
            # LM Studio is fully OpenAI-compatible — reuse the same streaming path
            async for event in self._stream_openai(messages, tools, temperature, max_tokens):
                yield event
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def warm_connection(self) -> None:
        """
        Pre-warm the TCP + TLS connection to the API provider.

        Call this ONCE during startup (while the user sees the banner)
        so the first real request skips the ~500ms-2s handshake.
        """
        if self._connection_warmed:
            return
        try:
            if self.provider == "anthropic":
                # Lightweight request — Anthropic returns 405 but connection is established
                await self._client.request("HEAD", "/v1/messages", timeout=5.0)
            elif self.provider == "openai":
                await self._client.request("HEAD", "/v1/chat/completions", timeout=5.0)
            elif self.provider == "google":
                # Just establish TCP+TLS to the API host
                await self._client.request("HEAD", "/", timeout=5.0)
            elif self.provider in ("ollama", "lmstudio"):
                # Local — check if server is alive
                await self._client.get("/", timeout=3.0)
        except Exception:
            # Connection warming is best-effort — never fail on this
            pass
        self._connection_warmed = True

    async def close(self) -> None:
        await self._client.aclose()

    # ── Anthropic ────────────────────────────────────────────────────────

    async def _chat_anthropic(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        # Split system messages
        system_parts = []
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_parts.append(m["content"])
            else:
                conv_messages.append(self._to_anthropic_message(m))

        # Anthropic requires alternating user/assistant
        conv_messages = self._fix_anthropic_alternation(conv_messages)

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conv_messages,
        }

        if system_parts:
            combined_system = "\n\n".join(system_parts)
            body["system"] = [
                {
                    "type": "text",
                    "text": combined_system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # Convert tools to Anthropic format
        if tools:
            anthropic_tools = []
            for t in tools:
                fn = t.get("function", t)
                anthropic_tools.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", fn.get("input_schema", {})),
                })
            body["tools"] = anthropic_tools

        resp = await self._client.post("/v1/messages", json=body)
        resp.raise_for_status()
        data = resp.json()

        # Parse response
        text_parts = []
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block.get("input", {}),
                ))

        usage = data.get("usage", {})
        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        )

    def _to_anthropic_message(self, msg: dict) -> dict:
        """Convert a message to Anthropic format."""
        role = msg["role"]
        if role == "system":
            role = "user"

        # Handle tool results
        if role == "tool":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }],
            }

        # Handle assistant messages with tool calls
        if role == "assistant" and msg.get("tool_calls"):
            content = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args,
                })
            return {"role": "assistant", "content": content}

        return {"role": role, "content": msg.get("content", "")}

    @staticmethod
    def _fix_anthropic_alternation(messages: list[dict]) -> list[dict]:
        """
        Anthropic requires strict user/assistant alternation.
        Fix consecutive same-role messages by merging them.
        """
        if not messages:
            return messages

        fixed = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == fixed[-1]["role"]:
                # Merge content
                prev_content = fixed[-1].get("content", "")
                curr_content = msg.get("content", "")
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    fixed[-1]["content"] = prev_content + "\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    fixed[-1]["content"] = prev_content + curr_content
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    fixed[-1]["content"] = [{"type": "text", "text": prev_content}] + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    fixed[-1]["content"] = prev_content + [{"type": "text", "text": curr_content}]
            else:
                fixed.append(msg)

        return fixed

    # ── OpenAI ───────────────────────────────────────────────────────────

    async def _chat_openai(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        resp = await self._client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {"raw": args_str}
            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=args,
            ))

        usage = data.get("usage", {})
        return LLMResponse(
            text=msg.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cache_read_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
        )

    # ── Google Gemini ────────────────────────────────────────────────────

    def _build_gemini_body(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Build the Gemini request body from messages and tools."""
        # Gemini 3 models require temperature=1.0 to avoid looping/degraded output
        if "gemini-3" in self.model:
            temperature = 1.0

        # Convert messages to Gemini format
        gemini_contents = []
        system_text = ""

        for m in messages:
            if m["role"] == "system":
                system_text += m.get("content", "") + "\n"
                continue

            role = "user" if m["role"] in ("user", "tool") else "model"
            parts = []

            if m["role"] == "tool":
                # Function response
                parts.append({
                    "functionResponse": {
                        "name": m.get("name", "tool"),
                        "response": {"result": m.get("content", "")},
                    }
                })
            elif m.get("tool_calls"):
                # Use raw Gemini parts if available — preserves thoughtSignature
                # for Gemini 3 models (mandatory for function calling).
                raw_parts = m.get("_gemini_parts")
                if raw_parts:
                    parts = list(raw_parts)  # use stored parts as-is
                else:
                    # Fallback: reconstruct from tool_calls (non-Gemini history)
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        parts.append({
                            "functionCall": {
                                "name": fn.get("name", ""),
                                "args": args,
                            }
                        })
                    if m.get("content"):
                        parts.insert(0, {"text": m["content"]})
            else:
                content = m.get("content", "")
                # Handle multimodal content (list of parts with images)
                if isinstance(content, list):
                    for item in content:
                        item_type = item.get("type", "")
                        if item_type == "text":
                            parts.append({"text": item.get("text", "")})
                        elif item_type == "image":
                            source = item.get("source", {})
                            parts.append({
                                "inlineData": {
                                    "mimeType": source.get("media_type", "image/png"),
                                    "data": source.get("data", ""),
                                }
                            })
                        elif item_type == "image_url":
                            # OpenAI-style data URL
                            url = item.get("image_url", {}).get("url", "")
                            if url.startswith("data:"):
                                # Parse data:mime;base64,DATA
                                header, data = url.split(",", 1)
                                mime = header.split(":")[1].split(";")[0]
                                parts.append({
                                    "inlineData": {
                                        "mimeType": mime,
                                        "data": data,
                                    }
                                })
                else:
                    parts.append({"text": content})

            gemini_contents.append({"role": role, "parts": parts})

        # Merge consecutive same-role contents (e.g. multiple tool results)
        # Gemini requires strict user/model alternation.
        gemini_contents = self._merge_gemini_contents(gemini_contents)

        # Convert tools to Gemini format
        gemini_tools = []
        if tools:
            declarations = []
            for t in tools:
                fn = t.get("function", t)
                declarations.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                })
            gemini_tools = [{"functionDeclarations": declarations}]

        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }

        # ── Gemini Thinking Configuration ──────────────────────────────
        # Gemini 3 and 2.5 series use DIFFERENT thinking parameters:
        #
        # Gemini 3 Pro:   thinkingLevel only ("low" | "high")
        #                 "minimal" NOT supported, default is "high" (very slow!)
        # Gemini 3 Flash: thinkingLevel only ("minimal" | "low" | "medium" | "high")
        # Gemini 2.5:     thinkingBudget only (-1=dynamic, 0=off, N=token cap)
        #
        # CRITICAL: Cannot mix thinkingLevel and thinkingBudget → 400 error.
        #           thinkingBudget is accepted on Gemini 3 for backward compat
        #           but causes "suboptimal performance" (per Google docs).
        _is_gemini3 = "gemini-3" in self.model
        _is_gemini25 = "2.5" in self.model

        if _is_gemini3:
            # Use thinkingLevel for Gemini 3 — "low" minimizes latency
            # "high" is default and takes 50+ seconds even for simple queries
            if "pro" in self.model:
                gen_config["thinkingConfig"] = {"thinkingLevel": "low"}
            else:
                # Gemini 3 Flash: "minimal" ≈ no thinking, lowest latency
                gen_config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        elif _is_gemini25:
            gen_config["thinkingConfig"] = {
                "thinkingBudget": min(max_tokens * 2, 16384),
            }

        body: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": gen_config,
        }

        if system_text.strip():
            body["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}

        if gemini_tools:
            body["tools"] = gemini_tools

        return body

    async def _chat_google(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        body = self._build_gemini_body(messages, tools, temperature, max_tokens)

        url = f"/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        # Retry loop for transient server errors (503, 429, 500, 502)
        last_exc: Exception | None = None
        for attempt in range(_MAX_TRANSIENT_RETRIES + 1):
            resp = await self._client.post(url, json=body)

            if resp.status_code in _TRANSIENT_STATUS_CODES:
                delay = _TRANSIENT_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Gemini %d (attempt %d/%d) — retrying in %.1fs…",
                    resp.status_code, attempt + 1, _MAX_TRANSIENT_RETRIES + 1, delay,
                )
                last_exc = RuntimeError(
                    f"Gemini {resp.status_code} for model '{self.model}' "
                    f"(tried {_MAX_TRANSIENT_RETRIES + 1} times). "
                    f"The model may be temporarily overloaded. "
                    f"Try 'gemini-2.5-flash' or retry in a few seconds."
                )
                await asyncio.sleep(delay)
                continue
            break  # non-transient status — stop retrying
        else:
            # All retries exhausted
            raise last_exc  # type: ignore[misc]

        if resp.status_code == 404:
            raise RuntimeError(
                f"Model '{self.model}' not found (404). "
                f"Valid Google models include: gemini-2.5-flash, gemini-2.5-pro, "
                f"gemini-3-pro-preview, gemini-2.5-flash-lite. "
                f"Run 'cvc setup' to reconfigure or use --model to override."
            )

        if resp.status_code == 400:
            error_body = resp.text
            logger.error("Gemini 400 Bad Request: %s", error_body[:1000])
            raise RuntimeError(
                f"Gemini returned 400 Bad Request for model '{self.model}'.\n"
                f"Response: {error_body[:500]}\n\n"
                f"If using a Gemini 3 model, ensure thought signatures are "
                f"being preserved. Try 'gemini-2.5-flash' as an alternative."
            )

        resp.raise_for_status()
        data = resp.json()

        # Parse Gemini response
        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(text="(no response from Gemini)")

        # Store the raw response parts — these contain thoughtSignature
        # fields that must be passed back for Gemini 3 function calling.
        raw_response_parts = candidates[0].get("content", {}).get("parts", [])

        text_parts = []
        tool_calls = []

        for i, part in enumerate(raw_response_parts):
            # Skip thinking parts — they're internal reasoning, not user output
            if part.get("thought") and "text" in part:
                continue
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(ToolCall(
                    id=f"call_{i}",
                    name=fc.get("name", ""),
                    arguments=fc.get("args", {}),
                ))

        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            _provider_meta={"gemini_parts": raw_response_parts},
        )

    async def _stream_google(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Stream from Google Gemini API using SSE (streamGenerateContent).

        Auto-retries with a safe fallback thinking budget if the model rejects
        thinkingBudget=0 (some Gemini models require a minimum of 512 tokens).

        Also retries up to 2 times on transient server errors (503, 429, 500, 502).
        """
        body = self._build_gemini_body(messages, tools, temperature, max_tokens)

        url = f"/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"

        # Retry loop for transient server errors (503/429/500/502)
        last_exc: Exception | None = None
        for attempt in range(_MAX_TRANSIENT_RETRIES):
            try:
                async for event in self._stream_google_body(body, url, messages, tools, temperature, max_tokens):
                    yield event
                return  # success — exit
            except RuntimeError as exc:
                err_lower = str(exc).lower()
                _is_transient = any(code in err_lower for code in ("503", "502", "429", "500", "overloaded", "unavailable", "capacity"))
                if _is_transient and attempt < _MAX_TRANSIENT_RETRIES - 1:
                    delay = _TRANSIENT_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Gemini streaming transient error (attempt %d/%d) — retrying in %.1fs…",
                        attempt + 1, _MAX_TRANSIENT_RETRIES, delay,
                    )
                    last_exc = exc
                    await asyncio.sleep(delay)
                    continue
                raise  # non-transient or last attempt — propagate
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_TRANSIENT_RETRIES - 1:
                    delay = _TRANSIENT_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Gemini streaming HTTP %d (attempt %d/%d) — retrying in %.1fs…",
                        exc.response.status_code, attempt + 1, _MAX_TRANSIENT_RETRIES, delay,
                    )
                    last_exc = exc
                    await asyncio.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Gemini streaming error ({exc.response.status_code}) for model '{self.model}'. "
                    f"Try: cvc agent --model gemini-2.5-flash"
                ) from exc

    async def _stream_google_body(
        self,
        body: dict,
        url: str,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
        _retry_fallback: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """Inner streaming implementation with automatic thinking-budget fallback."""
        tool_calls: list[ToolCall] = []
        all_raw_parts: list[dict] = []  # accumulate raw parts for thoughtSignature
        prompt_tokens = 0
        completion_tokens = 0
        finish_reason = ""  # Track why Gemini stopped
        has_any_content = False

        try:
            async with self._client.stream("POST", url, json=body) as resp:
                # ── Transient server errors (503, 429, 500, 502) ──────────
                if resp.status_code in _TRANSIENT_STATUS_CODES and not _retry_fallback:
                    delay = _TRANSIENT_RETRY_BASE_DELAY * 2
                    logger.warning(
                        "Gemini streaming %d — retrying in %.1fs…",
                        resp.status_code, delay,
                    )
                    await asyncio.sleep(delay)
                    # Retry once via recursive call (with _retry_fallback to prevent infinite loop)
                    async for event in self._stream_google_body(
                        body, url, messages, tools, temperature, max_tokens,
                        _retry_fallback=True,
                    ):
                        yield event
                    return
                elif resp.status_code in _TRANSIENT_STATUS_CODES:
                    raise RuntimeError(
                        f"Gemini {resp.status_code} for model '{self.model}' after retry. "
                        f"The model may be temporarily overloaded or in preview with limited capacity.\n"
                        f"Try: [bold]cvc agent --model gemini-2.5-flash[/bold]"
                    )

                if resp.status_code == 404:
                    raise RuntimeError(
                        f"Model '{self.model}' not found (404). "
                        f"Valid Google models: gemini-2.5-flash, gemini-2.5-pro, "
                        f"gemini-3-pro-preview, gemini-3-flash-preview.\n"
                        f"Run [bold]cvc setup[/bold] or use [bold]--model gemini-2.5-flash[/bold] to override."
                    )
                if resp.status_code == 400:
                    # Read the body for error details
                    body_bytes = b""
                    async for chunk in resp.aiter_bytes():
                        body_bytes += chunk
                    error_body = body_bytes.decode("utf-8", errors="replace")
                    logger.error("Gemini 400 Bad Request: %s", error_body[:1000])

                    # Auto-retry: if error is about thinking config and we
                    # haven't retried yet, switch to the other param style.
                    is_thinking_error = (
                        "thinkingBudget" in error_body
                        or "thinkingConfig" in error_body
                        or "thinking_budget" in error_body.lower()
                        or "thinking_level" in error_body.lower()
                        or "thinking level" in error_body.lower()
                        or "thinking mode" in error_body.lower()
                        or "thinkingLevel" in error_body
                        or "Budget" in error_body
                    )
                    if is_thinking_error and not _retry_fallback:
                        # Fallback: use the opposite thinking param style.
                        # Gemini 3 → try thinkingBudget (backward compat)
                        # Gemini 2.5 → try a small thinkingBudget
                        if "gemini-3" in self.model:
                            logger.info(
                                "thinkingLevel rejected — retrying with thinkingBudget=1024 (backward compat)"
                            )
                            fallback_thinking = {"thinkingBudget": 1024}
                        else:
                            logger.info(
                                "thinkingBudget rejected — retrying with thinkingBudget=1024"
                            )
                            fallback_thinking = {"thinkingBudget": 1024}

                        fallback_body = dict(body)
                        gc = dict(fallback_body.get("generationConfig", {}))
                        gc["thinkingConfig"] = fallback_thinking
                        fallback_body["generationConfig"] = gc
                        async for event in self._stream_google_body(
                            fallback_body, url, messages, tools, temperature, max_tokens,
                            _retry_fallback=True,
                        ):
                            yield event
                        return

                    raise RuntimeError(
                        f"Gemini 400 Bad Request for model '{self.model}'.\n"
                        f"{error_body[:400]}\n\n"
                        f"Try: [bold]cvc agent --model gemini-2.5-flash[/bold]"
                    )
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Check for API-level errors in the chunk
                    if "error" in chunk:
                        err = chunk["error"]
                        err_msg = err.get("message", str(err))[:300]
                        logger.error("Gemini API error in stream: %s", err_msg)
                        raise RuntimeError(f"Gemini API error: {err_msg}")

                    # Extract candidates
                    candidates = chunk.get("candidates", [])
                    if candidates:
                        candidate = candidates[0]

                        # Capture finishReason (only the last one matters)
                        fr = candidate.get("finishReason", "")
                        if fr:
                            finish_reason = fr

                        parts = candidate.get("content", {}).get("parts", [])
                        # Accumulate raw parts (preserves thoughtSignature for Gemini 3)
                        all_raw_parts.extend(parts)
                        for i, part in enumerate(parts):
                            # Skip thought-only parts (no user-visible text)
                            if part.get("thought") and "text" in part:
                                # Thinking part — don't yield as text_delta
                                # but DO keep in all_raw_parts for context
                                continue
                            if "text" in part:
                                has_any_content = True
                                yield StreamEvent(type="text_delta", text=part["text"])
                            elif "functionCall" in part:
                                has_any_content = True
                                fc = part["functionCall"]
                                tc = ToolCall(
                                    id=f"call_{len(tool_calls)}",
                                    name=fc.get("name", ""),
                                    arguments=fc.get("args", {}),
                                )
                                tool_calls.append(tc)
                                yield StreamEvent(type="tool_call_start", tool_call=tc)

                    # Extract usage metadata
                    usage = chunk.get("usageMetadata", {})
                    if usage:
                        prompt_tokens = usage.get("promptTokenCount", prompt_tokens)
                        completion_tokens = usage.get("candidatesTokenCount", completion_tokens)

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in _TRANSIENT_STATUS_CODES:
                raise RuntimeError(
                    f"Gemini {status} for model '{self.model}'. "
                    f"The model may be temporarily overloaded or in preview with limited capacity."
                ) from e
            raise RuntimeError(f"Gemini streaming error ({status}): {e}") from e

        # Detect blocked / empty responses and raise actionable errors
        if not has_any_content and finish_reason:
            _BLOCKED_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"}
            if finish_reason in _BLOCKED_REASONS:
                raise RuntimeError(
                    f"Gemini blocked the response (reason: {finish_reason}). "
                    f"This usually happens with very large tool outputs. "
                    f"Try a shorter query or use a different model."
                )
            elif finish_reason == "MAX_TOKENS":
                logger.warning("Gemini hit MAX_TOKENS with 0 visible output — "
                               "thinking may have consumed the entire budget.")
                # Don't raise — let the retry logic in the agentic loop handle it
            elif finish_reason not in ("STOP", ""):
                logger.warning("Gemini finished with reason '%s' and 0 content", finish_reason)

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            _provider_meta={
                "gemini_parts": all_raw_parts if all_raw_parts else [],
                "finish_reason": finish_reason,
            },
        )

    @staticmethod
    def _merge_gemini_contents(contents: list[dict]) -> list[dict]:
        """Merge consecutive same-role Gemini content blocks.

        Gemini requires strict user/model alternation.  Multiple tool
        results (role=user) must be merged into a single Content with
        multiple functionResponse parts.
        """
        if not contents:
            return contents
        merged = [contents[0]]
        for content in contents[1:]:
            if content["role"] == merged[-1]["role"]:
                merged[-1]["parts"].extend(content["parts"])
            else:
                merged.append(content)
        return merged

    # ── Ollama (native /api/chat endpoint) ──────────────────────────────
    #
    # IMPORTANT: We use Ollama's NATIVE /api/chat endpoint, NOT the
    # OpenAI-compat /v1/chat/completions endpoint. The compat layer has a
    # known bug (ollama#12557) where it silently drops tool_calls when
    # stream=true. The native API has fully supported streaming + tool
    # calling since May 2025 (ollama#10415).
    #
    # Critical fix: num_ctx MUST be set. Ollama defaults to 4096 tokens
    # which truncates the system prompt + all 17 tool schemas, causing the
    # model to never see the tool definitions and silently produce text
    # instead of tool calls.

    _OLLAMA_NUM_CTX = 32768  # Safe default: covers system prompt + all tools

    async def _chat_ollama(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                # FIX: Without num_ctx, Ollama defaults to 4096 tokens which
                # silently truncates the tool schemas — the model never sees
                # tool definitions and can't make tool calls.
                "num_ctx": self._OLLAMA_NUM_CTX,
            },
        }

        if tools:
            body["tools"] = tools

        try:
            resp = await self._client.post("/api/chat", json=body)
            resp.raise_for_status()
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._api_url}.\n"
                "Make sure Ollama is running. Start it with: ollama serve\n"
                "Download from: https://ollama.com/download"
            )
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text
            if exc.response.status_code == 404 or "not found" in body_text.lower():
                raise RuntimeError(
                    f"Model '{self.model}' is not installed in Ollama.\n"
                    f"Pull it first: ollama pull {self.model}\n"
                    f"Browse models: https://ollama.com/library"
                ) from exc
            raise RuntimeError(f"Ollama API error {exc.response.status_code}: {body_text}") from exc

        data = resp.json()
        msg = data.get("message", {})
        tool_calls_raw = msg.get("tool_calls", [])

        tool_calls = []
        for i, tc in enumerate(tool_calls_raw):
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            # FIX: Some Ollama model versions return arguments as a JSON string
            # rather than a pre-parsed dict. Normalise to dict in both cases.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {"raw": args}
            tool_calls.append(ToolCall(
                id=f"call_{i}",
                name=fn.get("name", ""),
                arguments=args,
            ))

        return LLMResponse(
            text=msg.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    # ── Streaming Implementations ────────────────────────────────────────

    async def _stream_anthropic(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Stream from Anthropic Messages API using SSE."""
        system_parts = []
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_parts.append(m["content"])
            else:
                conv_messages.append(self._to_anthropic_message(m))

        conv_messages = self._fix_anthropic_alternation(conv_messages)

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conv_messages,
            "stream": True,
        }

        # PERF: Use Anthropic prompt caching — mark the system prompt as
        # cacheable so subsequent turns skip re-processing the entire
        # system prompt + auto-context (saves ~1-2s per turn).
        if system_parts:
            combined_system = "\n\n".join(system_parts)
            body["system"] = [
                {
                    "type": "text",
                    "text": combined_system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        if tools:
            anthropic_tools = []
            for t in tools:
                fn = t.get("function", t)
                anthropic_tools.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", fn.get("input_schema", {})),
                })
            body["tools"] = anthropic_tools

        tool_calls: list[ToolCall] = []
        tool_input_buffers: dict[int, str] = {}
        prompt_tokens = 0
        completion_tokens = 0
        cache_read = 0

        async with self._client.stream("POST", "/v1/messages", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        idx = event.get("index", len(tool_calls))
                        tc = ToolCall(
                            id=block.get("id", f"call_{idx}"),
                            name=block.get("name", ""),
                            arguments={},
                        )
                        tool_calls.append(tc)
                        tool_input_buffers[idx] = ""
                        yield StreamEvent(type="tool_call_start", tool_call=tc, tool_call_index=idx)

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield StreamEvent(type="text_delta", text=delta.get("text", ""))
                    elif delta.get("type") == "input_json_delta":
                        idx = event.get("index", 0)
                        partial = delta.get("partial_json", "")
                        if idx in tool_input_buffers:
                            tool_input_buffers[idx] += partial

                elif event_type == "content_block_stop":
                    idx = event.get("index", 0)
                    if idx in tool_input_buffers and idx < len(tool_calls):
                        try:
                            tool_calls[idx].arguments = json.loads(tool_input_buffers[idx])
                        except json.JSONDecodeError:
                            tool_calls[idx].arguments = {"raw": tool_input_buffers[idx]}

                elif event_type == "message_delta":
                    usage = event.get("usage", {})
                    completion_tokens = usage.get("output_tokens", completion_tokens)

                elif event_type == "message_start":
                    msg_data = event.get("message", {})
                    usage = msg_data.get("usage", {})
                    prompt_tokens = usage.get("input_tokens", 0)
                    cache_read = usage.get("cache_read_input_tokens", 0)

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read,
        )

    async def _stream_openai(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Stream from OpenAI Chat Completions API using SSE."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        tool_calls: dict[int, ToolCall] = {}
        tool_args_buffers: dict[int, str] = {}
        prompt_tokens = 0
        completion_tokens = 0

        async with self._client.stream("POST", "/v1/chat/completions", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta", {})

                # Text content
                if delta.get("content"):
                    yield StreamEvent(type="text_delta", text=delta["content"])

                # Tool calls
                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls:
                        fn = tc_delta.get("function", {})
                        tc = ToolCall(
                            id=tc_delta.get("id", f"call_{idx}"),
                            name=fn.get("name", ""),
                            arguments={},
                        )
                        tool_calls[idx] = tc
                        tool_args_buffers[idx] = ""
                        yield StreamEvent(type="tool_call_start", tool_call=tc, tool_call_index=idx)

                    fn_delta = tc_delta.get("function", {})
                    if fn_delta.get("arguments"):
                        tool_args_buffers[idx] = tool_args_buffers.get(idx, "") + fn_delta["arguments"]

                # Usage info
                usage = chunk.get("usage")
                if usage:
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)

        # Finalize tool call arguments
        for idx, tc in tool_calls.items():
            raw = tool_args_buffers.get(idx, "{}")
            try:
                tc.arguments = json.loads(raw)
            except json.JSONDecodeError:
                tc.arguments = {"raw": raw}

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def _stream_ollama(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream from Ollama's native /api/chat endpoint.

        Tool call handling:
          Ollama sends tool_calls in ONE intermediate done:false chunk as a
          complete list (not incrementally like OpenAI). We accumulate them
          with a global index so IDs are unique across the entire response,
          then yield a tool_call_start event for each one as it arrives.

        num_ctx:
          Must be set explicitly — Ollama defaults to 4096 which truncates
          tool schemas and causes silent tool-call failures.
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                # FIX: Must set num_ctx or tool schemas get silently truncated
                "num_ctx": self._OLLAMA_NUM_CTX,
            },
        }

        if tools:
            body["tools"] = tools

        prompt_tokens = 0
        completion_tokens = 0
        # Global tool call counter so IDs are unique across chunks
        tc_global_idx = 0

        try:
            async with self._client.stream("POST", "/api/chat", json=body) as resp:
                # Must read the body before calling raise_for_status() inside a
                # streaming context — httpx raises ResponseNotRead otherwise when
                # it tries to include resp.text in the HTTPStatusError message.
                if resp.status_code >= 400:
                    await resp.aread()
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get("message", {})

                    # Text content delta — skip qwen3/thinking-mode "thinking"
                    # field; only forward the visible "content" to the user.
                    content = msg.get("content", "")
                    if content:
                        yield StreamEvent(type="text_delta", text=content)

                    # Tool calls — Ollama sends complete tool_calls in a single
                    # intermediate chunk (done:false). Accumulate with global index.
                    for tc_raw in msg.get("tool_calls", []):
                        fn = tc_raw.get("function", {})
                        args = fn.get("arguments", {})
                        # FIX: Normalise arguments — may be JSON string in some builds
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, ValueError):
                                args = {"raw": args}
                        tc = ToolCall(
                            id=f"call_{tc_global_idx}",
                            name=fn.get("name", ""),
                            arguments=args,
                        )
                        yield StreamEvent(
                            type="tool_call_start",
                            tool_call=tc,
                            tool_call_index=tc_global_idx,
                        )
                        tc_global_idx += 1

                    if chunk.get("done"):
                        prompt_tokens = chunk.get("prompt_eval_count", 0)
                        completion_tokens = chunk.get("eval_count", 0)

        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._api_url}.\n"
                "Make sure Ollama is running. Start it with: ollama serve"
            )
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text
            if exc.response.status_code == 404 or "not found" in body_text.lower():
                raise RuntimeError(
                    f"Model '{self.model}' is not installed in Ollama.\n"
                    f"Pull it with: ollama pull {self.model}"
                ) from exc
            raise

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
