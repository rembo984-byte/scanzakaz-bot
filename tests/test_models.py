import json

from app.core.models import (
    CITIES,
    MaterialMode,
    Money,
    Order,
    Profile,
    Segment,
)


def test_segment_values():
    assert Segment.CLEANING == "cleaning"
    assert Segment("repair") is Segment.REPAIR


def test_material_mode_values():
    assert MaterialMode.CLIENT == "client"
    assert MaterialMode("unknown") is MaterialMode.UNKNOWN


def test_order_defaults():
    o = Order()
    assert o.budget is None
    assert o.segment is Segment.UNKNOWN
    assert o.materials is MaterialMode.UNKNOWN
    assert o.area_m2 is None and o.object_m2 is None
    assert o.title == "" and o.place == "" and o.city == ""


def test_order_non_positive_budget_is_none():
    assert Order(budget=-100).budget is None
    assert Order(budget=0).budget is None
    assert Order(budget=2500).budget == 2500


def test_order_drops_empty_area():
    assert Order(area_m2=0).area_m2 is None
    assert Order(object_m2=-6).object_m2 is None
    assert Order(area_m2=6).area_m2 == 6.0


def test_order_turnkey_property():
    assert Order(object_m2=60).turnkey is True
    assert Order(area_m2=6).turnkey is False


def test_order_coerces_strings():
    o = Order(segment="cleaning", materials="client")
    assert o.segment is Segment.CLEANING
    assert o.materials is MaterialMode.CLIENT


def test_order_bad_strings_fall_back():
    o = Order(segment="???", materials="???")
    assert o.segment is Segment.UNKNOWN
    assert o.materials is MaterialMode.UNKNOWN


def test_order_city_normalised():
    assert Order(city="Химки").city == "moscow"
    assert Order(city="Московская область").city == "moscow"
    assert Order(city="Всеволожск").city == "spb"
    assert Order(city="Казань").city == ""


def test_money_defaults():
    m = Money()
    assert m.amount is None and m.source == "none" and m.note == ""
    assert m.known is False


def test_money_positional():
    m = Money(3500, "min", "минимум 3 500 ₽ за заказ")
    assert (m.amount, m.source, m.note) == (3500, "min", "минимум 3 500 ₽ за заказ")
    assert m.known is True


def test_money_negative_amount_is_none():
    assert Money(-5, "area").amount is None


def test_profile_defaults():
    p = Profile(user_id=42)
    assert p.segment is Segment.REPAIR
    assert p.city == ""
    assert p.min_order_price == 0
    assert p.area_rate is None and p.turnkey_rate is None
    assert p.travel_mode == "radius"
    assert p.travel_radius_km == 30.0


def test_profile_city_normalised():
    assert Profile(user_id=1, city="  СПб ").city == "spb"
    assert Profile(user_id=1, city="Moscow").city == "moscow"
    assert Profile(user_id=1, city="Казань").city == ""


def test_city_towns_moscow_region():
    assert Profile(user_id=1, city="Химки").city == "moscow"
    assert Profile(user_id=1, city="Мытищи").city == "moscow"
    assert Profile(user_id=1, city="Красногорск").city == "moscow"
    assert Profile(user_id=1, city="Подольск").city == "moscow"


def test_city_towns_leningrad_region():
    assert Profile(user_id=1, city="Всеволожск").city == "spb"
    assert Profile(user_id=1, city="Мурино").city == "spb"
    assert Profile(user_id=1, city="Кудрово").city == "spb"
    assert Profile(user_id=1, city="Гатчина").city == "spb"


def test_city_region_names():
    assert Profile(user_id=1, city="Московская область").city == "moscow"
    assert Profile(user_id=1, city="Подмосковье").city == "moscow"
    assert Profile(user_id=1, city="Ленинградская область").city == "spb"
    assert Profile(user_id=1, city="Ленобласть").city == "spb"


def test_city_prefix_case_and_dash():
    assert Profile(user_id=1, city="г. Химки").city == "moscow"
    assert Profile(user_id=1, city="город Красногорск").city == "moscow"
    assert Profile(user_id=1, city="Санкт-Петербург").city == "spb"
    assert Profile(user_id=1, city="наро-фоминск").city == "moscow"
    assert Profile(user_id=1, city="КОРОЛЁВ").city == "moscow"


def test_city_unknown_stays_empty():
    assert Profile(user_id=1, city="Казань").city == ""
    assert Profile(user_id=1, city="Новосибирск").city == ""
    assert Profile(user_id=1, city="Минск").city == ""


def test_profile_travel_mode_fallback():
    assert Profile(user_id=1, travel_mode="walk").travel_mode == "radius"
    assert Profile(user_id=1, travel_mode="anywhere").travel_mode == "anywhere"
    assert Profile(user_id=1, travel_mode="region").travel_mode == "region"


def test_profile_radius_fallback():
    assert Profile(user_id=1, travel_radius_km=0).travel_radius_km == 30.0
    assert Profile(user_id=1, travel_radius_km=50).travel_radius_km == 50


def test_covers_same_agglomeration():
    p = Profile(user_id=1, city="moscow", travel_mode="region")
    assert p.covers("moscow") is True
    assert p.covers("Химки") is True
    assert p.covers("Московская область") is True
    assert p.covers("spb") is False


def test_covers_anywhere():
    p = Profile(user_id=1, city="moscow", travel_mode="anywhere")
    assert p.covers("spb") is True


def test_covers_without_city():
    assert Profile(user_id=1, city="").covers("spb") is True


def test_covers_unknown_place():
    p = Profile(user_id=1, city="moscow")
    assert p.covers("") is True
    assert p.covers("Тверь") is True


def test_profile_roundtrip():
    p = Profile(
        user_id=7,
        segment=Segment.CLEANING,
        city="Химки",
        min_order_price=3000,
        travel_mode="region",
        travel_radius_km=25.0,
    )
    assert Profile.from_dict(p.as_dict()) == p


def test_profile_from_dict_ignores_unknown_keys():
    p = Profile.from_dict({"user_id": 5, "no_such_field": 1, "segment": "construction"})
    assert p.user_id == 5
    assert p.segment is Segment.CONSTRUCTION


def test_profile_from_dict_bad_segment():
    assert Profile.from_dict({"user_id": 5, "segment": "???"}).segment is Segment.REPAIR


def test_profile_from_dict_empty():
    assert Profile.from_dict(None) == Profile()
    assert Profile.from_dict({}) == Profile()


def test_profile_as_dict_is_json_ready():
    p = Profile(user_id=1, segment=Segment.CLEANING, city="moscow")
    payload = json.loads(json.dumps(p.as_dict()))
    assert payload["segment"] == "cleaning"
    assert payload["city"] == "moscow"


def test_cities_constant():
    assert CITIES == {"moscow", "spb"}
