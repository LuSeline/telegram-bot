import os
import logging
import time
import asyncio
from datetime import datetime
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request
import threading

# Получаем переменные из окружения
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DATABASE_ID = os.environ.get('DATABASE_ID')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class NotionAPI:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    
    def create_task(self, title, notes="", source="Telegram", category="Личное", database_id=None):
        # Используем переданный database_id или глобальный
        db_id = database_id or DATABASE_ID
        if not db_id:
            logger.error("DATABASE_ID не указан")
            return None
            
        url = "https://api.notion.com/v1/pages"  # Исправлено: убраны пробелы
        
        data = {
            "parent": {"database_id": db_id},
            "properties": {
                "Задача": {
                    "title": [{"text": {"content": title}}]
                },
                "Заметки": {
                    "rich_text": [{"text": {"content": notes}}]
                },
                "Источник": {
                    "select": {"name": source}
                },
                "Категория": {
                    "select": {"name": category}
                },
                "Действие требуется": {"checkbox": True},
                "Обработано": {"checkbox": False}
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            response.raise_for_status()
            logger.info(f"Задача создана: {title}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка Notion API: {e}")
            return None

# Инициализация
notion = NotionAPI(NOTION_TOKEN) if NOTION_TOKEN else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🤖 Бот для Notion Inbox запущен!\n\n"
        "📝 Отправляйте задачи в формате:\n"
        "• Обычно: Купить молоко\n"
        "• С категорией: #работа Сделать отчет\n"
        "• С заметками: Встреча | В офисе в 15:00\n\n"
        "🏷️ Доступные категории:\n"
        "#личное #дом #работа #здоровье #финансы #семья"
    )
    logger.info(f"Пользователь {update.effective_user.first_name} запустил бота")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    try:
        text = update.message.text
        user_name = update.effective_user.first_name or "Пользователь"
        
        # Инициализация переменных
        category = "Личное"
        title = text
        notes = f"Из Telegram: {user_name}"
        
        # Парсинг категорий
        category_map = {
            "#личное": "Личное", "#дом": "Дом", "#работа": "Работа",
            "#здоровье": "Здоровье", "#финансы": "Финансы", "#семья": "Семья"
        }
        
        for tag, cat in category_map.items():
            if text.lower().startswith(tag):
                category = cat
                title = text[len(tag):].strip()
                break
        
        # Парсинг заметок (разделитель |)
        if "|" in title:
            parts = title.split("|", 1)
            title = parts[0].strip()
            notes += f" | {parts[1].strip()}"
        
        # Отправляем уведомление о начале обработки
        processing_msg = await update.message.reply_text("⏳ Добавляю задачу...")
        
        # Создаем задачу в Notion
        if notion and DATABASE_ID:
            result = notion.create_task(
                title=title, 
                notes=notes, 
                category=category,
                source="Telegram",
                database_id=DATABASE_ID
            )
        else:
            result = None
        
        if result:
            await processing_msg.edit_text(
                f"✅ Добавлено в Inbox!\n\n"
                f"📝 **Задача:** {title}\n"
                f"🏷️ **Категория:** {category}\n"
                f"📅 **Время:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            await processing_msg.edit_text(
                "❌ Ошибка при добавлении задачи.\n"
                "Проверьте настройки Notion интеграции."
            )
            
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке сообщения")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

# Flask-приложение для health check и webhook
app = Flask(__name__)

# Глобальная переменная для хранения application
application = None

@app.route('/')
def health_check():
    return {"status": "ok", "service": "telegram-notion-bot"}

@app.route('/health')
def health():
    return {"status": "healthy"}

@app.route('/webhook', methods=['POST'])
def webhook():
    if application:
        update = Update.de_json(request.get_json(), application.bot)
        # Исправлено: используем asyncio для обработки асинхронных функций
        asyncio.run(application.process_update(update))
    return 'OK'

def run_flask():
    """Запуск Flask в отдельном потоке"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def main():
    """Основная функция запуска бота"""
    global application

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не найден!")
        return
    
    if not NOTION_TOKEN:
        logger.error("NOTION_TOKEN не найден!")
        return
        
    if not DATABASE_ID:
        logger.error("DATABASE_ID не найден!")
        return

    try:
        # Создаем приложение
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        # Запускаем Flask в отдельном потоке
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()

        # Устанавливаем webhook
        RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL')
        if RENDER_URL:
            webhook_url = f"{RENDER_URL}/webhook"
            application.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook установлен: {webhook_url}")
        else:
            logger.error("RENDER_EXTERNAL_URL не найден!")
            return

        logger.info("🚀 Бот и HTTP-сервер запущены на Render")

        # Держим основной поток активным
        while True:
            time.sleep(60)

    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()
