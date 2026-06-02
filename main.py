import asyncio
import os
import sys
import time
from tools import is_valid_url, to_snake_case, download_data
from logger import setup_logger

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Base setup
# -------------
# - Read token from env var
# - Read allowed user ids from env var using comma as sep
#
# How it works
# -------------
# If no name is specified after link, music will be placed in a folder named "common"
# If name specified, use that name in lowercase and camel_case, create folder if necessary
# Check userID, if not allowed, no response
# Use subprocess to download music

logger = setup_logger(__name__)

def bootstrap():
    token = os.environ.get('TELEGRAM_TOKEN', '')
    id_data = os.environ.get('USER_IDS', '')
    download_path = os.environ.get('DOWNLOAD_FOLDER', '')
    if token == '' or id_data == '' or download_path == '':
        logger.error("Missing required environment variables: TELEGRAM_TOKEN, USER_IDS, or DOWNLOAD_FOLDER")
        sys.exit(1)
    if ',' in id_data:
        ids = id_data.split(',')
    else:
        ids = [id_data]
    logger.info(f"Bot configured for {len(ids)} authorized user(s)")
    logger.info(f"Download path: {download_path}")
    return {'token': token, 'user_ids': ids, 'download_path': download_path}


def _progress_text(title, pct, speed, eta, playlist_index, playlist_count, status):
    bar_len = 10
    filled = round(pct / 100 * bar_len)
    bar = '█' * filled + '░' * (bar_len - filled)

    lines = []
    if playlist_index and playlist_count:
        lines.append(f'Track {playlist_index}/{playlist_count}')
    lines.append(title)
    if status == 'downloading':
        lines.append(f'[{bar}] {pct:.1f}%')
        lines.append(f'Speed: {speed} | ETA: {eta}')
    else:
        lines.append(f'[{bar}] Converting to mp3...')
    return '\n'.join(lines)


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_ids = context.bot_data.get('user_ids', [])
    download_path = context.bot_data.get('download_path', '')
    user_id = str(update.effective_user.id)

    if user_id not in allowed_user_ids:
        return

    command_data = update.message.text.split(' ')
    if len(command_data) < 2:
        await update.message.reply_text('Usage: /download <YouTube or YouTube Music URL> [optional folder name]')
        return

    if not is_valid_url(command_data[1]):
        logger.error(f'Invalid URL: {command_data[1]}')
        await update.message.reply_text(f'Invalid URL: {command_data[1]}')
        return

    if len(command_data) < 3:
        artist_name = 'Not defined artist'
        music_folder = 'common'
    else:
        artist_name = ' '.join(command_data[2:])
        music_folder = to_snake_case(artist_name)

    logger.info(f"Downloading: {artist_name}.")
    status_msg = await update.message.reply_text(f'Starting download: {artist_name}...')

    loop = asyncio.get_running_loop()
    # Telegram allows ~1 edit/second per chat; 3 s gives comfortable headroom.
    THROTTLE = 3.0
    last_edit = {'t': 0.0}

    def progress_callback(status, title, pct, speed, eta, playlist_index, playlist_count):
        now = time.monotonic()
        if now - last_edit['t'] < THROTTLE:
            return
        last_edit['t'] = now
        text = _progress_text(title, pct, speed, eta, playlist_index, playlist_count, status)
        future = asyncio.run_coroutine_threadsafe(status_msg.edit_text(text), loop)
        # Swallow "Message is not modified" and other non-fatal Telegram errors.
        try:
            future.result(timeout=5)
        except (BadRequest, Exception):
            pass

    success = await loop.run_in_executor(
        None,
        lambda: download_data(command_data[1], download_path, music_folder, progress_callback),
    )

    if success:
        logger.info(f"{artist_name} downloaded")
        await status_msg.edit_text(f'{artist_name} downloaded successfully.')
    else:
        logger.error(f"{artist_name} NOT downloaded")
        await status_msg.edit_text(f'{artist_name} could not be downloaded. Something went wrong.')

if __name__ == "__main__":
    logger.info("Starting Telegram Music Downloader Bot (yt-dlp)...")
    setup_data = bootstrap()

    app = ApplicationBuilder().token(setup_data['token']).build()
    app.bot_data['user_ids'] = setup_data['user_ids']
    app.bot_data['download_path'] = setup_data['download_path']
    app.add_handler(CommandHandler("download", download))

    logger.info("Bot started successfully! Listening for commands...")
    app.run_polling()
