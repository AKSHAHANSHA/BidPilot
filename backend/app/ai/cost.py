"""Estimated AI cost from token counts.

An estimate for display and budgeting, not billing (`docs/01` §4 strong additions). Rates are a
coarse per-million-token table with a safe default; the point is to give the user and the demo a
sense of spend, and to make cost visible in the analysis record.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

#: USD per 1M tokens (input, output). Approximate; update as pricing changes.
_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
}
_DEFAULT_RATE = (Decimal("2.50"), Decimal("10.00"))
_PER_MILLION = Decimal("1000000")


def estimate_cost(*, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """USD estimate rounded to 4 decimal places. Unknown models use a conservative default."""
    input_rate, output_rate = _RATES.get(model.lower(), _DEFAULT_RATE)
    cost = (
        Decimal(input_tokens) / _PER_MILLION * input_rate
        + Decimal(output_tokens) / _PER_MILLION * output_rate
    )
    return cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
