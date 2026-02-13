"""
cvc.adapters.anthropic — Anthropic Claude adapter with Prompt Caching.

Implements the provider optimization described in §5.1 of the CVC paper:
- Structure prompts so the "Immutable History" (committed context up to the
  last Commit) serves as the cacheable prefix.
- Inject ``cache_control: {"type": "ephemeral"}`` at the boundary so that
  rollbacks and branch switches bypass token reprocessing.
- Achieve ~90 % cost reduction and ~85 % latency reduction for state
  restoration via cache hits.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from cvc.core.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ContextMessage,
    UsageInfo,
)

logger = logging.getLogger("cvc.adapters.anthropic")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter:
    """
    Translates OpenAI-compatible ``ChatCompletionRequest`` objects into
    Anthropic Messages API calls, injecting prompt-cache control headers
    at the immutable-prefix boundary.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "anthropic-beta": "prompt-caching-2024-07-31",
                "content-type": "application/json",
            },
            timeout=120.0,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        request: ChatCompletionRequest,
        *,
        committed_prefix_len: int = 0,
    ) -> ChatCompletionResponse:
        """
        Send a completion request to Claude, splitting the messages into
        a cached *prefix* (the committed history) and a live *suffix*.

        Parameters
        ----------
        request:
            The incoming chat-completion request (OpenAI schema).
        committed_prefix_len:
            Number of messages (from the front) that are part of the
            immutable committed history and should be cached.
        """
        system_text, messages = self._split_system(request.messages)
        anthropic_msgs = self._build_messages(messages, committed_prefix_len)

        body: dict[str, Any] = {
            "model": request.model or self._model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": anthropic_msgs,
        }

        if system_text:
            body["system"] = self._build_system_blocks(system_text, committed_prefix_len)

        # Tools
        if request.tools:
            body["tools"] = self._convert_tools(request.tools)

        logger.debug("Anthropic request: %d messages, prefix=%d", len(anthropic_msgs), committed_prefix_len)

        resp = await self._client.post("/v1/messages", json=body)
        resp.raise_for_status()
        data = resp.json()

        return self._to_openai_response(data, request.model or self._model)

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Prompt construction with cache control
    # ------------------------------------------------------------------

    def _build_system_blocks(
        self, system_text: str, prefix_len: int
    ) -> list[dict[str, Any]]:
        """
        Build system content blocks.  If the system message is part of the
        committed prefix, mark it with ``cache_control``.
        """
        block: dict[str, Any] = {"type": "text", "text": system_text}
        if prefix_len > 0:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]

    def _build_messages(
        self,
        messages: list[ChatMessage],
        prefix_len: int,
    ) -> list[dict[str, Any]]:
        """
        Convert OpenAI-style messages to Anthropic format.

        The last message in the committed prefix gets ``cache_control``
        injected, telling Anthropic to cache everything up to (and
        including) that message.
        """
        out: list[dict[str, Any]] = []
        # prefix_len includes the system message which was already split out,
        # so the boundary in the remaining list is (prefix_len - 1) if there
        # was a system message, but we receive the already-stripped list.
        cache_boundary = max(0, prefix_len - 1)  # adjust for stripped system

        for i, msg in enumerate(messages):
            entry = self._convert_message(msg)
            # Inject cache_control at the boundary
            if i == cache_boundary and prefix_len > 0:
                self._inject_cache_control(entry)
            out.append(entry)

        return out

    @staticmethod
    def _inject_cache_control(entry: dict[str, Any]) -> None:
        """
        Inject ``cache_control`` into the content of a message.
        Anthropic expects it on the *last content block*.
        """
        content = entry.get("content")
        if isinstance(content, str):
            entry["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        elif isinstance(content, list) and content:
            content[-1]["cache_control"] = {"type": "ephemeral"}

    @staticmethod
    def _convert_message(msg: ChatMessage) -> dict[str, Any]:
        role = msg.role
        if role == "system":
            role = "user"  # Anthropic uses "user" + system parameter
        entry: dict[str, Any] = {"role": role}
        if isinstance(msg.content, str):
            entry["content"] = msg.content
        elif isinstance(msg.content, list):
            entry["content"] = msg.content
        else:
            entry["content"] = ""
        return entry

    @staticmethod
    def _split_system(
        messages: list[ChatMessage],
    ) -> tuple[str, list[ChatMessage]]:
        """Extract the system message (if any) from the front of the list."""
        system_parts: list[str] = []
        rest: list[ChatMessage] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content if isinstance(m.content, str) else str(m.content))
            else:
                rest.append(m)
        return "\n".join(system_parts), rest

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI tool schemas to Anthropic format."""
        converted: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function", {})
            converted.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })
        return converted

    # ------------------------------------------------------------------
    # Response normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_openai_response(data: dict[str, Any], model: str) -> ChatCompletionResponse:
        """Convert an Anthropic Messages response to OpenAI chat-completion format."""
        # Extract text content
        content_blocks = data.get("content", [])
        text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
        full_text = "\n".join(text_parts)

        # Extract tool calls
        tool_calls: list[dict[str, Any]] = []
        for b in content_blocks:
            if b.get("type") == "tool_use":
                tool_calls.append({
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": json.dumps(b.get("input", {})),
                    },
                })

        msg = ChatMessage(
            role="assistant",
            content=full_text if full_text else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        # Usage
        usage_data = data.get("usage", {})
        cache_read = usage_data.get("cache_read_input_tokens", 0)
        cache_creation = usage_data.get("cache_creation_input_tokens", 0)

        usage = UsageInfo(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=(
                usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0)
            ),
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

        stop_reason = data.get("stop_reason", "end_turn")
        finish = "tool_calls" if stop_reason == "tool_use" else "stop"

        return ChatCompletionResponse(
            model=model,
            choices=[ChatCompletionChoice(message=msg, finish_reason=finish)],
            usage=usage,
        )
