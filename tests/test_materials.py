from app.core.materials import assess
from app.core.models import MaterialMode, Money, Order, Profile, Segment


def prof(segment=Segment.REPAIR, **kw) -> Profile:
    return Profile(user_id=1, segment=segment, min_order_price=3500, **kw)


def test_cleaning_ignored():
    v = assess(
        prof(Segment.CLEANING),
        Order(segment=Segment.CLEANING, budget=5000),
        Money(3500, "min"),
    )
    assert v.verdict == "ignore"


def test_client_pass():
    v = assess(prof(), Order(budget=12000, materials=MaterialMode.CLIENT), Money(3500, "min"))
    assert v.verdict == "pass"
    assert v.work_budget == 12000


def test_client_fail():
    v = assess(prof(), Order(budget=2500, materials=MaterialMode.CLIENT), Money(3500, "min"))
    assert v.verdict == "fail"
    assert v.work_budget == 2500
    assert v.adds_penalty is False


def test_explicit_pass():
    order = Order(budget=250000, materials=MaterialMode.EXPLICIT, materials_sum=45000)
    v = assess(prof(), order, Money(200000, "min"))
    assert v.verdict == "pass"
    assert v.work_budget == 205000


def test_explicit_drains_budget():
    order = Order(budget=50000, materials=MaterialMode.EXPLICIT, materials_sum=60000)
    v = assess(prof(), order, Money(3500, "min"))
    assert v.verdict == "fail"
    assert v.work_budget == 0


def test_inclusive_pass():
    order = Order(budget=1_200_000, materials=MaterialMode.INCLUSIVE)
    v = assess(prof(), order, Money(600000, "min"))
    assert v.verdict == "pass"
    assert v.materials_room == 600000


def test_inclusive_borderline():
    order = Order(budget=1_000_000, materials=MaterialMode.INCLUSIVE)
    v = assess(prof(), order, Money(620000, "min"))
    assert v.verdict == "borderline"
    assert v.materials_room == 380000


def test_inclusive_fail():
    order = Order(budget=1_200_000, materials=MaterialMode.INCLUSIVE)
    v = assess(prof(), order, Money(900000, "min"))
    assert v.verdict == "fail"
    assert v.materials_room == 300000
    assert v.adds_penalty is True


def test_construction_no_verdict():
    order = Order(budget=2_000_000, segment=Segment.CONSTRUCTION, materials=MaterialMode.INCLUSIVE)
    v = assess(prof(Segment.CONSTRUCTION), order, Money(900000, "min"))
    assert v.verdict == "unknown"


def test_unknown_mode_is_neutral():
    v = assess(prof(), Order(budget=5000, materials=MaterialMode.UNKNOWN), Money(3500, "min"))
    assert v.verdict == "unknown"
    assert v.adds_penalty is False


def test_no_budget():
    v = assess(prof(), Order(materials=MaterialMode.INCLUSIVE), Money(3500, "min"))
    assert v.verdict == "unknown"
