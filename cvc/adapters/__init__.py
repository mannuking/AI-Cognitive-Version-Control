"""
cvc.adapters — LLM provider adapter registry.

Provides a ``create_adapter()`` factory that returns the correct adapter
based on the CVC_PROVIDER environment variable (or ``CVCConfig.provider``).

Supported providers:
    - ``anthropic``  — Claude Opus 4.6 / Opus 4.5 / Sonnet 4.5 / Haiku 4.5
    - ``openai``     — GPT-5.2 / GPT-5.2-Codex / GPT-5-mini
    - ``google``     — Gemini 2.5 Flash / Gemini 2.5 Pro / Gemini 3 Pro Preview
    - ``ollama``     — Qwen 2.5 Coder / Qwen 3 Coder / DeepSeek-R1 (local)    - ``lmstudio``   — Any model loaded in LM Studio's local server (local)"""

from __future__ import annotations

from cvc.adapters.base import BaseAdapter


# ---- Default models per provider (verified Feb 2026) ---------------------
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "anthropic": {
        "model": "claude-opus-4-6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "model": "gpt-5.2",
        "env_key": "OPENAI_API_KEY",
    },
    "google": {
        "model": "gemini-2.5-flash",
        "env_key": "GOOGLE_API_KEY",
    },
    "ollama": {
        "model": "qwen2.5-coder:7b",
        "env_key": "",  # No API key needed for local models
    },
    "lmstudio": {
        "model": "loaded-model",
        "env_key": "",  # No API key needed — LM Studio accepts any value
    },
}


def create_adapter(
    provider: str,
    api_key: str = "",
    model: str = "",
    base_url: str = "",
) -> BaseAdapter:
    """
    Factory function that returns the correct adapter for the given provider.

    Parameters
    ----------
    provider :
        One of ``"anthropic"``, ``"openai"``, ``"google"``, ``"ollama"``.
    api_key :
        API key for the provider (not needed for Ollama).
    model :
        Model identifier. Falls back to the provider's default.
    base_url :
        Optional base URL override (useful for Ollama on a non-standard port).
    """
    provider = provider.lower().strip()
    defaults = PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        raise ValueError(
            f"Unknown provider: '{provider}'. "
            f"Supported: {', '.join(PROVIDER_DEFAULTS)}"
        )

    model = model or defaults["model"]

    if provider == "anthropic":
        from cvc.adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter(api_key=api_key, model=model)

    elif provider == "openai":
        from cvc.adapters.openai import OpenAIAdapter

        return OpenAIAdapter(api_key=api_key, model=model)

    elif provider == "google":
        from cvc.adapters.google import GeminiAdapter

        return GeminiAdapter(api_key=api_key, model=model)

    elif provider == "ollama":
        from cvc.adapters.ollama import OllamaAdapter

        return OllamaAdapter(
            api_key=api_key,
            model=model,
            base_url=base_url or "http://localhost:11434",
        )

    elif provider == "lmstudio":
        from cvc.adapters.lmstudio import LMStudioAdapter

        return LMStudioAdapter(
            api_key=api_key or "lm-studio",
            model=model,
            base_url=base_url or "http://localhost:1234",
        )

    raise ValueError(f"Unknown provider: '{provider}'")


__all__ = ["BaseAdapter", "create_adapter", "PROVIDER_DEFAULTS"]
