from app.core.economics import assess
from app.core.models import Profile, Segment


def prof(**kw) -> Profile:
    base = dict(user_id=1, response_cost=300)
    base.update(kw)
    return Profile(**base)


def test_without_cost():
    e = assess(Profile(user_id=1), 10000)
    assert e.verdict == "unknown"
    assert e.per_order is None


def test_per_order():
    assert assess(prof(), None).per_order == 2000


def test_break_even_repair():
    assert assess(prof(), None).break_even == 6666


def test_break_even_cleaning():
    assert assess(prof(segment=Segment.CLEANING), None).break_even == 4000


def test_break_even_construction():
    assert assess(prof(segment=Segment.CONSTRUCTION), None).break_even == 10000


def test_custom_margin():
    assert assess(prof(margin=0.40), None).break_even == 5000


def test_worth():
    e = assess(prof(), 12000)
    assert e.verdict == "worth"
    assert e.share_pct == 2.5


def test_waste():
    e = assess(prof(), 2500)
    assert e.verdict == "waste"
    assert e.share_pct == 12.0


def test_no_budget_no_verdict():
    e = assess(prof(), None)
    assert e.verdict == "unknown"
    assert e.break_even == 6666
