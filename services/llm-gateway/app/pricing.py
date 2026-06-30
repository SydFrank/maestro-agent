"""Token pricing table — drives per-request cost attribution.

Prices are USD per 1M tokens. Update as provider pricing changes; cost metering
is what makes the platform's spend auditable per tenant (a JD requirement:
结果可追溯 / 成本监控).
"""

from __future__ import annotations

# (input_per_mtok, output_per_mtok)
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = _PRICES.get(model, (0.0, 0.0))
    return round(inp * input_tokens / 1e6 + out * output_tokens / 1e6, 6)
