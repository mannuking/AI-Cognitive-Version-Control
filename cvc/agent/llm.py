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

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger("cvc.agent.llm")


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
        else:
            raise ValueError(f"Unknown provider: {provider}")

        self._client = httpx.AsyncClient(
            base_url=self._api_url,
            headers=headers,
            timeout=180.0,
        )

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
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

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
            body["system"] = "\n\n".join(system_parts)

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

        body: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
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
        resp = await self._client.post(url, json=body)

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
        """Stream from Google Gemini API using SSE (streamGenerateContent)."""
        body = self._build_gemini_body(messages, tools, temperature, max_tokens)

        url = f"/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"

        tool_calls: list[ToolCall] = []
        all_raw_parts: list[dict] = []  # accumulate raw parts for thoughtSignature
        prompt_tokens = 0
        completion_tokens = 0

        try:
            async with self._client.stream("POST", url, json=body) as resp:
                if resp.status_code == 404:
                    raise RuntimeError(
                        f"Model '{self.model}' not found (404). "
                        f"Valid Google models include: gemini-2.5-flash, gemini-2.5-pro, "
                        f"gemini-3-pro-preview, gemini-2.5-flash-lite. "
                        f"Run 'cvc setup' to reconfigure or use --model to override."
                    )
                if resp.status_code == 400:
                    # Read the body for error details
                    body_bytes = b""
                    async for chunk in resp.aiter_bytes():
                        body_bytes += chunk
                    error_body = body_bytes.decode("utf-8", errors="replace")
                    logger.error("Gemini 400 Bad Request: %s", error_body[:1000])
                    raise RuntimeError(
                        f"Gemini returned 400 Bad Request for model '{self.model}'.\n"
                        f"Response: {error_body[:500]}\n\n"
                        f"If using a Gemini 3 model, ensure thought signatures are "
                        f"being preserved. Try 'gemini-2.5-flash' as an alternative."
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

                    # Extract candidates
                    candidates = chunk.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        # Accumulate raw parts (preserves thoughtSignature for Gemini 3)
                        all_raw_parts.extend(parts)
                        for i, part in enumerate(parts):
                            if "text" in part:
                                yield StreamEvent(type="text_delta", text=part["text"])
                            elif "functionCall" in part:
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
            raise RuntimeError(f"Gemini streaming error: {e}") from e

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            _provider_meta={"gemini_parts": all_raw_parts} if all_raw_parts else {},
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

    # ── Ollama (OpenAI-compatible) ───────────────────────────────────────

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
            },
        }

        if tools:
            body["tools"] = tools

        resp = await self._client.post("/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message", {})
        tool_calls_raw = msg.get("tool_calls", [])

        tool_calls = []
        for i, tc in enumerate(tool_calls_raw):
            fn = tc.get("function", {})
            tool_calls.append(ToolCall(
                id=f"call_{i}",
                name=fn.get("name", ""),
                arguments=fn.get("arguments", {}),
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

        if system_parts:
            body["system"] = "\n\n".join(system_parts)

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
        """Stream from Ollama API."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            body["tools"] = tools

        prompt_tokens = 0
        completion_tokens = 0

        async with self._client.stream("POST", "/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = chunk.get("message", {})

                # Text content
                if msg.get("content"):
                    yield StreamEvent(type="text_delta", text=msg["content"])

                # Tool calls (Ollama sends them in the final message)
                for i, tc_raw in enumerate(msg.get("tool_calls", [])):
                    fn = tc_raw.get("function", {})
                    tc = ToolCall(
                        id=f"call_{i}",
                        name=fn.get("name", ""),
                        arguments=fn.get("arguments", {}),
                    )
                    yield StreamEvent(type="tool_call_start", tool_call=tc)

                if chunk.get("done"):
                    prompt_tokens = chunk.get("prompt_eval_count", 0)
                    completion_tokens = chunk.get("eval_count", 0)

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
