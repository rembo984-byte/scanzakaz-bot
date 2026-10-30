"""Логистика: штраф за удалённость. Сети нет — расстояние приходит снаружи."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.models import Profile

MAX_PENALTY = 20
PENALTY_PER_KM = 0.8


@dataclass(frozen=True)
class LogisticsVerdict:
    penalty: int = 0
    distance_km: float | None = None
    travel_km: float | None = None
    known: bool = False
    note: str = ""


def assess(profile: Profile, distance_km: float | None) -> LogisticsVerdict:
    """Поездка = туда-обратно. Штраф растёт только за пределами радиуса."""
    if profile.travel_mode == "anywhere":
        return LogisticsVerdict(0, distance_km, None, True, "выезд по любому расстоянию")

    if distance_km is None:
        return LogisticsVerdict(0, None, None, False, "")

    travel = round(distance_km * 2, 1)
    over = max(0.0, distance_km - profile.travel_radius_km)

    if over == 0:
        return LogisticsVerdict(
            0,
            distance_km,
            travel,
            True,
            f"{distance_km:g} км в одну сторону, в пределах радиуса",
        )

    penalty = round(min(MAX_PENALTY, over * PENALTY_PER_KM))
    return LogisticsVerdict(
        penalty,
        distance_km,
        travel,
        True,
        f"{distance_km:g} км в одну сторону, за радиусом на {over:g} км",
    )
