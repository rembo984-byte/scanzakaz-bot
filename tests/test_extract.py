from app.core.extract import extract
from app.core.models import MaterialMode, Profile, Segment


def prof(**kw) -> Profile:
    base = dict(user_id=1, min_order_price=3500, area_rate=15000, turnkey_rate=15000)
    base.update(kw)
    return Profile(**base)


def test_budget_and_area():
    order = extract("Укладка плитки\nПлощадь 6 м2\nБюджет 90 000 ₽", prof())
    assert order.budget == 90000
    assert order.area_m2 == 6.0
    assert order.object_m2 is None


def test_turnkey_goes_to_object():
    order = extract("Ремонт квартиры под ключ 60 м2\nБюджет 1 200 000", prof())
    assert order.object_m2 == 60.0
    assert order.area_m2 is None


def test_turnkey_without_rate_falls_back_to_surface():
    order = extract("Ремонт под ключ 60 м2", prof(turnkey_rate=None))
    assert order.area_m2 == 60.0
    assert order.object_m2 is None


def test_segment_detected():
    assert extract("Генеральная уборка квартиры", prof()).segment is Segment.CLEANING


def test_materials_client():
    order = extract("Поклейка обоев\nМатериалы клиента", prof())
    assert order.materials is MaterialMode.CLIENT


def test_materials_explicit_sum():
    order = extract("Ремонт\nМатериалы на 45 000 ₽", prof())
    assert order.materials is MaterialMode.EXPLICIT
    assert order.materials_sum == 45000
    assert order.budget is None


def test_title_is_first_line():
    order = extract("Укладка плитки в ванной\nБюджет 90000", prof())
    assert order.title == "Укладка плитки в ванной"


def test_empty_text():
    order = extract("", prof())
    assert order.budget is None
    assert order.area_m2 is None
    assert order.title == ""


def test_place_detected():
    order = extract("Укладка плитки\nРайон Митино\nБюджет 90000", prof())
    assert "Митино" in order.place


def test_place_empty_when_no_address():
    assert extract("Замена смесителя", prof()).place == ""


def test_place_keeps_full_line():
    order = extract("Ремонт\nМосковская область, Одинцово\nБюджет 90000", prof())
    assert order.place == "Московская область, Одинцово"
def test_no_budget():
    order = extract("Замена смесителя", prof())
    assert order.budget is None
