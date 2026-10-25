import asyncio
import io
import logging
import os
from datetime import datetime, timezone

from redis.asyncio import Redis
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)


# -------------------- Настройки --------------------

FREE_CHECKS_LIMIT = 10
DAILY_CHECKS_LIMIT = 30
MAX_IMAGE_BYTES = 10 * 1024 * 1024

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
).strip()

# Установите True только после реализации analyze_order().
ANALYSIS_ENABLED = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def positive_env_int(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return 0

    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} должен содержать целое положительное число"
        ) from exc

    if value <= 0:
        raise RuntimeError(f"{name} должен быть больше нуля")

    return value


PLANS = {
    "sub_14_days": {
        "days": 14,
        "title": "СканЗаказ — доступ на 14 дней",
        "stars": positive_env_int("STARS_PRICE_14"),
    },
    "sub_30_days": {
        "days": 30,
        "title": "СканЗаказ — доступ на 30 дней",
        "stars": positive_env_int("STARS_PRICE_30"),
    },
}


START_TEXT = """🤖 Рад приветствовать тебя в СканЗаказ!

📡 Я — твой персональный ИИ-ассистент, который анализирует заказы от клиентов по ремонту, строительству, электрике, сантехнике, клинингу и другим услугам с площадок Профи и YouDo. Моя главная задача — беречь твой баланс и повышать вероятность сделки по твоему чеку.

🎁 Твой тест-драйв активирован: у тебя есть 10 бесплатных высокоточных проверок!

⚙️ Сначала настрой свой профиль мастера: /settings

👇 После настройки просто перешли мне скриншот или текст любого заказа с Профи или YouDo."""


SETTINGS_TEXT = """⚠️ Для более точного анализа заказов на Профи рекомендую подключить "Премиум доступ".

🔒 Количество мест в СканЗаказ ограничено: ИИ-ассистент работает в режиме закрытой беты для обеспечения максимальной скорости нейросети.

🛠️ Настроим профиль мастера.

Отправьте своё имя и фамилию одной строкой.

Для отмены настройки: /cancel"""


# -------------------- Redis --------------------

def redis_client(context: ContextTypes.DEFAULT_TYPE) -> Redis:
    return context.application.bot_data["redis"]


def master_key(user_id: int) -> str:
    return f"master:{user_id}"


def free_key(user_id: int) -> str:
    return f"master:{user_id}:free_checks_left"


def utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def paid_until_timestamp(value: str | None) -> int:
    """Поддерживает прежние ISO-даты и новые Unix timestamps."""
    if not value:
        return 0

    try:
        return int(value)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value)
            # Старый код сохранял локальное время без часового пояса.
            # Здесь такие даты интерпретируются как UTC.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp())
        except (ValueError, OverflowError):
            logger.warning("Некорректное значение paid_until")
            return 0


