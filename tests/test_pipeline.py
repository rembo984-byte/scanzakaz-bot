from app.core.economics import assess as econ_assess
from app.core.extract import extract
from app.core.logistics import assess as log_assess
from app.core.materials import assess as mat_assess
from app.core.models import Profile, Segment
from app.core.pricing import estimate
from app.core.report import render
from app.core.scoring import assess as score_assess


def prof(**kw) -> Profile:
    base = dict(
        user_id=1,
        segment=Segment.REPAIR,
        min_order_price=3500,
        area_rate=15000,
        turnkey_rate=15000,
        response_cost=300,
        travel_mode="radius",
        travel_radius_km=30.0,
    )
    base.update(kw)
    return Profile(**base)


def run(text: str, profile: Profile, distance_km: float | None = None):
    order = extract(text, profile)
    money = estimate(profile, order)
    a = score_assess(
        profile,
        order,
        money=money,
        materials=mat_assess(profile, order, money),
        econ=econ_assess(profile, order.budget),
        logistics=log_assess(profile, distance_km),
    )
    return a, order


def test_good_order_end_to_end():
    a, order = run(
        "Укладка плитки в ванной\nПлощадь 6 м2\nБюджет 90 000 ₽\nМатериалы клиента",
        prof(),
    )
    assert a.money.amount == 90000
    assert a.score == 80
    assert a.verdict == "take"
    assert "🟢 Брать · 80/100" in render(a, order)


def test_bad_order_end_to_end():
    a, order = run("Замена смесителя\nБюджет 2 500 ₽", prof())
    assert a.money.amount == 3500
    assert a.materials.verdict == "unknown"
    assert a.score == 13
    assert a.verdict == "skip"
    text = render(a, order)
    assert "🔴 Пропустить · 13/100" in text
    assert "отклик не окупается" in text


def test_materials_fail_borderline():
    a, order = run(
        "Ремонт квартиры под ключ 60 м2\nБюджет 1 200 000 ₽\nС материалами", prof()
    )
    assert a.money.amount == 900000
    assert a.materials.verdict == "fail"
    assert a.materials.materials_room == 300000
    assert a.score == 55
    assert a.verdict == "think"
    assert "🟡 На грани · 55/100" in render(a, order)


def test_distance_drops_to_threshold():
    a, _ = run(
        "Укладка плитки в ванной\nПлощадь 6 м2\nБюджет 90 000 ₽\nМатериалы клиента",
        prof(),
        distance_km=100.0,
    )
    assert a.logistics.penalty == 20
    assert a.score == 60
    assert a.verdict == "think"


def test_no_budget_does_not_crash():
    a, order = run("Замена смесителя", prof())
    assert a.money.amount == 3500
    assert a.materials.verdict == "unknown"
    text = render(a, order)
    assert "Порог окупаемости" in text
