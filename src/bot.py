import os
from datetime import datetime, timedelta
import asyncio  # Для асинхронных запросов
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

# Константы
FREE_CHECKS_LIMIT = 10  # Количество бесплатных проверок

# Заглушки для локального тестирования; замените на реальные ключи из Vercel
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")  # Локальный тест
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "YOUR_GIGACHAT_KEY")
FOLDER_ID = os.getenv("FOLDER_ID", "YOUR_FOLDER_ID")

# Проверка статуса подписки мастера
def is_premium(master_data: dict) -> bool:
    """Проверяет, активна ли платная подписка"""
    paid_until_str = master_data.get("paid_until")
    if not paid_until_str:
        return False
    
    paid_until = datetime.fromisoformat(paid_until_str)
    now = datetime.now()
    return paid_until > now

###############################################################################
# Базовые команды бота
###############################################################################

async def start(update: Update, context):
    await update.message.reply_text(
        "🛠️ Добро пожаловать в ScanZakaz!\n"
        "Я анализирую заказы от клиентов по ремонту, строительству, электрике,\n"
        "сантехнике, клинингу и другим услугам.\n\n"
        "/settings — Настройте ваши цены и услуги\n"
        "/scan [текст] — Отправьте заказ клиента для анализа"
    )

async def help_command(update: Update, context):
    await update.message.reply_text(
        """
🛠️ Как работает ScanZakaz?
1. /settings — Настройте ваши целевые услуги и цену.
2. /scan + [текст или скриншот заказа] → я проведу глубокий анализ.
   * **Квалификация лидов:** Пойму, надо ли тратить деньги на отклик *(оценка бюджета)*.
   * **Генератор скриптов продаж:** Дам готовый ответ клиенту и аргументы для звонка.
   
Тарифы:
* Бесплатный тест: 10 комплексных анализов в вашей нише для оценки полезности агента.
* Подписка: ₽4900/мес или ₽3800 за две недели (до 30 проверок/день).
"""
    )

###############################################################################
# Команда настройки профиля мастера (/settings)
###############################################################################

async def settings(update: Update, context):
    chat_id = str(update.effective_chat.id)
    r = Redis.from_url(REDIS_URL)
    master_key = f"master:{chat_id}"
    
    # Проверка наличия контекста
    step = context.user_data.get("setup_step")
    if not step:
        await update.message.reply_text(
            "🛠️ Для начала настройки отправьте своё имя и фамилию одной строкой."
        )
        context.user_data["setup_step"] = "name"
        return

async def handle_settings_input(update: Update, context):
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    r = Redis.from_url(REDIS_URL)
    master_key = f"master:{chat_id}"
    
    step = context.user_data.get("setup_step")
    
    if step == "name":
        name_parts = text.split(maxsplit=1)
        if len(name_parts) != 2:
            await update.message.reply_text("Пожалуйста, введите ваше полное имя.")
            return
        
        full_name = " ".join(name_parts)
        r.hset(master_key, "name", full_name)
        
        await update.message.reply_text(
            f"Привет, {full_name}!\nТеперь напишите ваши целевые услуги через запятую или пробел."
        )
        context.user_data["setup_step"] = "services"
    
    elif step == "services":
        services = ",".join(text.split(","))
        r.hset(master_key, "target_services", services.lower())
        
        await update.message.reply_text(
            "Отлично! Теперь укажите вашу цену:\n"
            "- За квадратный метр (например: 900)\n"
            "- Или почасовая ставка (например: 500/ч)"
        )
        context.user_data["setup_step"] = "price"
    
    elif step == "price":
        price_str = text.replace(",", ".").replace("руб.", "").strip()
        try:
            price_value = float(price_str)
            r.hset(master_key, "price_per_sqm", price_value)
            
            # Завершаем настройку
            del context.user_data["setup_step"]
            await update.message.reply_text(
                "🎉 Профиль сохранён!\n"
                f"Ваш текущий профиль: {r.hgetall(master_key)}"
            )
        except ValueError:
            await update.message.reply_text("Введите число без лишних символов.")

###############################################################################
# Основная команда анализа заказов (/scan)
###############################################################################

async def scan_order(update: Update, context):
    """
    Анализирует текстовый запрос клиента.
    Если бесплатные чеки закончились — предлагает купить премиум-подписку.
    """
    chat_id = str(update.effective_chat.id)
    r = Redis.from_url(REDIS_URL)
    master_data = r.hgetall(f"master:{chat_id}")
    
    # ❗️ ВСТАВЬТЕ ЭТОТ БЛОК ПРОВЕРКИ ✅
    free_checks_left = int(r.get(f"master:{chat_id}:free_checks_left") or 0)
    if free_checks_left <= 0 and not is_premium(master_data):
        keyboard = [
            [InlineKeyboardButton("Купить две недели", callback_data="buy_2weeks")],
            [InlineKeyboardButton("Купить месяц", callback_data="buy_month")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🛠️ Ваши бесплатные проверки закончились.\n"
            f"Вы использовали все {FREE_CHECKS_LIMIT} комплексных анализов.\n\n"
            "Выберите тариф:\n"
            "- Две недели (₽3800)\n"
            "- Месяц (₽4900)",
            reply_markout=reply_markup,
            parse_mode='Markdown'
        )
        return  # Блокируем дальнейший анализ!

    # ВАША ЛОГИКА АНАЛИЗА НАЧИНАЕТСЯ ЗДЕСЬ
    # Здесь вы делаете реальный запрос в GigaChat с вашим системным промтом A2+
    # И отправляете результат мастеру
