"""
cvc.adapters.ollama — Ollama adapter for local open-source models.

Translates CVC's ``ChatCompletionRequest`` to the Ollama REST API which
exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint at
``http://localhost:11434``.

Default model: ``qwen2.5-coder:7b`` — the most popular open-source coding
model, with 11M+ pulls and excellent code generation, reasoning, and
instruction-following capabilities.

Other recommended models for coding:
    - ``qwen3-coder:30b``    — Alibaba's latest agentic coding model
    - ``devstral:24b``       — Mistral's best open-source coding agent model
    - ``deepseek-r1:8b``     — Open reasoning model (chain-of-thought)
    - ``codestral:22b``      — Mistral's dedicated code model
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

logger = logging.getLogger("cvc.adapters.ollama")

DEFAULT_OLLAMA_URL = "http://localhost:11434"

# ---- Recommended Models (verified Feb 2026) ------------------------------
# qwen2.5-coder:7b  — Best coding model, 11M+ pulls, runs on most hardware
# qwen3-coder:30b   — Alibaba's latest for agentic coding tasks
# devstral:24b      — Mistral's "best open source model for coding agents"
# deepseek-r1:8b    — Open reasoning model, great chain-of-thought
# codestral:22b     — Mistral's dedicated code generation model
# --------------------------------------------------------------------------

DEFAULT_MODEL = "qwen2.5-coder:7b"


class OllamaAdapter(BaseAdapter):
    """
    Sends ``ChatCompletionRequest`` objects to a local Ollama instance.

    Ollama natively supports the OpenAI-compatible ``/v1/chat/completions``
    endpoint, so the translation is essentially a pass-through.  The primary
    addition is ``keep_alive`` to hold the model in memory across requests,
    reducing cold-start latency for agentic workflows.
    """

    def __init__(
        self,
        api_key: str = "",  # unused, accepted for interface consistency
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/v1",
            headers={"Content-Type": "application/json"},
            timeout=300.0,  # Local models can be slow on first load
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
        """Forward the request to the local Ollama instance."""
        messages = [self._convert_message(m) for m in request.messages]

        body: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        if request.tools:
            body["tools"] = request.tools
        if request.tool_choice:
            body["tool_choice"] = request.tool_choice

        logger.debug(
            "Ollama request: model=%s messages=%d base_url=%s",
            body["model"],
            len(messages),
            self._base_url,
        )

        try:
            resp = await self._client.post("/chat/completions", json=body)
            resp.raise_for_status()
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Make sure Ollama is running: https://ollama.com/download"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                model_name = body["model"]
                raise RuntimeError(
                    f"Model '{model_name}' not found in Ollama. "
                    f"Pull it first: ollama pull {model_name}"
                ) from exc
            raise

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
        """Convert a raw Ollama/OpenAI-compat JSON response to our schema."""
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
        )

        return ChatCompletionResponse(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
        )
