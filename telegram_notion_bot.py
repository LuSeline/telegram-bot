import os
import logging
from datetime import datetime
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Получаем переменные из окружения
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DATABASE_ID = os.environ.get('DATABASE_ID')

# Настройка логирования
logging.basicConfig(level=logging.INFO)

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
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Ошибка Notion API: {e}")
            return None

notion = NotionAPI(NOTION_TOKEN)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот для Notion Inbox запущен!\n\n"
        "Отправляйте задачи в формате:\n"
        "• Обычно: Купить молоко\n"
        "• С категорией: #работа Сделать отчет\n"
        "• С заметками: Встреча | В офисе в 15:00"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_name = update.effective_user.first_name or "Пользователь"
    
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
    
    # Парсинг заметок
    if "|" in title:
        parts = title.split("|", 1)
        title = parts[0].strip()
        notes += f" | {parts[1].strip()}"
    
    result = notion.create_task(title=title, notes=notes, category=category)
    
    if result:
        await update.message.reply_text(
            f"✅ Добавлено в Inbox!\n📝 {title}\n🏷️ {category}"
        )
    else:
        await update.message.reply_text("❌ Ошибка при добавлении задачи")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Для Render нужен polling, не webhook
    print("🚀 Бот запущен на Render")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
