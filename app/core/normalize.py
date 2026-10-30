"""Разбор текста карточки: суммы, площади, признаки материалов."""
from __future__ import annotations

import re

from app.core.models import MaterialMode

# Символы, которые OCR путает с цифрами. Меняем только внутри чисел.
_OCR_DIGITS = {
    "О": "0", "о": "0", "O": "0", "o": "0",
    "З": "3", "з": "3",
    "l": "1", "I": "1", "|": "1",
}

_NUMISH = re.compile(r"[0-9ОоOoЗзlI|][0-9ОоOoЗзlI|., \u00a0]*[0-9ОоOoЗзlI|]|[0-9]")


def fix_ocr(text: str) -> str:
    """'1 ООО ООО' -> '1 000 000'. Слова не трогает: нужен хотя бы один реальный цифровой символ."""
    def repl(m: re.Match[str]) -> str:
        frag = m.group(0)
        if not any(c.isdigit() for c in frag):
            return frag
        return "".join(_OCR_DIGITS.get(c, c) for c in frag)
    return _NUMISH.sub(repl, text or "")


_AMOUNT_RE = re.compile(
    r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?:[ \u00a0]*(млн|миллион\w*|тыс\w*|к(?![а-яё])|k(?![a-z])))?",
    re.I,
)

_BUDGET_HINT = re.compile(r"бюджет|стоимост|цена|заплат", re.I)
_MATERIALS_LINE = re.compile(r"материал", re.I)


def parse_amount(raw: str) -> int | None:
    """Самая крупная сумма в строке. '1,2 млн' -> 1200000."""
    text = fix_ocr(raw).lower()
    best: int | None = None
    for m in _AMOUNT_RE.finditer(text):
        value = _to_number(m.group(1))
        if value is None:
            continue
        amount = int(round(value * _multiplier(m.group(2) or "")))
        if amount > 0 and (best is None or amount > best):
            best = amount
    return best


def parse_budget(text: str) -> int | None:
    """Строка со словом 'бюджет', минуя строки про материалы."""
    fixed = fix_ocr(text)

    for line in fixed.splitlines():
        if _BUDGET_HINT.search(line) and not _MATERIALS_LINE.search(line):
            amount = parse_amount(line)
            if amount:
                return amount

    if _MATERIALS_LINE.search(fixed) and _EXPLICIT.search(fixed):
        return None

    return parse_amount(fixed)


_AREA_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:м2|м²|кв\.?\s?м|квадрат\w*|m2)",
    re.I,
)


def parse_area(text: str) -> float | None:
    """'60 м2', '2,5 кв.м', '60 квадратов'."""
    m = _AREA_RE.search(fix_ocr(text))
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


_CLIENT_MATERIALS = re.compile(
    r"материал\w*\s+(?:клиент|заказчик|ваш|свои)|материалы\s+есть|со\s+своими\s+материалами",
    re.I,
)
_INCLUSIVE = re.compile(
    r"с\s+материалами|под\s+ключ|материал\w*\s+включен\w*|включая\s+материал",
    re.I,
)
_EXPLICIT = re.compile(
    r"материал\w*\s+(?:на|около|примерно)\s*[\d \u00a0.,]+",
    re.I,
)


def materials_mode(text: str) -> tuple[MaterialMode, int | None]:
    """Режим материалов и, если сумма названа, она же."""
    fixed = fix_ocr(text)
    if _CLIENT_MATERIALS.search(fixed):
        return MaterialMode.CLIENT, None
    m = _EXPLICIT.search(fixed)
    if m:
        return MaterialMode.EXPLICIT, parse_amount(m.group(0))
    if _INCLUSIVE.search(fixed):
        return MaterialMode.INCLUSIVE, None
    return MaterialMode.UNKNOWN, None


def _to_number(num: str) -> float | None:
    n = num.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if n.count(".") > 1:
        return None
    try:
        return float(n)
    except ValueError:
        return None


def _multiplier(word: str) -> int:
    w = word.lower()
    if w.startswith(("млн", "миллион")):
        return 1_000_000
    if w.startswith(("тыс", "к", "k")):
        return 1_000
    return 1
