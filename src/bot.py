import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

async def start(update: Update, context):
    """Команда /start"""
    await update.message.reply_text(
        "🛠️ Добро пожаловать в ScanZakaz!\n"
        "Я анализирую заказы от клиентов по ремонту квартир.\n"
        "Просто отправьте мне текст сообщения клиента."
    )

async def handle_message(update: Update, context):
    """
    Основная функция обработки сообщений.
    Сейчас она просто сохраняет сообщение в Redis и отвечает стандартным текстом.
    Позже сюда будет добавлена вся логика анализа.
    """
    chat_id = str(update.effective_chat.id)
    
    try:
        from redis import Redis
        r = Redis.from_url(REDIS_URL)
        
        order_id = r.incr(f"master:{chat_id}:order_count")
        r.set(f"master:{chat_id}:order_{order_id}", update.message.text)
        
        await update.message.reply_text(
            f"Принято! Анализирую заказ №{order_id}...\n"
            "(Сейчас это заглушка. Реальная аналитика будет добавлена позже.)"
        )
    except Exception as e:
        print(f"Ошибка при работе с Redis: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте ещё раз.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()
