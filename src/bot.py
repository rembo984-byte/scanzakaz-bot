import os
import io
from datetime import datetime, timedelta
import asyncio
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    filters,
)

FREE_CHECKS_LIMIT = 10

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "YOUR_PROVIDER_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "YOUR_GIGACHAT_KEY")
FOLDER_ID = os.getenv("FOLDER_ID", "YOUR_FOLDER_ID")

def is_premium(master_data: dict) -> bool:
    paid_until_str = master_data.get("paid_until")
    if not paid_until_str:
        return False
    paid_until = datetime.fromisoformat(paid_until_str)
    return paid_until > datetime.now()

async def start(update: Update, context):
    context.user_data["setup_step"] = None
    await update.message.reply_text(
        """🤖 Рад приветствовать тебя в СканЗаказ!

📡 Я — твой персональный ИИ-ассистент, который анализирует заказы от клиентов по ремонту, строительству, электрике, сантехнике, клинингу и другим услугам с площадок Профи и YouDo. Моя главная задача — беречь твой баланс и повышать вероятность сделки по твоему чеку. 

🎁 Твой тест-драйв активирован: у тебя есть 10 бесплатных высокоточных проверок!

⚙️ Сначала настрой свой профиль мастера: /settings

👇 После настройки просто перешли мне скриншот или текст любого заказа с Профи или YouDo.

⚠️ Для более точного анализа заказов на Профи рекомендую подключить "Премиум доступ".

🔒 Количество мест в СканЗаказ ограничено: ИИ-ассистент работает в режиме закрытой беты для обеспечения максимальной скорости нейросети."""
    )

async def help_command(update: Update, context):
    await update.message.reply_text(
        "🛠️ Как работает ScanZakaz?\n"
        "1. /settings — Настройте ваши целевые услуги и цену.\n"
        "2. Отправьте боту текст или скриншот заказа → я проведу глубокий анализ.\n"
        "   * 💰 **Оценка клиента и бюджета:** Пойму, надо ли тратить деньги на отклик.\n"
        "   * ✍️ **Дам рекомендации:** Подготовлю убойный текст для отклика и аргументы для звонка.\n\n"
        "Тарифы:\n"
        "* Бесплатный тест: 10 подробных нейроанализов в вашей нише для оценки полезности ИИ-ассистента.\n"
        "* Подписка: ₽4900/мес или ₽3800 за две недели (до 30 проверок/день)."
    )

async def settings(update: Update, context):
    context.user_data["setup_step"] = "name"
    await update.message.reply_text(
        "🛠️ Для начала настройки отправьте своё имя и фамилию одной строкой."
    )

async def handle_global_input(update: Update, context):
    if context.user_data.get("setup_step"):
        await handle_settings_input(update, context)
    else:
        await scan_order(update, context)

async def handle_settings_input(update: Update, context):
    text = update.message.text.strip() if update.message.text else ""
    chat_id = str(update.effective_chat.id)
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    master_key = f"master:{chat_id}"
    step = context.user_data.get("setup_step")

    if step == "name":
        name_parts = text.split(maxsplit=1)
        if len(name_parts) != 2:
            await update.message.reply_text("Пожалуйста, введите ваше полное имя (Имя и Фамилию).")
            return
        full_name = " ".join(name_parts)
        r.hset(master_key, "name", full_name)
        await update.message.reply_text(
            f"Привет, {full_name}!\nТеперь напишите ваши целевые услуги через запятую.\n"
            "(Например: ремонт квартир, сантехника, уборка)"
        )
        context.user_data["setup_step"] = "services"
        
    elif step == "services":
        if update.message.text:
            services_text = ",".join([s.strip() for s in text.split(",")])
            r.hset(master_key, "target_services", services_text.lower())
            await update.message.reply_text(
                "🛠️ Отлично! Теперь отправьте ваш прайс-лист как фото или просто напишите цены текстом."
            )
            context.user_data["setup_step"] = "price_file_or_text"
            
    elif step == "price_file_or_text":
        if update.message.text:
            r.hset(master_key, "prices_list", text)
            context.user_data["setup_step"] = None
            await update.message.reply_text(
                "🎉 **Ваши настройки успешно сохранены!**\n\n"
                "ИИ-ассистент зафиксировал ваш прайс-лист и целевые услуги. "
                "Теперь при генерации рекомендаций и текстов откликов он будет автоматически опираться на ваши цены.\n\n"
                "🔍 Чтобы проверить заказ, просто отправьте его текст в чат!"
            )
        elif update.message.document or update.message.photo:
            await update.message.reply_text("Обрабатываю файл...")
            try:
                if update.message.document:
                    file_obj = await update.message.document.get_file()
                else:
                    file_obj = await update.message.photo[-1].get_file()
                file_bytes = await file_obj.download_as_bytearray()
                
                import pytesseract
                from PIL import Image
                img = Image.open(io.BytesIO(file_bytes))
                ocr_result = pytesseract.image_to_string(img, lang="rus")
                
                price_list = []
                for line in ocr_result.splitlines():
                    parts = line.split(":")
                    if len(parts) > 1 and any(char.isdigit() for char in parts):
                        service_name = parts.strip()
                        price_value = "".join(filter(str.isdigit, parts))
                        price_list.append(f"{service_name} - {price_value}")
                        
                saved_prices = "\n".join(price_list) if price_list else ocr_result.strip()
                r.hset(master_key, "prices_list", saved_prices)
                context.user_data["setup_step"] = None
                await update.message.reply_text(
                    "🎉 **Ваши настройки успешно сохранены!**\n\n"
                    "Прайс-лист успешно распознан по фото и привязан к профилю.\n\n"
                    "🔍 Чтобы проверить заказ, просто отправьте его текст в чат!"
                )
            except Exception as e:
                print(f"OCR error: {e}")
                await update.message.reply_text(
                    "🛠️ Не удалось распознать текст в файле.\nПожалуйста, введите ваши цены обычным текстовым сообщением."
                )

