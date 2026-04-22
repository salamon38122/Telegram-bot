import os
import threading
import logging
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# تهيئة السجلات
logging.basicConfig(level=logging.INFO)

# قراءة التوكن من متغير البيئة
TOKEN = os.environ.get("8717837657:AAEnqE3FLn7K018PKZuwBq3wSNaFfMJiYPE")
if not TOKEN:
    raise ValueError("❌ لم يتم العثور على التوكن! تأكد من إضافة TELEGRAM_TOKEN في إعدادات Render.")

# إنشاء تطبيق Flask
app = Flask(__name__)

# إعداد بوت Telegram
application = Application.builder().token(TOKEN).build()

# ----------------- تعريف أوامر البوت -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('مرحباً! البوت يعمل الآن عبر Render 🚀')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"أنت قلت: {update.message.text}")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ----------------- نقاط النهاية (Endpoints) -----------------
@app.route('/')
def health():
    return "Bot is running!", 200

# ----------------- تشغيل البوت في خلفية -----------------
def run_bot():
    """تشغيل البوت في دورة polling (منفصلة)"""
    application.run_polling()

if __name__ == "__main__":
    # تشغيل البوت في thread منفصل
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    # تشغيل خادم Flask على المنفذ المطلوب
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
