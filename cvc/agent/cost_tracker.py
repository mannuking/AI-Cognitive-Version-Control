"""
cvc.agent.cost_tracker — Per-session cost tracking for LLM API usage.

Calculates running cost based on token counts and per-model pricing.
Shows cost alongside token usage after each response.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Pricing per million tokens (input, output) in USD
# Updated Feb 2026 — adjust as providers change pricing
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-6":      (15.0, 75.0),
    "claude-opus-4-5":      (15.0, 75.0),
    "claude-sonnet-4-6":    (3.0, 15.0),
    "claude-sonnet-4-5":    (3.0, 15.0),
    "claude-haiku-4-5":     (0.80, 4.0),
    # OpenAI
    "gpt-5.3":              (2.50, 10.0),
    "gpt-5.2":              (2.50, 10.0),
    "gpt-5.2-codex":        (2.50, 10.0),
    "gpt-5-mini":           (0.40, 1.60),
    "gpt-4.1":              (2.00, 8.00),
    "gpt-4.1-mini":         (0.40, 1.60),
    "gpt-4.1-nano":         (0.10, 0.40),
    # Google
    "gemini-2.5-flash":     (0.15, 0.60),
    "gemini-2.5-pro":       (1.25, 10.0),
    "gemini-3-pro-preview": (1.25, 10.0),
    "gemini-3-flash-preview": (0.15, 0.60),
    "gemini-2.5-flash-lite": (0.075, 0.30),
    # Ollama — free / local
    "qwen2.5-coder:7b":    (0.0, 0.0),
    "qwen3-coder:30b":     (0.0, 0.0),
    "devstral:24b":         (0.0, 0.0),
    "deepseek-r1:8b":       (0.0, 0.0),
}

# Default pricing if model not found (conservative estimate)
DEFAULT_PRICING = (2.0, 8.0)


def _get_pricing(model: str) -> tuple[float, float]:
    """Get (input_price_per_M, output_price_per_M) for a model."""
    # Exact match first
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Partial match (e.g., "claude-sonnet-4-5-20250514" → "claude-sonnet-4-5")
    for key, pricing in MODEL_PRICING.items():
        if model.startswith(key):
            return pricing
    # Ollama models are free
    if ":" in model:  # Ollama format like "model:size"
        return (0.0, 0.0)
    return DEFAULT_PRICING


@dataclass
class CostTracker:
    """
    Tracks cumulative token usage and cost for a session.
    """
    model: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cost_usd: float = 0.0
    turn_costs: list[float] = field(default_factory=list)

    def add_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
    ) -> float:
        """
        Record token usage and return the cost for this turn.
        Cache-read tokens are typically 90% cheaper than regular input tokens.
        """
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read_tokens

        input_price, output_price = _get_pricing(self.model)

        # Cache-read tokens cost ~10% of regular input
        regular_input = input_tokens - cache_read_tokens
        cache_cost = (cache_read_tokens / 1_000_000) * input_price * 0.1
        input_cost = (max(0, regular_input) / 1_000_000) * input_price
        output_cost = (output_tokens / 1_000_000) * output_price

        turn_cost = input_cost + cache_cost + output_cost
        self.total_cost_usd += turn_cost
        self.turn_costs.append(turn_cost)

        return turn_cost

    def format_cost(self, turn_cost: float | None = None) -> str:
        """Format cost display string."""
        if turn_cost is not None and turn_cost > 0:
            return f"Turn: ${turn_cost:.4f} | Session: ${self.total_cost_usd:.4f}"
        if self.total_cost_usd > 0:
            return f"Session cost: ${self.total_cost_usd:.4f}"
        return "Session cost: $0.00 (local model)"

    def format_summary(self) -> str:
        """Format a full session cost summary."""
        input_price, output_price = _get_pricing(self.model)
        lines = [
            f"Session Cost Summary",
            f"  Model:          {self.model}",
            f"  Input tokens:   {self.total_input_tokens:,}",
            f"  Output tokens:  {self.total_output_tokens:,}",
            f"  Cached tokens:  {self.total_cache_read_tokens:,}",
            f"  Turns:          {len(self.turn_costs)}",
            f"  Total cost:     ${self.total_cost_usd:.4f}",
        ]
        if input_price > 0:
            lines.append(f"  Rate:           ${input_price}/M in, ${output_price}/M out")
        return "\n".join(lines)
