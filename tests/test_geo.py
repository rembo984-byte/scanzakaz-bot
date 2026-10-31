import asyncio
import json

from app.services.geo import distance_km, load_index, match, resolve


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.pending: set[str] = set()

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def sadd(self, key, value):
        self.pending.add(value)


def index_of(tmp_path, entries):
    path = tmp_path / "districts.json"
    path.write_text(json.dumps({"districts": entries}, ensure_ascii=False), encoding="utf-8")
    load_index.cache_clear()
    return load_index(str(path))


ENTRIES = [
    {"label": "Хамовники, Москва", "aliases": ["хамовник"], "lat": 55.7333, "lon": 37.5733},
    {"label": "Приморский, СПб", "aliases": ["приморск"], "lat": 60.0, "lon": 30.25},
    {"label": "Приморский район, СПб", "aliases": ["приморский район"], "lat": 60.01, "lon": 30.26},
]


def test_missing_file_gives_empty_index(tmp_path):
    load_index.cache_clear()
    assert load_index(str(tmp_path / "nope.json")) == {}


def test_broken_json_gives_empty_index(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    load_index.cache_clear()
    assert load_index(str(path)) == {}


def test_alias_match(tmp_path):
    point = match(index_of(tmp_path, ENTRIES), "Ремонт в Хамовниках")
    assert point == (55.7333, 37.5733, "Хамовники, Москва")


def test_longest_alias_wins(tmp_path):
    point = match(index_of(tmp_path, ENTRIES), "Приморский район, за городом")
    assert point[0] == 60.01


def test_no_match(tmp_path):
    assert match(index_of(tmp_path, ENTRIES), "Тверская область") is None


def test_empty_place(tmp_path):
    assert match(index_of(tmp_path, ENTRIES), "") is None


def test_distance_known_pair():
    d = distance_km(55.7520, 37.6175, 55.7333, 37.5733)
    assert 4.0 < d < 5.0


def test_distance_same_point():
    assert distance_km(55.75, 37.61, 55.75, 37.61) == 0.0


def test_resolve_from_table(tmp_path):
    load_index.cache_clear()
    index_of(tmp_path, ENTRIES)
    redis = FakeRedis()
    point = asyncio.run(resolve(redis, "Хамовники"))
    assert point[2] == "Хамовники, Москва"
    assert redis.pending == set()


def test_resolve_from_cache(tmp_path):
    load_index.cache_clear()
    index_of(tmp_path, ENTRIES)
    redis = FakeRedis()
    redis.store["geo:тверь"] = json.dumps({"lat": 56.86, "lon": 35.91, "label": "Тверь"})
    point = asyncio.run(resolve(redis, "Тверь"))
    assert point == (56.86, 35.91, "Тверь")


def test_resolve_miss_goes_to_queue(tmp_path):
    load_index.cache_clear()
    index_of(tmp_path, ENTRIES)
    redis = FakeRedis()
    assert asyncio.run(resolve(redis, "Норильск")) is None
    assert redis.pending == {"норильск"}
