"""Текст отчёта. Единственное место, где рождаются формулировки."""
from __future__ import annotations

from app.core.models import Order
from app.core.scoring import Assessment

EMOJI = {"take": "🟢", "think": "🟡", "skip": "🔴"}
LABEL = {"take": "Брать", "think": "На грани", "skip": "Пропустить"}


def _fmt(value: int) -> str:
    return f"{value:,}".replace(",", "\u00a0")


def render(a: Assessment, order: Order) -> str:
    lines = [f"{EMOJI[a.verdict]} {LABEL[a.verdict]} · {a.score}/100"]

    title = (order.title or "").strip()
    budget = f"{_fmt(order.budget)} ₽" if order.budget else "бюджет не указан"
    lines.append(f"{title}, {budget}" if title else f"Бюджет: {budget}")

    if a.money.amount:
        lines.append(f"Ваш расчёт: {_fmt(a.money.amount)} ₽ ({a.money.note})")
    else:
        lines.append("Ваш расчёт: прайс не задан — /settings")

    if a.materials.note:
        if a.materials.verdict == "ignore":
            lines.append(a.materials.note[:1].upper() + a.materials.note[1:])
        else:
            lines.append(f"Материалы: {a.materials.note}")

    if a.logistics.known and a.logistics.penalty:
        lines.append(f"Выезд: {a.logistics.note}")

    lines.append(_econ(a))

    if a.money.source == "min" and a.money.amount:
        lines.append(f"_Прайс: минимум {_fmt(a.money.amount)} ₽ за заказ_")

    return "\n".join(lines)


def _econ(a: Assessment) -> str:
    e = a.econ
    if not e.cost:
        return "_Цена отклика не задана — экономика отклика не считается_"
    if e.verdict == "waste":
        return (
            f"Отклик {e.cost} ₽. Один заказ стоит вам {_fmt(e.per_order or 0)} ₽ — "
            f"при чеке ниже {_fmt(e.break_even or 0)} ₽ отклик не окупается."
        )
    if e.verdict == "worth":
        share = str(e.share_pct).replace(".", ",")
        return f"Отклик {e.cost} ₽ ({share}% чека) — окупается с запасом."
