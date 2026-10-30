"""Сколько мастер возьмёт минимум. Только данные карточки, без вопросов клиенту."""
from __future__ import annotations

from app.core.models import Money, Order, Profile


def estimate(profile: Profile, order: Order) -> Money:
    """Максимум из применимых расчётов: минимум работает как порог, не как выбор."""
    candidates: list[Money] = []

    if order.object_m2 and profile.turnkey_rate:
        candidates.append(Money(
            round(order.object_m2 * profile.turnkey_rate),
            "turnkey",
            f"{order.object_m2:g} м² объекта × {profile.turnkey_rate} ₽/м²",
        ))

    if order.area_m2 and profile.area_rate:
        candidates.append(Money(
            round(order.area_m2 * profile.area_rate),
            "area",
            f"{order.area_m2:g} м² × {profile.area_rate} ₽/м²",
        ))

    if profile.min_order_price:
        candidates.append(Money(
            profile.min_order_price,
            "min",
            f"минимум {profile.min_order_price} ₽ за заказ",
        ))

    candidates = [c for c in candidates if c.amount and c.amount > 0]
    if not candidates:
        return Money(None, "none", "не задан ни минимум, ни ставка")

    return max(candidates, key=lambda c: c.amount)


def compare(budget: int | None, money: Money) -> dict:
    """Насколько расчёт отличается от бюджета."""
    if not budget or not money.amount or budget <= 0:
        return {"verdict": "unknown", "delta_pct": None}

    delta = round((money.amount - budget) / budget * 100, 1)
    verdict = "cheaper" if money.amount <= budget else "over"
    return {"verdict": verdict, "delta_pct": delta}
