import os
import yt_dlp
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggopus import OggOpus
from mutagen.aac import AAC

# Lade Umgebungsvariablen
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("Fehler: TELEGRAM_BOT_TOKEN wurde nicht gefunden.")

SUPPORTED_FORMATS = ["mp3", "mp4", "flac", "aac", "opus", "webm", "mkv"]

MESSAGES = {
    "welcome": "🎵 Hey, I'm Xalo's Media Bot! 🎥🎶\n\n"
               "I can convert videos from **YouTube, Facebook, TikTok, Instagram** into **MP3, FLAC, AAC, OPUS (audio) or MP4 (video), WEBM, MKV.** 🔥\n\n"
               "🎧 *To get an audio file:* Use /mp3, /flac, /aac, or /opus and then send the link.\n"
               "📹 *To get an MP4, WEBM, or MKV video:* Send /mp4, /webm, /mkv and then the link.\n"
               "💡 *Tip:* Use /quality 128, /quality 192, or /quality 320 to set MP3/AAC/OPUS quality!\n",
    "error": "❌ Oops, something went wrong. Please try again later.\nError: {error}",
    "choose_format": "Please choose first: /mp3, /flac, /aac, /opus, /mp4, /webm, or /mkv.",
}

download_queue = asyncio.Queue()

def add_metadata(file_path, title):
    try:
        ext = file_path.split(".")[-1]
        if ext == "mp3":
            audio = MP3(file_path, ID3=EasyID3)
            audio["title"] = title
            audio.save()
        elif ext == "m4a":
            audio = MP4(file_path)
            audio["\xa9nam"] = [title]
            audio.save()
        elif ext == "flac":
            audio = FLAC(file_path)
            audio["title"] = [title]
            audio.save()
        elif ext == "opus":
            audio = OggOpus(file_path)
            audio["title"] = [title]
            audio.save()
        elif ext == "aac":
            audio = AAC(file_path)
            audio["title"] = [title]
            audio.save()
    except Exception as e:
        print(f"❌ Fehler beim Speichern der Metadaten: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MESSAGES["welcome"])

async def set_format(update: Update, context: ContextTypes.DEFAULT_TYPE, format_type: str):
    context.user_data["format"] = format_type
    await update.message.reply_text(f"You selected **{format_type.upper()}**. Now send me the link!")

async def set_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        quality = context.args[0]
        if quality in ["128", "192", "320"]:
            context.user_data["quality"] = quality
            await update.message.reply_text(f"✅ Audio quality set to {quality}kbps.")
        else:
            await update.message.reply_text("❌ Invalid quality! Use /quality 128, /quality 192, or /quality 320.")
    else:
        await update.message.reply_text("❌ Please specify a quality. Example: /quality 192")

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    format_type = context.user_data.get("format")
    if format_type not in SUPPORTED_FORMATS:
        await update.message.reply_text(MESSAGES["choose_format"])
        return

    urls = update.message.text.split()
    for url in urls:
        await download_queue.put((update, context, format_type, url))

async def download_worker():
    while True:
        update, context, format_type, url = await download_queue.get()
        quality = context.user_data.get("quality", "192") if format_type in ["mp3", "aac", "opus"] else None
        file_name = f"temp.{format_type}"

        progress_msg = await update.message.reply_text("🔄 Downloading, please wait...")

        ydl_opts = {
            'format': 'bestaudio/best' if format_type in ["mp3", "flac", "aac", "opus"] else 'bestvideo[height<=360]+bestaudio/best',
            'outtmpl': 'temp.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': format_type, 'preferredquality': quality}] if format_type in ["mp3", "aac", "opus"] else [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'flac'}] if format_type == "flac" else [],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)

            title = info_dict.get("title", "Unknown Title")
            for ext in ["mp4", "webm", "mkv", "m4a", "opus", "mp3", "flac", "aac"]:
                if os.path.exists(f"temp.{ext}"):
                    file_name = f"temp.{ext}"
                    add_metadata(file_name, title)
                    break

            # Lösche die Fortschritts-Nachricht
            if progress_msg:
                await progress_msg.delete()

            # Datei senden
            if format_type in ["mp3", "flac", "aac", "opus"]:
                await update.message.reply_audio(audio=open(file_name, "rb"))
            elif format_type in ["mp4", "webm", "mkv"]:
                await update.message.reply_video(video=open(file_name, "rb"))

            # Aufräumen
            if os.path.exists(file_name):
                os.remove(file_name)

        except Exception as e:
            error_msg = str(e)
            if progress_msg:
                await progress_msg.edit_text(MESSAGES["error"].format(error=error_msg))

        download_queue.task_done()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mp3", lambda u, c: set_format(u, c, "mp3")))
    app.add_handler(CommandHandler("mp4", lambda u, c: set_format(u, c, "mp4")))
    app.add_handler(CommandHandler("webm", lambda u, c: set_format(u, c, "webm")))
    app.add_handler(CommandHandler("mkv", lambda u, c: set_format(u, c, "mkv")))
    app.add_handler(CommandHandler("flac", lambda u, c: set_format(u, c, "flac")))
    app.add_handler(CommandHandler("aac", lambda u, c: set_format(u, c, "aac")))
    app.add_handler(CommandHandler("opus", lambda u, c: set_format(u, c, "opus")))
    app.add_handler(CommandHandler("quality", set_quality))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link))

    loop = asyncio.get_event_loop()
    loop.create_task(download_worker())

    app.run_polling()

if __name__ == "__main__":
    main()
