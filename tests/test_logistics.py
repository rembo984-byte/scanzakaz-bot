from app.core.logistics import MAX_PENALTY, assess
from app.core.models import Profile


def prof(**kw) -> Profile:
    base = dict(user_id=1, travel_mode="radius", travel_radius_km=30.0)
    base.update(kw)
    return Profile(**base)


def test_anywhere_ignores_distance():
    v = assess(prof(travel_mode="anywhere"), 500.0)
    assert v.known is True
    assert v.penalty == 0


def test_unknown_distance():
    v = assess(prof(), None)
    assert v.known is False
    assert v.penalty == 0
    assert v.note == ""


def test_inside_radius():
    v = assess(prof(), 20.0)
    assert v.penalty == 0
    assert v.travel_km == 40.0
    assert "в пределах радиуса" in v.note


def test_exactly_on_radius():
    v = assess(prof(), 30.0)
    assert v.penalty == 0


def test_just_over_radius():
    v = assess(prof(), 50.0)
    assert v.penalty == 16


def test_far_is_capped():
    v = assess(prof(), 200.0)
    assert v.penalty == MAX_PENALTY


def test_custom_radius():
    v = assess(prof(travel_radius_km=100.0), 50.0)
    assert v.penalty == 0
