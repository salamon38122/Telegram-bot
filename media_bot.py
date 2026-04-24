#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# المسارات
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
TOKEN_FILE = Path.home() / ".bot_token"

# الحد الأقصى لحجم الملف (50 ميجابايت)
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

async def cleanup_old_files(directory: Path, max_age_hours: int = 24):
    """حذف الملفات الأقدم من max_age_hours"""
    now = datetime.now()
    for file_path in directory.glob("*"):
        if file_path.is_file():
            age = now - datetime.fromtimestamp(file_path.stat().st_mtime)
            if age.total_seconds() > max_age_hours * 3600:
                try:
                    file_path.unlink()
                    logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")

async def download_media(url: str, chat_id: int, is_audio: bool = False, update: Update = None) -> str:
    """
    تحميل الوسائط مع إظهار رسائل بسيطة (بدون تقدم تفصيلي)
    """
    download_path = DOWNLOAD_DIR / f"{chat_id}"
    download_path.mkdir(exist_ok=True)
    output_template = "%(title)s.%(ext)s"

    ydl_opts = {
        'outtmpl': str(download_path / output_template),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
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
        # تحميل فيديو بجودة لا تتجاوز 720p و حجم معقول
        ydl_opts.update({
            'format': 'best[height<=720]/best',
        })

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
        logger.error(f"Download error: {e}")
        if update:
            await update.message.reply_text(f"❌ فشل التحميل: {str(e)[:100]}")
        return None

def is_file_size_valid(file_path: str) -> bool:
    """التحقق من أن حجم الملف أقل من 50 ميجابايت"""
    size = Path(file_path).stat().st_size
    return size <= MAX_FILE_SIZE_BYTES

# ----------------- أوامر البوت -----------------
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "🎬 **مرحباً بك في بوت تحميل الفيديوهات!**\n\n"
        "أرسل لي رابطاً وسأقوم بتحميل الفيديو أو الصوت.\n\n"
        "**الأوامر:**\n"
        "/start - عرض هذه الرسالة\n"
        "/audio <رابط> - تحميل الصوت فقط بصيغة MP3\n"
        "/help - المساعدة\n\n"
        "🔹 يمكنك إرسال الرابط مباشرة لتحميل الفيديو.",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📌 **كيفية الاستخدام:**\n"
        "• أرسل رابط الفيديو لتحميل الفيديو.\n"
        "• استخدم /audio قبل الرابط لتحميل الصوت فقط.\n\n"
        "**المنصات المدعومة:**\n"
        "YouTube, Instagram, TikTok, Twitter/X, Facebook, Reddit, Twitch, SoundCloud وغيرها.\n\n"
        "⚠️ **ملاحظات:**\n"
        f"• الحد الأقصى للملف هو {MAX_FILE_SIZE_MB} ميجابايت.\n"
        "• إذا كان الفيديو أكبر، حاول تحميل الصوت فقط أو استخدم روابط أقل جودة.",
        parse_mode='Markdown'
    )

async def handle_audio(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("⚠️ يرجى إرسال الرابط بعد الأمر /audio\nمثال: /audio https://youtu.be/...")
        return

    url = context.args[0]
    if not is_valid_url(url):
        await update.message.reply_text("❌ الرابط غير صالح.")
        return

    await update.message.reply_text("🎵 جاري تحميل الصوت... قد يستغرق ذلك بضع ثوانٍ.")
    file_path = await download_media(url, update.effective_chat.id, is_audio=True, update=update)

    if file_path and Path(file_path).exists():
        if not is_file_size_valid(file_path):
            await update.message.reply_text(f"⚠️ الملف أكبر من {MAX_FILE_SIZE_MB} ميجابايت ولا يمكن إرساله عبر تيليجرام.")
            Path(file_path).unlink(missing_ok=True)
            return

        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_audio(audio=f, title=Path(file_path).stem, performer="Media Bot")
            await update.message.reply_text("✅ تم إرسال الصوت بنجاح!")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ أثناء الإرسال: {str(e)[:100]}")
        finally:
            Path(file_path).unlink(missing_ok=True)
    else:
        await update.message.reply_text("❌ فشل تحميل الصوت. تأكد من الرابط.")

async def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if not is_valid_url(text):
        await update.message.reply_text("❌ يرجى إرسال رابط صحيح يبدأ بـ http:// أو https://")
        return

    await update.message.reply_text("🎬 جاري تحميل الفيديو... قد يستغرق ذلك بضع ثوانٍ.")
    file_path = await download_media(text, update.effective_chat.id, is_audio=False, update=update)

    if file_path and Path(file_path).exists():
        if not is_file_size_valid(file_path):
            await update.message.reply_text(f"⚠️ الفيديو أكبر من {MAX_FILE_SIZE_MB} ميجابايت. حاول استخدام /audio لتحميل الصوت فقط.")
            Path(file_path).unlink(missing_ok=True)
            return

        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_video(video=f, supports_streaming=True)
            await update.message.reply_text("✅ تم إرسال الفيديو بنجاح!")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ أثناء الإرسال: {str(e)[:100]}")
        finally:
            Path(file_path).unlink(missing_ok=True)
    else:
        await update.message.reply_text("❌ فشل تحميل الفيديو. قد يكون الرابط غير مدعوم أو الملف خاصاً.")

async def cleanup_job(context: CallbackContext):
    await cleanup_old_files(DOWNLOAD_DIR)

# ----------------- الحصول على التوكن -----------------
def get_bot_token() -> str:
    # 1. متغير البيئة
    token = os.getenv("BOT_TOKEN")
    if token:
        return token

    # 2. محاولة قراءة من ملف (احتياطي للتشغيل المحلي)
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token

    # 3. إدخال يدوي (للاستخدام المحلي فقط)
    print("لم يتم العثور على توكن البوت. يرجى إدخاله الآن (لن يطلب مرة أخرى):")
    token = input("التوكن: ").strip()
    if not token:
        raise ValueError("لا يمكن تشغيل البوت بدون توكن")
    TOKEN_FILE.write_text(token)
    print(f"✅ تم حفظ التوكن في {TOKEN_FILE}")
    return token

def main():
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║     Telegram Media Downloader Bot v2.1               ║
    ║     (تم إصلاح أخطاء التحميل)                         ║
    ╚══════════════════════════════════════════════════════╝
    """)

    try:
        TOKEN = get_bot_token()
    except ValueError as e:
        print(f"❌ {e}")
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("audio", handle_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(cleanup_job, interval=21600, first=10)

    print("✅ البوت يعمل الآن... اضغط Ctrl+C للإيقاف")
    application.run_polling()

if __name__ == "__main__":
    main()
