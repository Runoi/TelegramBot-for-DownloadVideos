import os
import re
import asyncio
import logging
import time
import yt_dlp
from typing import Optional
from aiogram import Bot
from aiogram.types import Message
from config import DOWNLOAD_DIR, MAX_FILE_SIZE

logger = logging.getLogger(__name__)

class DownloadLogger:
    def debug(self, msg):
        if msg.startswith('[download]'):
            logger.info(f"YT-DLP: {msg}")

    def warning(self, msg):
        logger.warning(f"YT-DLP: {msg}")

    def error(self, msg):
        logger.error(f"YT-DLP: {msg}")

class SyncProgressHook:
    def __init__(self, bot: Bot, chat_id: int, message_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_update = 0
        self.loop = asyncio.get_event_loop()

    def __call__(self, d):
        if d['status'] == 'downloading':
            now = time.time()
            if now - self.last_update > 3:
                self.last_update = now
                asyncio.run_coroutine_threadsafe(
                    self._update_progress(d),
                    self.loop
                )

    async def _update_progress(self, d):
        try:
            percent = float(d['_percent_str'].strip('%'))
            progress = int(percent / 10)
            progress_bar = '⬜' * progress + '⬛' * (10 - progress)
            
            text = (
                f"⏳ Загрузка видео...\n\n"
                f"{progress_bar} {d['_percent_str']}\n"
                f"🚀 Скорость: {d['_speed_str']}\n"
                f"⏱ Осталось: {d['_eta_str']}"
            )
            
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text
            )
        except Exception as e:
            logger.error(f"Progress update error: {e}")

async def download_video(url: str, message: Message, bot: Bot, platform: str = None) -> Optional[str]:
    """Универсальная функция загрузки видео (сохраняет обратную совместимость)"""
    return await download_media(url, message, bot, platform)

async def download_media(url: str, message: Message, bot: Bot, platform: str = None) -> Optional[str]:
    """Основная функция загрузки медиа"""
    try:
        progress_msg = await bot.send_message(
            chat_id=message.chat.id,
            text="🔄 Подготовка к загрузке..."
        )

        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'progress_hooks': [SyncProgressHook(bot, message.chat.id, progress_msg.message_id)],
            'logger': DownloadLogger(),
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'windows_filenames': True,
            'restrictfilenames': True,
            'nooverwrites': True,
            'continuedl': True,
            'concurrent_fragment_downloads': 2,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        }

        if platform == 'twitter':
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'extractor_args': {
                    'twitter': {
                        'username': os.getenv('TWITTER_USERNAME'),
                        'password': os.getenv('TWITTER_PASSWORD')
                    }
                }
            })
        elif platform == 'youtube':
            ydl_opts.update({
                'format': 'bv*[height<=720][ext=mp4]+ba/b[height<=720]'
            })
        elif platform == 'vk':
            ydl_opts.update({
                'referer': 'https://vk.com/',
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            })

        def sync_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        filename = await asyncio.get_event_loop().run_in_executor(
            None,
            sync_download
        )

        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="✅ Загрузка завершена!"
        )

        return filename

    except yt_dlp.DownloadError as e:
        logger.error(f"Download failed: {e}")
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=f"❌ Ошибка загрузки: {str(e)}"
        )
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None
    finally:
        try:
            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=progress_msg.message_id
            )
        except:
            pass

async def download_twitter_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    """Специальная функция для Twitter (для обратной совместимости)"""
    return await download_media(url, message, bot, 'twitter')