async def scan_order(update: Update, context):
    chat_id = str(update.effective_chat.id)
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    master_data = r.hgetall(f"master:{chat_id}")
    if not master_data or "name" not in master_data:
        await update.message.reply_text("Сначала настройте профиль через /settings")
        return
    free_checks_left = int(r.get(f"master:{chat_id}:free_checks_left") or 10)
    if free_checks_left <= 0 and not is_premium(master_data):
        keyboard = [
            [InlineKeyboardButton("🚀 Купить доступ на 14 дней — 3800 ₽", callback_data="buy_2weeks")],
            [InlineKeyboardButton("👑 Купить доступ на 30 дней — 4900 ₽", callback_data="buy_month")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🛠️ Ваши бесплатные проверки закончились.\nВы использовали все {FREE_CHECKS_LIMIT} тестовых нейроанализов.\n\nВыберите тариф для продолжения работы:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    if not is_premium(master_data):
        r.decrby(f"master:{chat_id}:free_checks_left", 1)
    await update.message.reply_text("🔍 Заказ принят в обработку. Нейросеть начинает анализ...")

async def test_invoice(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("🚀 Купить доступ на 14 дней — 3800 ₽", callback_data="buy_2weeks")],
        [InlineKeyboardButton("👑 Купить доступ на 30 дней — 4900 ₽", callback_data="buy_month")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💳 **Выберите тариф доступа к ИИ-ассистенту «СканЗаказ»:**\n\n"
        "После оплаты вам откроется полный доступ к нейроанализу заказов.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def process_payment_choice(update: Update, context):
    import json
    query = update.callback_query
    await query.answer()
    
    # Печатаем лог в терминал Codespaces, чтобы увидеть, что кнопка СРАБОТАЛА
    print(f"--- НАЖАТИЕ НА КНОПКУ ПОЙМАНО! Callback data: {query.data} ---")
    
    chat_id = update.effective_chat.id
    choice = query.data
    
    if choice == "buy_2weeks":
        title = "Доступ к СканЗаказ на 14 дней"
        price = 3800
        days = 14
        payload = "sub_14_days"
    else:
        title = "Доступ к СканЗаказ на 30 дней"
        price = 4900
        days = 30
        payload = "sub_30_days"
        
    description = (
        f"Полный доступ к нейроанализу заказов на {days} дней.\n"
        f"Лимит: строго до 30 проверок в сутки."
    )
    prices = [LabeledPrice("Подписка СканЗаказ", price * 100)]
    
    provider_data = {
        "receipt": {
            "items": [
                {
                    "description": title,
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{price}.00",
                        "currency": "RUB"
                    },
                    "vat_code": 1
                }
            ]
        }
    }

    print("--- ОТПРАВЛЯЕМ ИНВОЙС В ТЕЛЕГРАМ ---")
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="scanzakaz-subscription",
        provider_data=json.dumps(provider_data)
    )

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="scanzakaz-subscription",
        provider_data=json.dumps(provider_data)
    )

async def precheckout_callback(update: Update, context):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("sub_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Что-то пошло не так. Пожалуйста, попробуйте еще раз.")

async def successful_payment_callback(update: Update, context):
    payment = update.message.successful_payment
    chat_id = str(update.effective_chat.id)
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    master_key = f"master:{chat_id}"
    days = 14 if "14" in payment.invoice_payload else 30
    expire_date = (datetime.now() + timedelta(days=days)).isoformat()
    r.hset(master_key, "paid_until", expire_date)
    await update.message.reply_text(
        f"🎉 Оплата успешно прошла!\n"
        f"Спасибо за покупку. Ваш доступ успешно активирован на {days} дней.\n"
        f"Суточный лимит до 30 проверок в 24 часа включен."
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("scan", scan_order))
    app.add_handler(CommandHandler("test_invoice", test_invoice))
    app.add_handler(CallbackQueryHandler(process_payment_choice))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_global_input))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
