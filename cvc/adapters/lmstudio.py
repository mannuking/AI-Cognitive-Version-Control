"""
cvc.adapters.lmstudio — LM Studio adapter for local open-source models.

LM Studio exposes a **fully OpenAI-compatible** API at ``http://localhost:1234``
(default). This adapter is a thin wrapper that points the OpenAI-compatible
client at the local LM Studio server instead of api.openai.com.

Key differences from Ollama:
    - Uses ``/v1/chat/completions`` (OpenAI compat) — no streaming tool-call
      issues because LM Studio implements the endpoint correctly.
    - Default port: 1234 (vs Ollama's 11434)
    - No API key required — use "lm-studio" as a placeholder if needed.
    - Model identifier is whatever is **loaded** in LM Studio's server tab,
      shown as the model ID in the LM Studio UI.

Recommended coding models to load in LM Studio (Feb 2026):
    - ``qwen2.5-coder-32b-instruct``     — Best overall coding, 32B
    - ``devstral-small-2505``            — Mistral agentic coding model
    - ``deepseek-r1-distill-qwen-32b``   — Reasoning + coding
    - ``codestral-22b-v0.1``             — Mistral dedicated code model
    - ``gemma-3-27b-it``                 — Google's best local model
    - ``mistral-small-3.1-24b-instruct`` — Balanced instruction following
"""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger("cvc.adapters.lmstudio")

DEFAULT_LMSTUDIO_URL = "http://localhost:1234"
DEFAULT_MODEL = "loaded-model"   # LM Studio serves whatever model is loaded


class LMStudioAdapter(BaseAdapter):
    """
    Adapter for LM Studio's OpenAI-compatible local server.

    LM Studio implements ``/v1/chat/completions``, ``/v1/models``, and
    related OpenAI endpoints correctly — including streaming + tool calling
    without the bugs present in Ollama's compat layer.

    The model name should match the identifier shown in LM Studio's
    "Developer" → "Server" tab when a model is loaded.
    """

    def __init__(
        self,
        api_key: str = "lm-studio",   # LM Studio accepts any non-empty value
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_LMSTUDIO_URL,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/v1",
            headers={
                "Content-Type": "application/json",
                # Include Authorization so strict LM Studio builds don't reject
                "Authorization": f"Bearer {api_key or 'lm-studio'}",
            },
            timeout=300.0,
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
        """Forward the request to the local LM Studio instance."""
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
            body["tool_choice"] = "auto"
        if request.tool_choice:
            body["tool_choice"] = request.tool_choice

        logger.debug(
            "LM Studio request: model=%s messages=%d base_url=%s",
            body["model"],
            len(messages),
            self._base_url,
        )

        try:
            resp = await self._client.post("/chat/completions", json=body)
            resp.raise_for_status()
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to LM Studio at {self._base_url}.\n"
                "Make sure LM Studio is running with the local server enabled:\n"
                "  1. Open LM Studio\n"
                "  2. Go to Developer → Local Server\n"
                "  3. Load a model and click 'Start Server'"
            )
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text
            if exc.response.status_code == 400 and "no model" in body_text.lower():
                raise RuntimeError(
                    "No model is loaded in LM Studio.\n"
                    "Load a model in LM Studio's 'Developer → Local Server' tab first."
                ) from exc
            raise RuntimeError(
                f"LM Studio API error {exc.response.status_code}: {body_text}"
            ) from exc

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
        """Convert a raw OpenAI-compat JSON response to our schema."""
        choices: list[ChatCompletionChoice] = []
        for c in data.get("choices", []):
            raw_msg = c.get("message", {})
            # Normalise tool call arguments — may be JSON string in some builds
            tool_calls = raw_msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            fn["arguments"] = json.loads(args)
                        except (json.JSONDecodeError, ValueError):
                            pass
            msg = ChatMessage(
                role=raw_msg.get("role", "assistant"),
                content=raw_msg.get("content"),
                tool_calls=tool_calls,
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
