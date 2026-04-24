#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import asyncio
import logging
import threading
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

from flask import Flask, jsonify
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# محاولة استيراد nest_asyncio لحل مشكلة حلقات asyncio المتداخلة
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

# إعداد نظام تسجيل الأخطاء
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعدادات المسارات
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# إنشاء تطبيق Flask
app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({"status": "alive", "message": "Bot is running 24/7"})

@app.route('/health')
def health():
    return jsonify({"status": "ok", "uptime": "continuous"})

# ----------------- دوال مساعدة -----------------
def is_valid_url(url: str) -> bool:
    """التحقق من صحة الرابط."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

async def cleanup_old_files(directory: Path, max_age_hours: int = 24):
    """حذف الملفات القديمة لتوفير المساحة."""
    now = datetime.now()
    if not directory.exists():
        return
    for file_path in directory.glob("*"):
        if file_path.is_file():
            file_age = now - datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_age.total_seconds() > max_age_hours * 3600:
                try:
                    file_path.unlink()
                    logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")

async def download_media(url: str, chat_id: int, is_audio: bool = False, update: Update = None) -> str:
    """
    تحميل الوسائط باستخدام yt-dlp وإرجاع مسار الملف.
    """
    output_template = "%(title)s.%(ext)s"
    download_path = DOWNLOAD_DIR / f"{chat_id}"
    download_path.mkdir(exist_ok=True, parents=True)

    ydl_opts = {
        'outtmpl': str(download_path / output_template),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
    }

    if is_audio:
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        ydl_opts.update({
            'format': 'best[height<=720]/best',
        })

    # إضافة معالج التقدم في حال وجود كائن التحديث
    if update:
        last_progress = {'percent': 0}

        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    percent_str = d.get('_percent_str', '0%').strip('%')
                    if '%' in percent_str:
                        percent_str = percent_str.replace('%', '')
                    try:
                        percent_float = float(percent_str)
                        if percent_float - last_progress['percent'] >= 10:
                            last_progress['percent'] = percent_float
                            asyncio.create_task(update.message.reply_text(f"🔄 جاري التحميل: {percent_float:.1f}%"))
                    except ValueError:
                        pass
                except:
                    pass
            elif d['status'] == 'finished':
                asyncio.create_task(update.message.reply_text("✅ تم التحميل! جاري المعالجة والإرسال..."))

        ydl_opts['progress_hooks'] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            filename = ydl.prepare_filename(info)
            if is_audio:
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return filename
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        if update:
            await update.message.reply_text(f"❌ فشل التحميل: {str(e)[:100]}")
        return None

# ----------------- أوامر البوت -----------------
async def start(update: Update, context) -> None:
    """رسالة الترحيب."""
    await update.message.reply_text(
        "🎬 **مرحباً بك في بوت تحميل الفيديوهات!**\n\n"
        "أرسل لي رابطاً من أي منصة وسأقوم بتحميل الفيديو لك.\n\n"
        "**الأوامر المتاحة:**\n"
        "/start - عرض هذه الرسالة\n"
        "/audio <رابط> - تحميل الصوت فقط بصيغة MP3\n"
        "/help - عرض المساعدة",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context) -> None:
    """عرض تعليمات الاستخدام."""
    await update.message.reply_text(
        "📌 **كيفية الاستخدام:**\n"
        "1. أرسل رابط الفيديو\n"
        "2. انتظر حتى يتم التحميل والإرسال\n"
        "3. استخدم /audio قبل الرابط لتحميل الصوت فقط\n\n"
        "**المنصات المدعومة:**\n"
        "✅ YouTube, Instagram, TikTok, Twitter/X, Facebook, Reddit, Twitch, Vimeo, SoundCloud وغيرها الكثير",
        parse_mode='Markdown'
    )

async def handle_audio(update: Update, context) -> None:
    """معالجة أمر تحميل الصوت."""
    if not context.args:
        await update.message.reply_text("⚠️ يرجى إرسال رابط الفيديو بعد الأمر /audio\nمثال: /audio https://www.youtube.com/watch?v=...")
        return

    url = context.args[0]
    if not is_valid_url(url):
        await update.message.reply_text("❌ الرابط غير صالح. يرجى التأكد من الرابط وإعادة المحاولة.")
        return

    await update.message.reply_text("🎵 جاري تحميل الصوت... قد يستغرق هذا بضع ثوانٍ.")
    file_path = await download_media(url, update.effective_chat.id, is_audio=True, update=update)

    if file_path and Path(file_path).exists():
        try:
            with open(file_path, 'rb') as audio_file:
                await update.message.reply_audio(audio=audio_file, title=Path(file_path).stem, performer="Media Bot")
            await update.message.reply_text("✅ تم إرسال الصوت بنجاح!")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ أثناء إرسال الملف: {str(e)[:100]}")
        finally:
            try:
                Path(file_path).unlink()
            except:
                pass
    else:
        await update.message.reply_text("❌ فشل تحميل الصوت. تأكد من أن الرابط صحيح ويدعمه البوت.")

async def handle_message(update: Update, context) -> None:
    """معالجة الرسائل النصية (الروابط)."""
    text = update.message.text.strip()
    if not is_valid_url(text):
        await update.message.reply_text("❌ يرجى إرسال رابط صحيح يبدأ بـ http:// أو https://")
        return

    await update.message.reply_text("🎬 جاري تحميل الفيديو... قد يستغرق هذا بضع ثوانٍ.")
    file_path = await download_media(text, update.effective_chat.id, is_audio=False, update=update)

    if file_path and Path(file_path).exists():
        try:
            with open(file_path, 'rb') as video_file:
                await update.message.reply_video(video=video_file, supports_streaming=True)
            await update.message.reply_text("✅ تم إرسال الفيديو بنجاح!")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ أثناء إرسال الملف: {str(e)[:100]}")
        finally:
            try:
                Path(file_path).unlink()
            except:
                pass
    else:
        await update.message.reply_text("❌ فشل تحميل الفيديو. قد يكون الرابط غير مدعوم أو الفيديو خاصاً.")

async def cleanup_job(context):
    """تنظيف الملفات القديمة بشكل دوري."""
    await cleanup_old_files(DOWNLOAD_DIR)

def run_bot():
    """تشغيل البوت في thread منفصل مع حل مشكلة event loop."""
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("❌ لم يتم العثور على BOT_TOKEN في متغيرات البيئة")
        return

    # إعادة تعيين event loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception as e:
        logger.warning(f"Could not set new event loop: {e}")
    
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()

    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("audio", handle_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # جدولة مهمة التنظيف التلقائي كل 6 ساعات
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(cleanup_job, interval=21600, first=10)

    logger.info("✅ البوت يعمل الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# ----------------- التشغيل الرئيسي -----------------
if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║     Telegram Media Downloader Bot v2.0               ║
    ║     مع حفظ التوكن تلقائياً                           ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    # التحقق من وجود التوكن
    if not os.environ.get("BOT_TOKEN"):
        logger.error("8618250652:AAG4j4sYcO29zLI7wRsIKLcunG_vWxEgZKg")
        # لا نخرج هنا لأن Flask قد يحتاج للتشغيل لعرض الخطأ
    else:
        # تشغيل البوت في thread منفصل
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logger.info("تم بدء تشغيل البوت في خلفية")
    
    # تشغيل خادم Flask لمنع النوم
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"تشغيل خادم Flask على المنفذ {port}")
    app.run(host="0.0.0.0", port=port)
