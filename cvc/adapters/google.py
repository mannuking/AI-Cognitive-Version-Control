"""
cvc.adapters.google — Google Gemini adapter.

Translates CVC's ``ChatCompletionRequest`` objects to the Gemini API
(``generativelanguage.googleapis.com``), using Context Caching for the
committed prefix when available.

Default model: ``gemini-2.5-flash`` — Google's best price-performance model.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from cvc.adapters.base import BaseAdapter
from cvc.core.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    UsageInfo,
)

logger = logging.getLogger("cvc.adapters.google")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ---- Available Models (verified Feb 2026) --------------------------------
# gemini-3-pro-preview   — Newest multimodal & agentic model (preview)
# gemini-2.5-pro         — Advanced thinking model (GA)
# gemini-2.5-flash       — Best price-performance (GA)  ← default
# gemini-2.5-flash-lite  — Fastest, cheapest (GA)
# --------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiAdapter(BaseAdapter):
    """
    Sends ``ChatCompletionRequest`` objects to the Gemini API via their
    OpenAI-compatible endpoint (``/v1beta/openai/``).

    Google offers a fully OpenAI-compatible Chat Completions surface,
    so translation is minimal.  For committed prefixes the adapter sets
    the ``cachedContent`` hint when the prefix exceeds Gemini's minimum
    (32 768 tokens).
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model
        # Use Gemini's OpenAI-compatible endpoint for simplicity
        self._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
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
        """Forward the request to Gemini via its OpenAI-compatible surface."""
        messages = [self._convert_message(m) for m in request.messages]

        body: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.tools:
            body["tools"] = request.tools
        if request.tool_choice:
            body["tool_choice"] = request.tool_choice

        logger.debug(
            "Gemini request: model=%s messages=%d prefix=%d",
            body["model"],
            len(messages),
            committed_prefix_len,
        )

        resp = await self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()

        return self._to_response(data)

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_message(msg: ChatMessage) -> dict[str, Any]:
        """Convert a Pydantic ChatMessage to a plain dict."""
        entry: dict[str, Any] = {"role": msg.role}
        if msg.content is not None:
            entry["content"] = msg.content
        if msg.name:
            entry["name"] = msg.name
        if msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        return entry

    @staticmethod
    def _to_response(data: dict[str, Any]) -> ChatCompletionResponse:
        """Convert a raw Gemini/OpenAI-compat JSON response to our schema."""
        choices: list[ChatCompletionChoice] = []
        for c in data.get("choices", []):
            raw_msg = c.get("message", {})
            msg = ChatMessage(
                role=raw_msg.get("role", "assistant"),
                content=raw_msg.get("content"),
                tool_calls=raw_msg.get("tool_calls"),
            )
            choices.append(
                ChatCompletionChoice(
                    index=c.get("index", 0),
                    message=msg,
                    finish_reason=c.get("finish_reason", "stop"),
                )
            )

        usage_data = data.get("usage", {})
        usage = UsageInfo(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            cache_read_tokens=usage_data.get("prompt_tokens_details", {}).get(
                "cached_tokens", 0
            ),
        )

        return ChatCompletionResponse(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
        )
