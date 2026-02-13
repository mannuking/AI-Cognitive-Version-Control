"""
cvc.adapters.base — Abstract base class for LLM provider adapters.

Every adapter translates between the OpenAI-compatible ``ChatCompletionRequest``
schema used internally by CVC and the provider's native API format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from cvc.core.models import ChatCompletionRequest, ChatCompletionResponse


class BaseAdapter(ABC):
    """
    Interface contract for all provider adapters.

    Subclasses must implement ``complete()`` and ``close()``.
    """

    @abstractmethod
    async def complete(
        self,
        request: ChatCompletionRequest,
        *,
        committed_prefix_len: int = 0,
    ) -> ChatCompletionResponse:
        """Send a completion request to the provider and return a normalised response."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release any held resources (HTTP clients, etc.)."""
        ...
