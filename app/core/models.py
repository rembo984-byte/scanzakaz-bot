"""Модели домена. Ничего не знают про сеть, MAX и Redis."""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum


class Segment(str, Enum):
    CLEANING = "cleaning"
    REPAIR = "repair"
    CONSTRUCTION = "construction"
    UNKNOWN = "unknown"


class MaterialMode(str, Enum):
    CLIENT = "client"        # материалы клиента
    EXPLICIT = "explicit"    # сумма материалов названа числом
    INCLUSIVE = "inclusive"  # материалы входят в цену, сумма не названа
    UNKNOWN = "unknown"      # в карточке об этом ни слова


CITIES: frozenset[str] = frozenset({"moscow", "spb"})
TRAVEL_MODES = ("radius", "anywhere")


@dataclass(frozen=True)
class Money:
    """Расчёт мастера. amount = None значит «посчитать не удалось»."""

    amount: int | None = None
    source: str = "none"     # min | area | turnkey | none
    note: str = ""

    def __post_init__(self) -> None:
        if self.amount is not None:
            value = int(round(self.amount))
            object.__setattr__(self, "amount", value if value > 0 else None)

    @property
    def known(self) -> bool:
        return bool(self.amount)


@dataclass
class Profile:
    """Настройки мастера. Все поля с дефолтом: профиль можно создать одной строкой."""

    user_id: int = 0
    segment: Segment = Segment.REPAIR
    city: str = ""                    # moscow | spb — где работает мастер
    min_order_price: int = 0          # минимальный чек за заказ
    area_rate: int | None = None      # цена за м² поверхности
    turnkey_rate: int | None = None   # цена за м² объекта под ключ
    response_cost: int = 0            # цена одного отклика
    visit_cost: int = 0               # цена выезда, подсказкой в отчёте
    margin: float = 0.0               # доля прибыли; 0 = взять по сегменту
    conversion: float = 0.0           # конверсия отклика; 0 = взять 0.15
    travel_mode: str = "radius"       # radius | anywhere
    travel_radius_km: float = 30.0

    def __post_init__(self) -> None:
        if isinstance(self.segment, str) and not isinstance(self.segment, Segment):
            try:
                self.segment = Segment(self.segment)
            except ValueError:
                self.segment = Segment.REPAIR

        self.city = (self.city or "").strip().lower()
        if self.city not in CITIES:
            self.city = ""

        if self.travel_mode not in TRAVEL_MODES:
            self.travel_mode = "radius"

        if not self.travel_radius_km or self.travel_radius_km <= 0:
            self.travel_radius_km = 30.0

        # 0 или мусор -> economics возьмёт значение по сегменту
        if not (0 < self.margin <= 1):
            self.margin = 0.0
        if not (0 < self.conversion <= 1):
            self.conversion = 0.0

    def as_dict(self) -> dict:
        """Готово к json.dumps и к Redis: enum-ы уже строками."""
        return {
            "user_id": self.user_id,
            "segment": self.segment.value,
            "city": self.city,
            "min_order_price": self.min_order_price,
            "area_rate": self.area_rate,
            "turnkey_rate": self.turnkey_rate,
            "response_cost": self.response_cost,
            "visit_cost": self.visit_cost,
            "margin": self.margin,
            "conversion": self.conversion,
            "travel_mode": self.travel_mode,
            "travel_radius_km": self.travel_radius_km,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Profile":
        """Лишние ключи игнорируются: старая запись в Redis не сломает чтение."""
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}

        segment = clean.get("segment")
        if isinstance(segment, str) and not isinstance(segment, Segment):
            try:
                clean["segment"] = Segment(segment)
            except ValueError:
                clean["segment"] = Segment.REPAIR

        return cls(**clean)


@dataclass
class Order:
    """Карточка заказа после разбора. Создаётся из текста, нигде не хранится."""

    segment: Segment = Segment.UNKNOWN
    budget: int | None = None
    area_m2: float | None = None       # площадь поверхности
    object_m2: float | None = None     # площадь объекта («под ключ»)
    materials: MaterialMode = MaterialMode.UNKNOWN
    materials_sum: int | None = None
    place: str = ""                    # район или метро из текста
    title: str = ""
    raw: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.segment, str) and not isinstance(self.segment, Segment):
            try:
                self.segment = Segment(self.segment)
            except ValueError:
                self.segment = Segment.UNKNOWN

        if isinstance(self.materials, str) and not isinstance(self.materials, MaterialMode):
            try:
                self.materials = MaterialMode(self.materials)
            except ValueError:
                self.materials = MaterialMode.UNKNOWN

        if self.budget is not None and self.budget <= 0:
            self.budget = None
        if self.area_m2 is not None and self.area_m2 <= 0:
            self.area_m2 = None
        if self.object_m2 is not None and self.object_m2 <= 0:
            self.object_m2 = None
        if self.materials_sum is not None and self.materials_sum <= 0:
            self.materials_sum = None

        self.place = (self.place or "").strip()
        self.title = (self.title or "").strip()

    @property
    def turnkey(self) -> bool:
        """Площадь отнесена к объекту, а не к поверхности."""
        return self.object_m2 is not None
