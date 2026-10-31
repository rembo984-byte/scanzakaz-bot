"""Координаты района: память -> кэш Redis -> очередь. В запросе пользователя сети нет."""
from __future__ import annotations

import json
import math
from functools import lru_cache

import redis.asyncio as aioredis

CACHE_TTL = 60 * 60 * 24 * 365
PENDING_KEY = "geo:pending"
ROAD_FACTOR = 1.3
TABLE_PATH = "data/districts.json"

Point = tuple[float, float, str]


@lru_cache(maxsize=4)
def load_index(path: str = TABLE_PATH) -> dict[str, Point]:
    """Алиас -> точка. Читается один раз за жизнь процесса."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    index: dict[str, Point] = {}
    for entry in data.get("districts", []):
        try:
            point: Point = (float(entry["lat"]), float(entry["lon"]), entry["label"])
        except (KeyError, TypeError, ValueError):
            continue
        for alias in entry.get("aliases", []):
            index[alias.lower()] = point
    return index


def match(index: dict[str, Point], place: str) -> Point | None:
    """Побеждает самый длинный совпавший алиас: 'приморский район' точнее 'приморск'."""
    low = (place or "").strip().lower()
    if not low:
        return None

    best_len = 0
    best: Point | None = None
    for alias, point in index.items():
        if alias in low and len(alias) > best_len:
            best_len = len(alias)
            best = point
    return best


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """По прямой с коэффициентом дорог. Грубо — этого достаточно для мягкого штрафа."""
    radius = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    straight = 2 * radius * math.asin(math.sqrt(h))
    return round(straight * ROAD_FACTOR, 1)


async def resolve(redis: aioredis.Redis, place: str) -> Point | None:
    """Сначала память, потом кэш. При промахе — в очередь, возврат None без сети."""
    low = (place or "").strip().lower()
    if not low:
        return None

    hit = match(load_index(), low)
    if hit:
        return hit

    cached = await redis.get(f"geo:{low}")
    if cached:
        item = json.loads(cached)
        return float(item["lat"]), float(item["lon"]), item["label"]

    await redis.sadd(PENDING_KEY, low[:120])
    return None
