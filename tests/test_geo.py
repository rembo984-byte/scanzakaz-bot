import asyncio
import json

from app.services.geo import detect_city, distance_km, load_index, match, resolve


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


ENTRIES = [
    {"city": "moscow", "label": "Хамовники, Москва", "aliases": ["хамовник"],
     "lat": 55.7333, "lon": 37.5733},
    {"city": "spb", "label": "Приморский, СПб", "aliases": ["приморск"],
     "lat": 60.0, "lon": 30.25, "strict": True},
    {"city": "spb", "label": "Приморский район, СПб", "aliases": ["приморский район"],
     "lat": 60.01, "lon": 30.26},
    {"city": "spb", "label": "Красносельский, СПб", "aliases": ["красносельск"],
     "lat": 59.83, "lon": 30.17},
    {"city": "moscow", "label": "Красносельский, Москва", "aliases": ["красносельск"],
     "lat": 55.775, "lon": 37.66},
]


def make_table(tmp_path, entries=ENTRIES) -> str:
    path = tmp_path / "districts.json"
    path.write_text(json.dumps({"districts": entries}, ensure_ascii=False), encoding="utf-8")
    load_index.cache_clear()
    return str(path)


def test_missing_file_gives_empty_index(tmp_path):
    load_index.cache_clear()
    assert load_index(str(tmp_path / "nope.json")) == {}


def test_broken_json_gives_empty_index(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    load_index.cache_clear()
    assert load_index(str(path)) == {}


def test_alias_match(tmp_path):
    index = load_index(make_table(tmp_path))
    point = match(index, "Ремонт в Хамовниках")
    assert point == (55.7333, 37.5733, "Хамовники, Москва")


def test_longest_alias_wins(tmp_path):
    index = load_index(make_table(tmp_path))
    assert match(index, "Приморский район, за городом", "spb")[0] == 60.01


def test_no_match(tmp_path):
    index = load_index(make_table(tmp_path))
    assert match(index, "Тверская область") is None


def test_empty_place(tmp_path):
    index = load_index(make_table(tmp_path))
    assert match(index, "") is None


def test_strict_alias_needs_city(tmp_path):
    index = load_index(make_table(tmp_path))
    assert match(index, "Приморский") is None
    assert match(index, "Приморский", "spb")[0] == 60.0


def test_ambiguous_alias_without_city_is_none(tmp_path):
    index = load_index(make_table(tmp_path))
    assert match(index, "Красносельский") is None


def test_ambiguous_alias_with_city_resolves(tmp_path):
    index = load_index(make_table(tmp_path))
    assert match(index, "Красносельский", "spb")[0] == 59.83
    assert match(index, "Красносельский", "moscow")[0] == 55.775


def test_distance_known_pair():
    d = distance_km(55.7520, 37.6175, 55.7333, 37.5733)
    assert 4.0 < d < 5.0


def test_distance_same_point():
    assert distance_km(55.75, 37.61, 55.75, 37.61) == 0.0


def test_resolve_from_table(tmp_path):
    path = make_table(tmp_path)
    redis = FakeRedis()
    point = asyncio.run(resolve(redis, "Хамовники", "moscow", path))
    assert point[2] == "Хамовники, Москва"
    assert redis.pending == set()


def test_resolve_from_cache(tmp_path):
    path = make_table(tmp_path)
    redis = FakeRedis()
    redis.store["geo:тверь"] = json.dumps({"lat": 56.86, "lon": 35.91, "label": "Тверь"})
    assert asyncio.run(resolve(redis, "Тверь", path=path)) == (56.86, 35.91, "Тверь")


def test_resolve_miss_goes_to_queue(tmp_path):
    path = make_table(tmp_path)
    redis = FakeRedis()
    assert asyncio.run(resolve(redis, "Норильск", "moscow", path)) is None
    assert redis.pending == {"moscow|норильск"}


def test_card_city_beats_profile(tmp_path):
    path = make_table(tmp_path)
    redis = FakeRedis()
    point = asyncio.run(resolve(redis, "Красносельский, Санкт-Петербург", "moscow", path))
    assert point[0] == 59.83


def test_detect_city():
    assert detect_city("Укладка плитки, Москва") == "moscow"
    assert detect_city("м. Пионерская, СПб") == "spb"
    assert detect_city("Ремонт в Хамовниках") is None
    assert detect_city("Подмосковье, Одинцово") is None
    assert detect_city("Санкт-Петербург, Московский район") == "spb"


def test_real_table_loads():
    load_index.cache_clear()
    assert load_index("data/districts.json")


def test_real_table_schema_and_bbox():
    boxes = {
        "moscow": (55.4, 56.0, 37.2, 38.0),
        "spb": (59.7, 60.1, 29.4, 30.8),
    }
    load_index.cache_clear()
    index = load_index("data/districts.json")

    for alias, candidates in index.items():
        assert alias == alias.lower()
        for point, city, _strict in candidates:
            lat, lon, label = point
            assert city in boxes, f"{label}: неизвестный город {city}"
            lat_lo, lat_hi, lon_lo, lon_hi = boxes[city]
            assert lat_lo <= lat <= lat_hi, f"{label}: широта {lat} вне города"
            assert lon_lo <= lon <= lon_hi, f"{label}: долгота {lon} вне города"


def test_real_moskovsky_needs_city():
    load_index.cache_clear()
    index = load_index("data/districts.json")
    assert match(index, "Ремонт, Московская область") is None
    assert match(index, "Московский район, СПб") is None
    assert match(index, "Московский район", "spb")[2] == "Московский, СПб"


def test_detect_area_region():
    assert detect_area("Укладка плитки, Московская область") == "moscow"
    assert detect_area("Московская область, Одинцово") == "moscow"
    assert detect_area("Ленинградская область, Всеволожск") == "spb"
    assert detect_area("Ленобласть, Мурино") == "spb"


def test_detect_area_region_without_city():
    assert detect_area("Подмосковье, Одинцово") == "moscow"
    assert detect_city("Подмосковье, Одинцово") is None


def test_detect_area_keeps_city_first():
    assert detect_area("Санкт-Петербург, Московский район") == "spb"
    assert detect_area("Укладка плитки, Москва") == "moscow"


def test_region_not_confused_with_district():
    index = load_index(make_table(ENTRIES), )
    assert match(index, "Красносельский", "moscow")[0] == 55.775
    assert match(index, "Красносельский", "spb")[0] == 59.83
