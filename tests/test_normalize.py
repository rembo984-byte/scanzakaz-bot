from app.core.models import MaterialMode
from app.core.normalize import fix_ocr, materials_mode, parse_amount, parse_area, parse_budget


def test_plain():
    assert parse_amount("15000") == 15000


def test_spaces():
    assert parse_amount("1 200 000 ₽") == 1_200_000


def test_nbsp():
    assert parse_amount("1\u00a0200\u00a0000") == 1_200_000


def test_million_comma():
    assert parse_amount("1,2 млн") == 1_200_000


def test_million_dot():
    assert parse_amount("1.5 млн ₽") == 1_500_000


def test_thousand():
    assert parse_amount("120 тыс") == 120_000


def test_thousand_k():
    assert parse_amount("120к") == 120_000


def test_ocr_zero_in_number():
    assert fix_ocr("1 ООО ООО") == "1 000 000"


def test_ocr_three():
    assert fix_ocr("1 З00 000") == "1 300 000"


def test_ocr_leaves_words():
    assert fix_ocr("ОТДЕЛКА ООО Ромашка") == "ОТДЕЛКА ООО Ромашка"


def test_no_amount():
    assert parse_amount("бюджет не указан") is None


def test_budget_by_hint():
    text = "Укладка плитки\nПлощадь 45 м2\nБюджет 250 000 ₽"
    assert parse_budget(text) == 250_000


def test_budget_fallback_largest():
    text = "Ремонт квартиры\n45 м2\n180000"
    assert parse_budget(text) == 180_000


def test_area_m2():
    assert parse_area("Площадь 45 м2") == 45.0


def test_area_kv_m():
    assert parse_area("2,5 кв.м") == 2.5


def test_area_square_word():
    assert parse_area("60 квадратов") == 60.0


def test_area_none():
    assert parse_area("без площади") is None


def test_materials_client():
    mode, _ = materials_mode("Материалы клиента")
    assert mode is MaterialMode.CLIENT


def test_materials_explicit():
    mode, amount = materials_mode("Материалы на 45 000 ₽")
    assert mode is MaterialMode.EXPLICIT
    assert amount == 45_000


def test_materials_inclusive():
    mode, amount = materials_mode("Нужен ремонт с материалами")
    assert mode is MaterialMode.INCLUSIVE
    assert amount is None

def test_budget_ignores_materials_line():
    text = "Стоимость материалов 45 000 ₽\nБюджет 250 000 ₽"
    assert parse_budget(text) == 250_000


def test_budget_ignores_materials_line():
    text = "Стоимость материалов 45 000 ₽\nБюджет 250 000 ₽"
    assert parse_budget(text) == 250_000


def test_no_budget_when_only_materials_sum():
    assert parse_budget("Ремонт\nМатериалы на 45 000 ₽") is None
