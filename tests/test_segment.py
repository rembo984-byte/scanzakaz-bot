from app.core.models import Segment
from app.core.segment import classify


def test_cleaning():
    seg, conf = classify("Нужна генеральная уборка квартиры 60 м2")
    assert seg is Segment.CLEANING
    assert conf == 1.0


def test_repair():
    seg, _ = classify("Укладка плитки в ванной")
    assert seg is Segment.REPAIR


def test_construction():
    seg, _ = classify("Залить фундамент под баню, каркас")
    assert seg is Segment.CONSTRUCTION


def test_cleaning_wins_tie():
    seg, _ = classify("Уборка после ремонта")
    assert seg is Segment.CLEANING


def test_empty_defaults_to_repair():
    seg, conf = classify("")
    assert seg is Segment.REPAIR
    assert conf == 0.0
