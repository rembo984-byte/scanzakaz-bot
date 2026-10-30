from app.core.models import Order, Profile
from app.core.pricing import compare, estimate


def profile(**kw) -> Profile:
    base = dict(user_id=1, min_order_price=3500, area_rate=15000, turnkey_rate=15000)
    base.update(kw)
    return Profile(**base)


def test_no_min_no_rates():
    m = estimate(profile(min_order_price=0, area_rate=None, turnkey_rate=None), Order())
    assert m.amount is None
    assert m.source == "none"


def test_min_only():
    m = estimate(profile(area_rate=None, turnkey_rate=None), Order(budget=5000))
    assert (m.amount, m.source) == (3500, "min")


def test_area_beats_min():
    m = estimate(profile(area_rate=15000), Order(area_m2=2.0))
    assert (m.amount, m.source) == (30000, "area")


def test_min_is_floor():
    m = estimate(profile(min_order_price=5000, area_rate=1000), Order(area_m2=2.0))
    assert (m.amount, m.source) == (5000, "min")


def test_turnkey_wins():
    m = estimate(profile(area_rate=1000, turnkey_rate=15000), Order(area_m2=10, object_m2=60))
    assert (m.amount, m.source) == (900000, "turnkey")


def test_compare_cheaper():
    m = estimate(profile(area_rate=None, turnkey_rate=None), Order())
    v = compare(12000, m)
    assert v["verdict"] == "cheaper"
    assert v["delta_pct"] == -70.8


def test_compare_over():
    m = estimate(profile(area_rate=None, turnkey_rate=None), Order())
    v = compare(2500, m)
    assert v["verdict"] == "over"
    assert v["delta_pct"] == 40.0


def test_compare_unknown():
    m = estimate(profile(), Order())
    assert compare(None, m)["verdict"] == "unknown"
