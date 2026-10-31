"""Итоговый индекс и вердикт. Собирает всё, что посчитали слои ниже."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.economics import ResponseEconomics
from app.core.logistics import LogisticsVerdict
from app.core.materials import MaterialsVerdict
from app.core.models import Money, Order, Profile

PENALTY_CAP = 20
TAKE_THRESHOLD = 70
THINK_THRESHOLD = 45
MATERIALS_BONUS = 10
MATERIALS_PENALTY = 15
NO_BUDGET_POINTS = 10   # бюджет не назван: не штраф и не потолок вердикта


@dataclass(frozen=True)
class Assessment:
    score: int
    verdict: str            # take | think | skip
    money: Money
    materials: MaterialsVerdict
    econ: ResponseEconomics
    logistics: LogisticsVerdict
    reasons: list[str]


def verdict_for(score: int) -> str:
    if score >= TAKE_THRESHOLD:
        return "take"
    if score >= THINK_THRESHOLD:
        return "think"
    return "skip"


def _budget_points(budget: int | None, money: Money) -> tuple[int, str]:
    """Плюс за укладывание в бюджет. Бюджет не назван — не наказываем за неизвестность."""
    if not money.amount:
        return 0, ""
    if not budget or budget <= 0:
        return NO_BUDGET_POINTS, "бюджет не назван — считаем от вашего минимума"

    delta = (money.amount - budget) / budget
    if delta <= -0.30:
        return 25, f"вы дешевле бюджета на {abs(delta):.0%}"
    if delta <= 0:
        return 15, "ваш расчёт укладывается в бюджет"
    if delta <= 0.20:
        return -10, f"вы дороже бюджета на {delta:.0%}"
    return -25, f"вы дороже бюджета на {delta:.0%}"


def _materials_points(materials: MaterialsVerdict) -> int:
    if materials.verdict == "pass":
        return MATERIALS_BONUS
    if materials.verdict == "fail" and materials.adds_penalty:
        return -MATERIALS_PENALTY
    return 0


def _econ_points(verdict: str) -> int:
    return {"worth": 5, "waste": -12}.get(verdict, 0)


def assess(
    profile: Profile,
    order: Order,
    *,
    money: Money,
    materials: MaterialsVerdict,
    econ: ResponseEconomics,
    logistics: LogisticsVerdict,
) -> Assessment:
    points, budget_note = _budget_points(order.budget, money)

    score = 50 + points
    score += _materials_points(materials)
    score += _econ_points(econ.verdict)
    score -= min(logistics.penalty, PENALTY_CAP)
    score = max(0, min(100, score))

    reasons = [r for r in (budget_note, materials.note, logistics.note) if r]
    return Assessment(
        score=score,
        verdict=verdict_for(score),
        money=money,
        materials=materials,
        econ=econ,
        logistics=logistics,
        reasons=reasons,
    )
