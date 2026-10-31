"""Координаты района: память -> кэш Redis -> очередь. В запросе пользователя сети нет."""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache

import redis.asyncio as aioredis

CACHE_TTL = 60 * 60 * 24 * 365
PENDING_KEY = "geo:pending"
ROAD_FACTOR = 1.3
TABLE_PATH = "data/districts.json"

Point = tuple[float, float, str]
Candidate = tuple[Point, str, bool]   # точка, город, требует подсказки города

# Только явное название города. «Московская» сюда не попадает: в ней нет «москв».
CITY_PATTERNS = {
    "spb": re.compile(r"санкт[\s-]?петербург|петербург|\bспб\b|\bпитер\b|ленинград", re.I),
    "moscow": re.compile(r"\bмск\b|\bмоскв[аыуеой]\b", re.I),
}

# Область вокруг города: агломерация. Проверяется только если города в тексте нет.
REGION_PATTERNS = {
    "spb": re.compile(r"ленинград\w*|лен\s*обл\w*|ленобласт\w*", re.I),
    "moscow": re.compile(r"подмосков\w*|московск\w*|мо\s*обл\w*", re.I),
}


@lru_cache(maxsize=4)
def load_index(path: str = TABLE_PATH) -> dict[str, list[Candidate]]:
    """Алиас -> все записи с этим алиасом. Читается один раз за жизнь процесса."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    index: dict[str, list[Candidate]] = {}
    for entry in data.get("districts", []):
        try:
            point: Point = (float(entry["lat"]), float(entry["lon"]), entry["label"])
            city = str(entry["city"])
        except (KeyError, TypeError, ValueError):
            continue
        strict = bool(entry.get("strict", False))
        for alias in entry.get("aliases", []):
            index.setdefault(alias.lower(), []).append((point, city, strict))
    return index


def detect_city(text: str) -> str | None:
    """Город, названный в тексте явно. Петербург проверяется первым: он точнее."""
    low = text or ""
    for city, pattern in CITY_PATTERNS.items():
        if pattern.search(low):
            return city
    return None


def detect_area(text: str) -> str | None:
    """Агломерация: город или его область. Нужна для карточек «Московская область»."""
    hit = detect_city(text)
    if hit:
        return hit

    low = text or ""
    for area, pattern in REGION_PATTERNS.items():
        if pattern.search(low):
            return area
    return None


def match(
    index: dict[str, list[Candidate]], place: str, city: str | None = None
) -> Point | None:
    """Побеждает самый длинный алиас. Неоднозначность без города -> None, не угадываем."""
    low = (place or "").strip().lower()
    if not low:
        return None

    found: list[tuple[int, Candidate]] = []
    for alias, candidates in index.items():
        if alias in low:
            for candidate in candidates:
                found.append((len(alias), candidate))
    if not found:
        return None

    longest = max(length for length, _ in found)
    pool = [candidate for length, candidate in found if length == longest]

    if city:
        pool = [c for c in pool if c[1] == city]
    else:
        pool = [c for c in pool if not c[2]]

    return pool[0][0] if len(pool) == 1 else None


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """По прямой с коэффициентом дорог. Грубо — этого достаточно для мягкого штрафа."""
    radius = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    straight = 2 * radius * math.asin(math.sqrt(h))
    return round(straight * ROAD_FACTOR, 1)


async def resolve(
    redis: aioredis.Redis,
    place: str,
    city: str | None = None,
    path: str = TABLE_PATH,
) -> Point | None:
    """Агломерация из текста важнее профиля. Промах уходит в очередь, ответа не ждём."""
    low = (place or "").strip().lower()
    if not low:
        return None

    known_city = detect_area(low) or city
    hit = match(load_index(path), low, known_city)
    if hit:
        return hit

    cached = await redis.get(f"geo:{low}")
    if cached:
        item = json.loads(cached)
        return float(item["lat"]), float(item["lon"]), item["label"]

    await redis.sadd(PENDING_KEY, f"{known_city or '-'}|{low}"[:150])
    return None
