"""Экономика отклика: во что обходится один заказ и при каком чеке это окупается."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.models import Profile, Segment

DEFAULT_CONVERSION = 0.15
SEGMENT_MARGIN = {
    Segment.CLEANING: 0.50,
    Segment.REPAIR: 0.30,
    Segment.CONSTRUCTION: 0.20,
}


@dataclass
class ResponseEconomics:
    cost: int | None = None
    conversion: float = DEFAULT_CONVERSION
    margin: float = 0.30
    per_order: int | None = None
    break_even: int | None = None
    share_pct: float | None = None
    verdict: str = "unknown"          # worth | waste | unknown


def assess(profile: Profile, budget: int | None) -> ResponseEconomics:
    margin = profile.margin or SEGMENT_MARGIN.get(profile.segment, 0.30)
    conversion = profile.conversion or DEFAULT_CONVERSION

    econ = ResponseEconomics(
        cost=profile.response_cost, conversion=conversion, margin=margin
    )
    if not econ.cost:
        return econ

    econ.per_order = int(econ.cost / econ.conversion)
    econ.break_even = int(econ.cost / (econ.conversion * econ.margin))

    if not budget or budget <= 0:
        return econ

    econ.share_pct = round(econ.cost / budget * 100, 1)
    econ.verdict = "waste" if budget < econ.break_even else "worth"
    return econ
