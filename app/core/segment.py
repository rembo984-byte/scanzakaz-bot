"""Классификация: клининг -> ремонт -> строительство. Порядок важен."""
from __future__ import annotations

import re

from app.core.models import Segment

_CLEANING = re.compile(r"уборк|клининг|химчистк|мыть[её]|помыть|чистк|дезинфекц|озонирован", re.I)
_REPAIR = re.compile(
    r"ремонт|плитк|штукатур|поклей|обои|ламинат|стяжк|сантехник|электрик|смесител|натяжн|гипсокартон",
    re.I,
)
_CONSTRUCTION = re.compile(
    r"фундамент|каркас|сруб|кровл|бан[яию]|пристро|гараж|ангар|коттедж|монолит",
    re.I,
)

_PRIORITY = (Segment.CLEANING, Segment.REPAIR, Segment.CONSTRUCTION)


def classify(text: str) -> tuple[Segment, float]:
    """Сегмент и уверенность 0..1. При равенстве приоритет: клининг, ремонт, стройка."""
    low = text or ""
    scores = {
        Segment.CLEANING: len(_CLEANING.findall(low)),
        Segment.REPAIR: len(_REPAIR.findall(low)),
        Segment.CONSTRUCTION: len(_CONSTRUCTION.findall(low)),
    }
    hits = max(scores.values())
    if hits == 0:
        return Segment.REPAIR, 0.0

    best = max(_PRIORITY, key=lambda s: (scores[s], -_PRIORITY.index(s)))
    return best, round(scores[best] / sum(scores.values()), 2)
