"""Настройки из окружения. Читаются один раз при импорте, .env подхватывается локально."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int = 0) -> int:
    try:
        return int(_str(name) or default)
    except ValueError:
        return default


def _float(name: str, default: float = 0.0) -> float:
    try:
        return float(_str(name) or default)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = _str(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class Settings:
    """Все значения имеют безопасный дефолт: импорт не падает без .env."""

    def __init__(self) -> None:
        # MAX
        self.max_bot_token = _str("MAX_BOT_TOKEN")
        self.max_api_base = _str("MAX_API_BASE", "https://botapi.max.ru")
        self.max_webhook_secret = _str("MAX_WEBHOOK_SECRET")
        self.use_long_polling = _bool("USE_LONG_POLLING", False)

        # GigaChat
        self.gigachat_client_id = _str("GIGACHAT_CLIENT_ID")
        self.gigachat_client_secret = _str("GIGACHAT_CLIENT_SECRET")
        self.gigachat_scope = _str("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.gigachat_model = _str("GIGACHAT_MODEL", "GigaChat")
        self.gigachat_base = _str(
            "GIGACHAT_BASE", "https://gigachat.devices.sberbank.ru/api/v1"
        )

        # Yandex Vision OCR
        self.yandex_api_key = _str("YANDEX_API_KEY")
        self.yandex_folder_id = _str("YANDEX_FOLDER_ID")
        self.yandex_ocr_url = _str(
            "YANDEX_OCR_URL", "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
        )

        # Геокодер: Nominatim, бесплатный
        self.nominatim_url = _str(
            "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
        )
        self.geo_user_agent = _str("GEO_USER_AGENT", "scanzakaz/1.0")

        # Redis
        self.redis_url = _str("REDIS_URL")

        # YooKassa
        self.yookassa_shop_id = _str("YOOKASSA_SHOP_ID")
        self.yookassa_secret_key = _str("YOOKASSA_SECRET_KEY")
        self.yookassa_return_url = _str("YOOKASSA_RETURN_URL")
        self.yookassa_receipt_enabled = _bool("YOOKASSA_RECEIPT_ENABLED", False)

        # Продукт
        self.price_week = _int("PRICE_WEEK", 1490)
        self.price_month = _int("PRICE_MONTH", 4950)
        self.checks_per_day = _int("CHECKS_PER_DAY", 30)
        self.trial_checks = _int("TRIAL_CHECKS", 10)

        # Экономика материалов
        self.labor_share_low = _float("LABOR_SHARE_LOW", 0.55)
        self.labor_share_high = _float("LABOR_SHARE_HIGH", 0.70)
        self.labor_share_buffer = _float("LABOR_SHARE_BUFFER", 1.10)


settings = Settings()
