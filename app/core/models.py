"""Модели данных. Без внешних зависимостей — импортируются везде."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Segment(str, Enum):
    CLEANING = "cleaning"
    REPAIR = "repair"
    CONSTRUCTION = "construction"


class MaterialMode(str, Enum):
    CLIENT = "client"        # материалы клиента — сравниваем напрямую
    EXPLICIT = "explicit"    # сумма названа — вычитаем из бюджета
    INCLUSIVE = "inclusive"  # включены, сумма не названа — вилка
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Order:
    """То, что вытащили из карточки заказа."""
    budget: int | None = None
    area_m2: float | None = None       # площадь поверхности (плитка, стяжка)
    object_m2: float | None = None     # площадь объекта (под ключ)
    materials: MaterialMode = MaterialMode.UNKNOWN
    materials_sum: int | None = None
    segment: Segment = Segment.REPAIR
    title: str = ""
    raw: str = ""


@dataclass(frozen=True)
class Profile:
    """То, что мастер сказал о себе."""
    user_id: int
    segment: Segment = Segment.REPAIR
    min_order_price: int = 0           # ₽ за заказ, только работа
    area_rate: int | None = None       # ₽/м² поверхности
    turnkey_rate: int | None = None    # ₽/м² объекта
    travel_mode: str = "radius"        # radius | anywhere
    travel_radius_km: float = 30.0
    visit_cost: int = 0                # ₽ за выезд, туда-обратно
    base_lat: float | None = None
    base_lon: float | None = None
    response_cost: int | None = None   # ₽ за отклик
    conversion: float = 0.15
    margin: float | None = None        # None → по сегменту


@dataclass(frozen=True)
class Money:
    """Результат: сумма и то, откуда она взялась."""
    amount: int | None = None
    source: str = "none"               # turnkey | area | min | none
    note: str = ""
