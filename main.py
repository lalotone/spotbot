import os
import sys
from tools import is_valid_url, to_snake_case, download_data
from logger import setup_logger

from telegram import Update
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


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Access user_ids from bot_data
    allowed_user_ids = context.bot_data.get('user_ids', [])
    download_path = context.bot_data.get('download_path', [])
    user_id = str(update.effective_user.id)

    # Check if user is allowed
    if user_id not in allowed_user_ids:
        # Optionally: log the unauthorized attempt or just silently ignore
        return
    command_data = update.message.text.split(' ')
    if len(command_data) < 2:
        await update.message.reply_text(f'Invalid number of parameters: /download URL [optional_path]')
    else:
        if is_valid_url(command_data[1]):
            # If no folder specified, use common folder
            if len(command_data) < 3:
                artist_name = 'Not defined artist'
                music_folder = 'common'
            else:
                artist_name = ' '.join(command_data[2:])
                music_folder = to_snake_case(artist_name)

            logger.info(f"Downloading: {artist_name}.")
            await update.message.reply_text(f'Downloading: {artist_name}, please wait.')
            if download_data(command_data[1], download_path, music_folder):
                logger.info(f"{artist_name} downloaded")
                await update.message.reply_text(f'{artist_name}, downloaded.')
            else:
                logger.error(f"{artist_name} NOT downloaded")
                await update.message.reply_text(f'{artist_name} not downloaded. Something went wrong.')
        else:
            logger.error(f'Invalid URL: {command_data[1]}')
            await update.message.reply_text(f'Invalid URL: {command_data[1]}')

if __name__ == "__main__":
    logger.info("Starting Telegram SpotDL Bot...")
    setup_data = bootstrap()

    app = ApplicationBuilder().token(setup_data['token']).build()
    app.bot_data['user_ids'] = setup_data['user_ids']
    app.bot_data['download_path'] = setup_data['download_path']
    app.add_handler(CommandHandler("download", download))

    logger.info("Bot started successfully! Listening for commands...")
    app.run_polling()
