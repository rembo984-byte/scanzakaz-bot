"""Вердикт по материалам. Ни одного вопроса клиенту — только то, что есть в карточке."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.core.models import MaterialMode, Money, Order, Profile, Segment


def fmt(value: int) -> str:
    return f"{value:,}".replace(",", "\u00a0")


@dataclass(frozen=True)
class MaterialsVerdict:
    verdict: str = "unknown"          # pass | borderline | fail | ignore | unknown
    work_budget: int | None = None    # сколько остаётся на работу
    materials_room: int | None = None # сколько остаётся на материалы
    note: str = ""


def assess(profile: Profile, order: Order, money: Money) -> MaterialsVerdict:
    if order.segment is Segment.CLEANING:
        return MaterialsVerdict(
            "ignore", note="клининг: материалы — расходники, в расчёт не входят"
        )

    price = money.amount
    budget = order.budget
    if price is None or not budget or budget <= 0:
        return MaterialsVerdict(
            "unknown", note="нет бюджета или расчёта — вердикт по материалам невозможен"
        )

    if order.segment is Segment.CONSTRUCTION:
        return MaterialsVerdict(
            "unknown", note="стройка: доля материалов непредсказуема, вердикта нет"
        )

    if order.materials is MaterialMode.CLIENT:
        return _direct(price, budget, "материалы клиента — сравниваю работу с бюджетом")

    if order.materials is MaterialMode.EXPLICIT and order.materials_sum:
        work_budget = budget - order.materials_sum
        if work_budget <= 0:
            return MaterialsVerdict(
                "fail",
                work_budget=max(work_budget, 0),
                materials_room=order.materials_sum,
                note=f"материалы {fmt(order.materials_sum)} ₽ съедают бюджет целиком",
            )
        return _direct(
            price,
            work_budget,
            f"материалы {fmt(order.materials_sum)} ₽, на работу остаётся {fmt(work_budget)} ₽",
        )

    if order.materials is MaterialMode.INCLUSIVE:
        return _fork(price, budget)

    return _direct(
        price, budget, "материалы не указаны — считаю, что бюджет только за работу"
    )


def _direct(price: int, budget: int, note: str) -> MaterialsVerdict:
    """Материалы не смешиваются с работой: прямое сравнение."""
    if price <= budget:
        return MaterialsVerdict(
            "pass",
            work_budget=budget,
            note=f"{note}; ваш расчёт {fmt(price)} ₽ — запас {fmt(budget - price)} ₽",
        )
    return MaterialsVerdict(
        "fail",
        work_budget=budget,
        note=f"{note}; ваш расчёт {fmt(price)} ₽ выше на {fmt(price - budget)} ₽",
    )


def _fork(price: int, budget: int) -> MaterialsVerdict:
    """Сумма материалов не названа: вилка доли работ. Считаем только в полосе 55-100%."""
    low = settings.labor_share_low
    high = settings.labor_share_high
    ratio = price / budget
    room = budget - price

    if ratio <= low:
        return MaterialsVerdict(
            "pass",
            work_budget=budget,
            materials_room=room,
            note=(
                f"проходит даже при доле работ {low:.0%}: "
                f"на материалы остаётся до {fmt(room)} ₽"
            ),
        )

    if ratio <= high:
        return MaterialsVerdict(
            "borderline",
            work_budget=budget,
            materials_room=room,
            note=(
                f"проходит, только если материалы дороже {fmt(room)} ₽ "
                f"({room / budget:.0%} бюджета)"
            ),
        )

    return MaterialsVerdict(
        "fail",
        work_budget=price,
        materials_room=max(room, 0),
        note=(
            f"не проходит: на материалы остаётся {fmt(max(room, 0))} ₽ "
            f"({max(room, 0) / budget:.0%} бюджета) — для объекта этого мало"
        ),
    )
