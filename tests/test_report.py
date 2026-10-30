from app.core.economics import ResponseEconomics
from app.core.logistics import LogisticsVerdict
from app.core.materials import MaterialsVerdict
from app.core.models import Money, Order, Profile
from app.core.report import render
from app.core.scoring import assess


def build(econ="worth", mat="pass", mat_note="", penalty=0, log_note="", cost=300):
    profile = Profile(user_id=1, min_order_price=3500)
    order = Order(budget=12000, title="Укладка плитки")
    a = assess(
        profile,
        order,
        money=Money(3500, "min", "минимум 3\u00a0500 ₽ за заказ"),
        materials=MaterialsVerdict(mat, note=mat_note),
        econ=ResponseEconomics(
            verdict=econ, cost=cost, per_order=2000, break_even=6666, share_pct=2.5
        ),
        logistics=LogisticsVerdict(penalty, note=log_note),
    )
    return render(a, order)


def test_verdict_header():
    assert build().startswith("🟢 Брать · 90/100")


def test_title_and_budget():
    assert "Укладка плитки, бюджет 12\u00a0000 ₽" in build()


def test_price_line():
    assert "Ваш расчёт: 3\u00a0500 ₽ (минимум 3\u00a0500 ₽ за заказ)" in build()


def test_worth_line():
    text = build()
    assert "окупается с запасом" in text
    assert "(2,5% чека)" in text


def test_waste_line():
    text = build(econ="waste")
    assert "отклик не окупается" in text
    assert "2\u00a0000 ₽" in text


def test_no_cost_hint():
    assert "Цена отклика не задана" in build(econ="unknown", cost=None)


def test_logistics_only_when_penalty():
    assert "Выезд:" not in build()
    assert "Выезд: 20 км в одну сторону" in build(penalty=16, log_note="20 км в одну сторону")


def test_no_banned_words():
    for econ in ("worth", "waste", "unknown"):
        text = build(
            econ=econ, mat="borderline", mat_note="проходит, если материалы дороже"
        ).lower()
        assert "уточн" not in text
        assert "спроси" not in text
        assert "свяжис" not in text