async def load_profile(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> dict:
    r = redis_client(context)
    key = master_key(user_id)
    data = await r.hgetall(key)

    old_value = data.get("paid_until")
    if old_value and not old_value.isdigit():
        new_value = str(paid_until_timestamp(old_value))

        # Не перезаписываем подписку, если параллельно прошла оплата.
        await r.eval(
            """
            if redis.call('HGET', KEYS[1], 'paid_until') == ARGV[1] then
                redis.call('HSET', KEYS[1], 'paid_until', ARGV[2])
            end
            return 1
            """,
            1,
            key,
            old_value,
            new_value,
        )
        data = await r.hgetall(key)

    return data


# Атомарное резервирование проверки.
# -1: бесплатные проверки закончились.
# -2: исчерпан дневной лимит.
#  1: списана бесплатная проверка.
#  2: учтена проверка подписчика.
RESERVE_CHECK_LUA = """
local paid_until = tonumber(
    redis.call('HGET', KEYS[1], 'paid_until') or '0'
) or 0

if paid_until > tonumber(ARGV[1]) then
    local used = tonumber(redis.call('GET', KEYS[3]) or '0')

    if used >= tonumber(ARGV[3]) then
        return -2
    end

    redis.call('INCR', KEYS[3])
    redis.call('EXPIRE', KEYS[3], 172800)
    return 2
end

redis.call('SET', KEYS[2], ARGV[2], 'NX')

local remaining = tonumber(redis.call('GET', KEYS[2]))

if remaining <= 0 then
    return -1
end

redis.call('DECR', KEYS[2])
return 1
"""


# Продление и защита от повторной обработки платежа
# выполняются одной атомарной операцией.
APPLY_PAYMENT_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then
    return 0
end

local current = tonumber(
    redis.call('HGET', KEYS[1], 'paid_until') or '0'
) or 0

local now = tonumber(ARGV[1])
local base = math.max(current, now)
local expires = base + tonumber(ARGV[2])

redis.call('HSET', KEYS[1], 'paid_until', tostring(expires))
redis.call('SET', KEYS[2], KEYS[1])

return expires
"""


# -------------------- Общие функции --------------------

async def private_only(update: Update) -> bool:
    if update.effective_chat.type == ChatType.PRIVATE:
        return True

    if update.effective_message:
        await update.effective_message.reply_text(
            "Пожалуйста, используйте бота в личном чате."
        )
    return False


def payment_keyboard() -> InlineKeyboardMarkup | None:
    buttons = []

    for payload, plan in PLANS.items():
        if plan["stars"] > 0:
            buttons.append([
                InlineKeyboardButton(
                    f"Доступ на {plan['days']} дней — "
                    f"{plan['stars']} ⭐",
                    callback_data=f"buy:{payload}",
                )
            ])

    return InlineKeyboardMarkup(buttons) if buttons else None


async def send_long_text(message, text: str):
    # Небольшой запас относительно лимита Telegram.
    for offset in range(0, len(text), 3500):
        await message.reply_text(text[offset:offset + 3500])


# -------------------- Команды --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await private_only(update):
        return

    context.user_data.pop("setup_step", None)
    context.user_data.pop("profile_draft", None)

    user_id = update.effective_user.id
    r = redis_client(context)

    # Повторный /start не восстанавливает бесплатные проверки.
    created = await r.set(
        free_key(user_id),
        FREE_CHECKS_LIMIT,
        nx=True,
    )

    text = START_TEXT

    if not created:
        remaining = max(
            0,
            int(await r.get(free_key(user_id)) or 0),
        )
        text = text.replace(
            "🎁 Твой тест-драйв активирован: у тебя есть "
            "10 бесплатных высокоточных проверок!",
            f"🎁 Осталось бесплатных проверок: {remaining}.",
        )

    await update.message.reply_text(text)


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🛠️ Как пользоваться СканЗаказ\n\n"
        "/settings — настроить профиль, услуги и цены.\n"
        "/cancel — отменить настройку.\n"
        "/status — проверить доступ.\n"
        "/buy — выбрать тариф.\n"
        "/paysupport — помощь по оплате.\n\n"
        "После настройки отправьте текст заказа или фотографию.\n"
        "Бесплатно: 10 проверок.\n"
        "С подпиской: до 30 проверок за календарные сутки UTC."
    )


async def settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await private_only(update):
        return

    context.user_data["setup_step"] = "name"
    context.user_data["profile_draft"] = {}

    await update.message.reply_text(SETTINGS_TEXT)


async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("setup_step", None)
    context.user_data.pop("profile_draft", None)

    await update.message.reply_text(
        "Настройка отменена. Ранее сохранённый профиль не изменён."
    )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await private_only(update):
        return

    user_id = update.effective_user.id
    r = redis_client(context)
    profile = await load_profile(context, user_id)

    await r.set(free_key(user_id), FREE_CHECKS_LIMIT, nx=True)
    remaining = max(0, int(await r.get(free_key(user_id)) or 0))

    expires = paid_until_timestamp(profile.get("paid_until"))

    if expires > utc_timestamp():
        date = datetime.fromtimestamp(
            expires,
            timezone.utc,
        ).strftime("%d.%m.%Y %H:%M UTC")
        access = f"✅ Подписка действует до {date}."
    else:
        access = "Активной подписки нет."

    await update.message.reply_text(
        f"{access}\n"
        f"Бесплатных проверок осталось: {remaining}."
    )


async def paysupport(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    contact = os.getenv("SUPPORT_CONTACT", "").strip()

    await update.message.reply_text(
        f"По вопросам оплаты и возврата: {contact}"
        if contact
        else "Контакт поддержки пока не настроен. Продажа отключена."
    )


# -------------------- Фото и OCR --------------------

def recognize_image(data: bytes) -> str:
    # Зависимости нужны только для распознавания изображений.
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > 25_000_000:
            raise ValueError("Слишком большое разрешение изображения.")

        image.load()

        return pytesseract.image_to_string(
            image,
            lang="rus+eng",
            timeout=30,
        ).strip()


async def extract_text(message) -> str:
    if message.text:
        return message.text.strip()

    if message.photo:
        attachment = message.photo[-1]
    elif message.document:
        attachment = message.document
        mime = attachment.mime_type or ""

        if not mime.startswith("image/"):
            raise ValueError(
                "Пришлите JPG/PNG, фотографию или обычный текст. "
                "PDF и другие документы пока не поддерживаются."
            )
    else:
        raise ValueError("Пришлите текст или изображение.")

    if attachment.file_size and attachment.file_size > MAX_IMAGE_BYTES:
        raise ValueError("Изображение должно быть не больше 10 МБ.")

    file = await attachment.get_file()
    data = bytes(await file.download_as_bytearray())

    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Изображение должно быть не больше 10 МБ.")

    text = await asyncio.to_thread(recognize_image, data)

    if not text:
        raise ValueError(
            "Не удалось найти текст. Пришлите более чёткое фото "
            "или введите данные вручную."
        )

    if message.caption:
        text = f"{message.caption}\n\n{text}"

    return text


# -------------------- Настройка профиля --------------------

async def handle_settings_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    step = context.user_data.get("setup_step")
    draft = context.user_data.setdefault("profile_draft", {})

    if step == "name":
        text = (message.text or "").strip()
        parts = text.split()

        if len(parts) < 2 or len(text) > 150:
            await message.reply_text(
                "Введите имя и фамилию текстом, например: Иван Петров."
            )
            return

        draft["name"] = " ".join(parts)
        context.user_data["setup_step"] = "services"

        await message.reply_text(
            f"Привет, {draft['name']}!\n\n"
            "Напишите целевые услуги через запятую.\n"
            "Например: ремонт квартир, сантехника, уборка."
        )
        return

    if step == "services":
        text = (message.text or "").strip()
        services = [item.strip() for item in text.split(",") if item.strip()]

        if not services or len(text) > 4000:
            await message.reply_text(
                "Введите услуги текстом через запятую, до 4000 символов."
            )
            return

        draft["target_services"] = ", ".join(services)
        context.user_data["setup_step"] = "prices"

        await message.reply_text(
            "Отправьте прайс-лист текстом или изображением.\n"
            "Например:\n"
            "Установка розетки: 800 ₽\n"
            "Замена смесителя: 2000 ₽"
        )
        return

    if step == "prices":
        try:
            prices = await extract_text(message)
        except ValueError as exc:
            await message.reply_text(str(exc))
            return
        except Exception:
            logger.exception("Ошибка распознавания прайса")
            await message.reply_text(
                "Не удалось распознать изображение. "
                "Попробуйте отправить цены текстом."
            )
            return

        if len(prices) > 15000:
            await message.reply_text(
                "Прайс слишком длинный. Сократите его до 15 000 символов."
            )
            return

        draft["prices_list"] = prices

        await redis_client(context).hset(
            master_key(update.effective_user.id),
            mapping=draft,
        )

        context.user_data.pop("setup_step", None)
        context.user_data.pop("profile_draft", None)

        await message.reply_text(
            "🎉 Ваши настройки успешно сохранены!\n\n"
            "Имя, целевые услуги и прайс-лист привязаны к профилю.\n\n"
            "🔍 Теперь отправьте текст или скриншот заказа."
        )
        return

    context.user_data.pop("setup_step", None)
    await message.reply_text("Начните настройку заново: /settings")


# -------------------- Анализ заказов --------------------

async def analyze_order(order_text: str, profile: dict) -> str:
    """
    Здесь должен быть реальный асинхронный вызов нейросети.

    Доступные данные:
        order_text
        profile["name"]
        profile["target_services"]
        profile["prices_list"]

    Функция должна вернуть непустую строку с анализом.
    После реализации установите ANALYSIS_ENABLED = True.
    """
    raise NotImplementedError("API анализа заказов пока не подключён.")


async def scan_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    user_id = update.effective_user.id
    r = redis_client(context)
    profile = await load_profile(context, user_id)

    required = ("name", "target_services", "prices_list")
    if not all(profile.get(field) for field in required):
        await message.reply_text(
            "Сначала полностью настройте профиль через /settings."
        )
        return

    if not ANALYSIS_ENABLED:
        await message.reply_text(
            "🛠️ Анализ заказов пока не подключён.\n"
            "Профиль сохранён. Бесплатные проверки не списаны."
        )
        return

    try:
        order_text = await extract_text(message)
    except ValueError as exc:
        await message.reply_text(str(exc))
        return
    except Exception:
        logger.exception("Ошибка чтения заказа")
        await message.reply_text(
            "Не удалось прочитать изображение. Отправьте заказ текстом."
        )
        return

    if len(order_text) > 15000:
        await message.reply_text(
            "Заказ слишком длинный. Сократите текст до 15 000 символов."
        )
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_key = f"master:{user_id}:daily:{today}"

    reservation = await r.eval(
        RESERVE_CHECK_LUA,
        3,
        master_key(user_id),
        free_key(user_id),
        daily_key,
        utc_timestamp(),
        FREE_CHECKS_LIMIT,
        DAILY_CHECKS_LIMIT,
    )

    if reservation == -1:
        await message.reply_text(
            "Бесплатные проверки закончились. Тарифы доступны: /buy"
        )
        return

    if reservation == -2:
        await message.reply_text(
            "Дневной лимит исчерпан: 30 проверок.\n"
            "Он обновится в 00:00 UTC."
        )
        return

    try:
        await message.reply_text("🔍 Анализирую заказ…")

        result = await asyncio.wait_for(
            analyze_order(order_text, profile),
            timeout=120,
        )

        if not isinstance(result, str) or not result.strip():
            raise ValueError("Нейросеть вернула пустой результат")

        await send_long_text(message, result.strip())

    except Exception:
        logger.exception("Ошибка анализа или доставки результата")

        # Возвращаем зарезервированную проверку.
        if reservation == 1:
            await r.incr(free_key(user_id))
        else:
            await r.eval(
                """
                local value = tonumber(redis.call('GET', KEYS[1]) or '0')
                if value > 0 then
                    redis.call('DECR', KEYS[1])
                end
                return 1
                """,
                1,
                daily_key,
            )

        await message.reply_text(
            "Не удалось завершить анализ. Проверка возвращена."
        )


async def handle_global_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await private_only(update):
        return

    if context.user_data.get("setup_step"):
        await handle_settings_input(update, context)
    else:
        await scan_order(update, context)


async def scan_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Отправьте заказ отдельным текстовым сообщением или фотографией."
    )


# -------------------- Оплата Telegram Stars --------------------

def sales_enabled() -> bool:
    return (
        ANALYSIS_ENABLED
        and bool(os.getenv("SUPPORT_CONTACT", "").strip())
    )


async def buy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await private_only(update):
        return

    keyboard = payment_keyboard()

    if not sales_enabled() or keyboard is None:
        await update.message.reply_text(
            "🛠️ Продажа доступа пока не включена."
        )
        return

    await update.message.reply_text(
        "💳 Выберите срок доступа к СканЗаказ.\n\n"
        "Оплата — Telegram Stars.\n"
        "Подписка без автоматического продления.\n"
        "Лимит: до 30 проверок за календарные сутки UTC.\n\n"
        "Вопросы по оплате: /paysupport",
        reply_markup=keyboard,
    )


async def process_payment_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    if not await private_only(update):
        return

    payload = query.data.removeprefix("buy:")
    plan = PLANS.get(payload)

    if (
        not sales_enabled()
        or not plan
        or plan["stars"] <= 0
    ):
        await query.message.reply_text(
            "Этот тариф сейчас недоступен."
        )
        return

    try:
        # Для Stars нужен пустой provider_token.
        # Сумма — целое количество звёзд, без умножения на 100.
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=plan["title"],
            description=(
                f"Доступ на {plan['days']} дней. "
                "До 30 проверок за календарные сутки UTC. "
                "Без автоматического продления."
            ),
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=plan["title"],
                    amount=plan["stars"],
                )
            ],
        )
    except TelegramError:
        logger.exception("Не удалось создать счёт")
        await query.message.reply_text(
            "Не удалось создать счёт. Попробуйте позже."
        )


async def precheckout_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.pre_checkout_query
    plan = PLANS.get(query.invoice_payload)

    valid = (
        sales_enabled()
        and plan is not None
        and plan["stars"] > 0
        and query.currency == "XTR"
        and query.total_amount == plan["stars"]
    )

    if valid:
        await query.answer(ok=True)
    else:
        await query.answer(
            ok=False,
            error_message=(
                "Тариф недоступен или его цена изменилась. "
                "Создайте новый счёт через /buy."
            ),
        )


async def successful_payment_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    payment = update.message.successful_payment
    plan = PLANS.get(payment.invoice_payload)

    # Это уже состоявшийся платёж.
    # Изменение цены после pre-checkout не отменяет выдачу доступа.
    if not plan or payment.currency != "XTR":
        logger.error("Получен платёж с неизвестным тарифом или валютой")
        await update.message.reply_text(
            "Платёж получен, но тариф не распознан. "
            "Обратитесь в поддержку: /paysupport"
        )
        return

    user_id = update.effective_user.id
    await load_profile(context, user_id)

    expires = await redis_client(context).eval(
        APPLY_PAYMENT_LUA,
        2,
        master_key(user_id),
        f"payment:{payment.telegram_payment_charge_id}",
        utc_timestamp(),
        plan["days"] * 24 * 60 * 60,
    )

    if expires == 0:
        await update.message.reply_text(
            "✅ Этот платёж уже учтён. Проверить доступ: /status"
        )
        return

    date = datetime.fromtimestamp(
        expires,
        timezone.utc,
    ).strftime("%d.%m.%Y %H:%M UTC")

    await update.message.reply_text(
        "🎉 Оплата успешно прошла!\n\n"
        f"Доступ продлён на {plan['days']} дней.\n"
        f"Подписка действует до {date}.\n\n"
        "Лимит: до 30 проверок за календарные сутки UTC."
    )


# -------------------- Запуск и ошибки --------------------

async def on_startup(application):
    r = Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    try:
        await r.ping()
    except Exception:
        await r.aclose()
        raise

    application.bot_data["redis"] = r

    # Не переключаем бота с webhook на polling незаметно.
    webhook = await application.bot.get_webhook_info()
    if webhook.url:
        await r.aclose()
        raise RuntimeError(
            "У бота настроен webhook. Эта версия использует polling. "
            "Сначала остановите webhook-развёртывание и удалите webhook."
        )

    logger.info("Бот запущен; Redis доступен")


async def on_shutdown(application):
    r = application.bot_data.get("redis")
    if r is not None:
        await r.aclose()


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    error = context.error
    logger.error(
        "Необработанная ошибка",
        exc_info=(type(error), error, error.__traceback__),
    )

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Произошла техническая ошибка. Попробуйте позже.\n"
                "Если оплата уже списана, не оплачивайте повторно: "
                "обратитесь в /paysupport."
            )
        except TelegramError:
            logger.warning("Не удалось отправить сообщение об ошибке")


def main():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        raise RuntimeError("Задайте TELEGRAM_TOKEN в окружении")

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("paysupport", paysupport))

    # Старое имя команды оставлено как псевдоним меню тарифов.
    # Само по себе оно НЕ включает тестовый режим оплаты.
    application.add_handler(CommandHandler("test_invoice", buy))

    application.add_handler(
        CallbackQueryHandler(
            process_payment_choice,
            pattern=r"^buy:sub_(14|30)_days$",
        )
    )
    application.add_handler(
        PreCheckoutQueryHandler(precheckout_callback)
    )
    application.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            successful_payment_callback,
        )
    )
    application.add_handler(
        MessageHandler(
            (
                filters.TEXT
                | filters.PHOTO
                | filters.Document.ALL
            )
            & ~filters.COMMAND,
            handle_global_input,
        )
    )

    application.add_error_handler(error_handler)

    application.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
            "pre_checkout_query",
        ],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
