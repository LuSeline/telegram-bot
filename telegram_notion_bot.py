import os
import logging
import asyncio
from datetime import datetime
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Добавим Flask для HTTP-сервера
from flask import Flask
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
    
    def create_task(self, title, notes="", source="Telegram", category="Личное"):
        url = "https://api.notion.com/v1/pages"
        
        data = {
            "parent": {"database_id": DATABASE_ID},
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
notion = NotionAPI(NOTION_TOKEN)

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
        result = notion.create_task(
            title=title, 
            notes=notes, 
            category=category,
            source="Telegram"
        )
        
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

def main():
    """Основная функция запуска бота"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не найден!")
        return
    
    if not NOTION_TOKEN:
        logger.error("NOTION_TOKEN не найден!")
        return
        
    if not DATABASE_ID:
        logger.error("DATABASE_ID не найден!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен на Render")
    
    # Запускаем polling
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

# Создаем Flask-приложение для health check
app = Flask(__name__)

@app.route('/')
def health_check():
    return {"status": "ok", "service": "telegram-notion-bot"}

@app.route('/health')
def health():
    return {"status": "healthy"}

def run_flask():
    """Запуск Flask в отдельном потоке"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def main():
    """Основная функция запуска бота"""
    # ... ваша проверка переменных ...
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Создаем и запускаем Telegram-бота
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # ... добавление обработчиков ...
    
    logger.info("🚀 Бот и HTTP-сервер запущены на Render")
    
    # Запускаем polling
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()
