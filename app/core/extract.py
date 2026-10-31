"""Сборка Order из текста карточки. Только чистая логика: ни сети, ни ключей."""
from __future__ import annotations

import re

from app.core.models import Order, Profile
from app.core.normalize import materials_mode, parse_area, parse_budget
from app.core.segment import classify

_TURNKEY_HINT = re.compile(r"под\s+ключ", re.I)
_PLACE_HINT = re.compile(
    r"район|р-н|метро|улиц|ул\.|проспект|шоссе|переулок|набережн|бульвар|проезд|област|округ",
    re.I,
)
_TITLE_MAX = 60
_PLACE_MAX = 120


def extract(text: str, profile: Profile) -> Order:
    raw = text or ""
    segment, _ = classify(raw)
    area = parse_area(raw)
    surface, obj = _areas(raw, area, profile)
    mode, mat_sum = materials_mode(raw)

    return Order(
        budget=parse_budget(raw),
        area_m2=surface,
        object_m2=obj,
        materials=mode,
        materials_sum=mat_sum,
        segment=segment,
        place=_place(raw),
        title=_title(raw),
        raw=raw,
    )


def _areas(
    text: str, area: float | None, profile: Profile
) -> tuple[float | None, float | None]:
    """Одна и та же цифра — либо площадь поверхности, либо площадь объекта."""
    if area is None:
        return None, None
    if _TURNKEY_HINT.search(text) and profile.turnkey_rate:
        return None, area
    if profile.area_rate:
        return area, None
    if profile.turnkey_rate:
        return None, area
    return area, None


def _place(text: str) -> str:
    """Строка, похожая на адрес. Разбор по районам — в services/geo.py."""
    for line in text.splitlines():
        if _PLACE_HINT.search(line):
            return line.strip()[:_PLACE_MAX]
    return ""


def _title(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip(" ·—-•\t")
        if len(clean) >= 3:
            return clean[:_TITLE_MAX]
    return ""
