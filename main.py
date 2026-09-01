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
# If a name is specified, it is snake_cased and used as the folder name; the folder
# is created if necessary
# A text file with one URL per line can be attached instead: those go to "various"
# (or to the given folder name, if any)
# Check userID, if not allowed, no response
# Downloads run in a thread pool executor via yt-dlp's Python API

logger = setup_logger(__name__)

DOWNLOAD_LOCK = asyncio.Lock()
MAX_LIST_FILE_BYTES = 512 * 1024
LIST_DEFAULT_FOLDER = 'various'


def _parse_user_ids(raw: str) -> list:
    return [part.strip() for part in raw.split(',') if part.strip()]


def bootstrap():
    token = os.environ.get('TELEGRAM_TOKEN', '')
    id_data = os.environ.get('USER_IDS', '')
    download_path = os.environ.get('DOWNLOAD_FOLDER', '')
    if token == '' or id_data == '' or download_path == '':
        logger.error("Missing required environment variables: TELEGRAM_TOKEN, USER_IDS, or DOWNLOAD_FOLDER")
        sys.exit(1)
    ids = _parse_user_ids(id_data)
    if not ids:
        logger.error("USER_IDS contains no valid user IDs")
        sys.exit(1)
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


def _make_progress_emitter(status_msg, loop: asyncio.AbstractEventLoop, label_prefix: str = ''):
    # Telegram allows ~1 edit/second per chat; 3 s gives comfortable headroom.
    THROTTLE = 3.0
    last_edit = {'t': 0.0}

    def progress_callback(status, title, pct, speed, eta, playlist_index, playlist_count):
        now = time.monotonic()
        if now - last_edit['t'] < THROTTLE:
            return
        last_edit['t'] = now
        text = _progress_text(title, pct, speed, eta, playlist_index, playlist_count, status)
        if label_prefix:
            text = f'{label_prefix}\n{text}'
        # Fire and forget: this runs on the yt-dlp download thread and blocking
        # here would stall the actual download.
        try:
            asyncio.run_coroutine_threadsafe(status_msg.edit_text(text), loop)
        except Exception:
            pass

    return progress_callback


async def _fetch_url_list(message) -> list:
    document = message.document
    if document.file_size is None or document.file_size > MAX_LIST_FILE_BYTES:
        raise ValueError('file is larger than 512 KB')
    tg_file = await document.get_file()
    chunk = await tg_file.download_as_byte_array()
    raw = bytes(chunk).decode('utf-8', errors='replace')
    urls = [line.strip() for line in raw.splitlines()]
    urls = [u for u in urls if u and not u.startswith('#') and is_valid_url(u)]
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and not is_valid_url(line):
            logger.warning(f"Skipping invalid URL in attached file: {line}")
    return urls


async def _safe_edit(message, text) -> None:
    try:
        await message.edit_text(text)
    except BadRequest:
        # Covers "message is not modified", FloodWait 429s and deleted messages.
        pass


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed_user_ids = context.bot_data.get('user_ids', [])
    download_path = context.bot_data.get('download_path', '')
    user_id = str(update.effective_user.id)

    if user_id not in allowed_user_ids:
        return

    message = update.effective_message
    if message is None or not message.text:
        return

    command_data = message.text.split()
    if not command_data:
        return

    if message.document is not None:
        args = command_data[1:]
        if args and is_valid_url(args[0]):
            await message.reply_text(
                'A URL was given together with an attached file.\n'
                'Usage with a file: /download [optional folder name] + attached .txt with one URL per line'
            )
            return
        if args:
            folder = to_snake_case(' '.join(args))
        else:
            folder = LIST_DEFAULT_FOLDER
        try:
            urls = await _fetch_url_list(message)
        except ValueError as e:
            await message.reply_text(f'Could not read the attached file: {e}')
            return
        except Exception:
            logger.exception('Failed to fetch attached URL list file')
            await message.reply_text('Could not read the attached file.')
            return
        if not urls:
            await message.reply_text('No valid URLs found in the attached file.')
            return
        await _download_url_list(message, urls, download_path, folder)
        return

    if len(command_data) < 2:
        await message.reply_text('Usage: /download <YouTube or YouTube Music URL> [optional folder name]')
        return

    if not is_valid_url(command_data[1]):
        logger.error(f'Invalid URL: {command_data[1]}')
        await message.reply_text(f'Invalid URL: {command_data[1]}')
        return

    if len(command_data) < 3:
        artist_name = 'Not defined artist'
        music_folder = 'common'
    else:
        artist_name = ' '.join(command_data[2:])
        music_folder = to_snake_case(artist_name)

    logger.info(f"Downloading: {artist_name}.")
    status_msg = await message.reply_text(f'Starting download: {artist_name}...')

    loop = asyncio.get_running_loop()
    progress_callback = _make_progress_emitter(status_msg, loop)

    async with DOWNLOAD_LOCK:
        success = await loop.run_in_executor(
            None,
            lambda: download_data(command_data[1], download_path, music_folder, progress_callback),
        )

    if success:
        logger.info(f"{artist_name} downloaded")
        await _safe_edit(status_msg, f'{artist_name} downloaded successfully.')
    else:
        logger.error(f"{artist_name} NOT downloaded")
        await _safe_edit(status_msg, f'{artist_name} could not be downloaded. Something went wrong.')


async def _download_url_list(message, urls, download_path, folder) -> None:
    total = len(urls)
    logger.info(f"Downloading {total} URL(s) from list into folder '{folder}'")
    status_msg = await message.reply_text(f'Starting download of {total} URL(s)...')

    loop = asyncio.get_running_loop()
    ok_count = 0
    async with DOWNLOAD_LOCK:
        for index, url in enumerate(urls, start=1):
            label = f'[{index}/{total}]'
            progress_callback = _make_progress_emitter(status_msg, loop, label_prefix=label)
            await _safe_edit(status_msg, f'{label} Downloading...\n{url}')
            success = await loop.run_in_executor(
                None,
                lambda u=url: download_data(u, download_path, folder, progress_callback),
            )
            if success:
                ok_count += 1

    summary = f'{ok_count}/{total} downloaded from list into folder "{folder}".'
    logger.info(summary)
    await _safe_edit(status_msg, summary)

if __name__ == "__main__":
    logger.info("Starting Telegram Music Downloader Bot (yt-dlp)...")
    setup_data = bootstrap()

    app = ApplicationBuilder().token(setup_data['token']).build()
    app.bot_data['user_ids'] = setup_data['user_ids']
    app.bot_data['download_path'] = setup_data['download_path']
    app.add_handler(CommandHandler("download", download))

    logger.info("Bot started successfully! Listening for commands...")
    app.run_polling()
