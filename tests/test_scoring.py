from app.core.economics import ResponseEconomics
from app.core.logistics import LogisticsVerdict
from app.core.materials import MaterialsVerdict
from app.core.models import Money, Order, Profile
from app.core.scoring import PENALTY_CAP, assess, verdict_for


def build(
    materials=MaterialsVerdict(mat, adds_penalty=(mat == "fail")),
    budget: int | None,
    price: int,
    mat: str = "pass",
    econ: str = "worth",
    penalty: int = 0,
):
    profile = Profile(user_id=1, min_order_price=3500)
    order = Order(budget=budget)
    return assess(
        profile,
        order,
        money=Money(price, "min"),
        materials=MaterialsVerdict(mat),
        econ=ResponseEconomics(verdict=econ, cost=300),
        logistics=LogisticsVerdict(penalty),
    )


def test_client_fail_not_double_penalized():
    profile = Profile(user_id=1, min_order_price=3500)
    order = Order(budget=2500)
    a = assess(
        profile,
        order,
        money=Money(3500, "min"),
        materials=MaterialsVerdict("fail", adds_penalty=False),
        econ=ResponseEconomics(verdict="waste", cost=300),
        logistics=LogisticsVerdict(0),
    )
    assert a.score == 13
    assert a.verdict == "skip"


def test_verdict_thresholds():
    assert verdict_for(70) == "take"
    assert verdict_for(69) == "think"
    assert verdict_for(45) == "think"
    assert verdict_for(44) == "skip"


def test_ideal_order():
    a = build(12000, 3500)
    assert a.score == 90
    assert a.verdict == "take"


def test_over_budget_think():
    a = build(4000, 3500, econ="waste")
    assert a.score == 63
    assert a.verdict == "think"


def test_floor_at_zero():
    a = build(2500, 3500, mat="fail", econ="waste")
    assert a.score == 0
    assert a.verdict == "skip"


def test_logistics_reduces_to_boundary():
    a = build(12000, 3500, penalty=PENALTY_CAP)
    assert a.score == 70
    assert a.verdict == "take"


def test_penalty_capped_in_scoring():
    a = build(12000, 3500, penalty=99)
    assert a.score == 70


def test_no_budget_no_bonus():
    a = build(None, 3500, econ="unknown")
    assert a.score == 60
    assert a.verdict == "think"


def test_reasons_collected():
    profile = Profile(user_id=1, min_order_price=3500)
    order = Order(budget=12000)
    a = assess(
        profile,
        order,
        money=Money(3500, "min"),
        materials=MaterialsVerdict("pass", note="материалы клиента"),
        econ=ResponseEconomics(verdict="worth", cost=300),
        logistics=LogisticsVerdict(0, note="20 км в одну сторону"),
    )
    assert len(a.reasons) == 3
