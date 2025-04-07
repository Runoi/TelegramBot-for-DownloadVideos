import os
import asyncio
import logging
import time
import yt_dlp
from typing import Optional
from aiogram import Bot
from aiogram.types import Message
from config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)

class DownloadLogger:
    def debug(self, msg):
        if msg.startswith('[download]'):
            logger.info(f"YT-DLP: {msg}")

    def warning(self, msg):
        logger.warning(f"YT-DLP: {msg}")

    def error(self, msg):
        logger.error(f"YT-DLP: {msg}")

class AsyncProgressHook:
    def __init__(self, bot: Bot, chat_id: int, message_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_update = 0
        self.update_interval = 1  # Обновлять каждую секунду

    async def __call__(self, d):
        if d['status'] == 'downloading':
            now = time.time()
            if now - self.last_update > self.update_interval:
                self.last_update = now
                try:
                    percent = float(d.get('_percent_str', '0%').strip('%'))
                    progress = min(int(percent / 10), 10)  # Ограничиваем до 10 шагов
                    progress_bar = '⬜' * progress + '⬛' * (10 - progress)
                    
                    text = (
                        f"⏳ Загрузка видео...\n\n"
                        f"{progress_bar} {d.get('_percent_str', '0%')}\n"
                        f"🚀 Скорость: {d.get('_speed_str', 'N/A')}\n"
                        f"⏱ Осталось: {d.get('_eta_str', 'N/A')}"
                    )
                    
                    await self.bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self.message_id,
                        text=text
                    )
                except Exception as e:
                    logger.error(f"Progress update error: {e}")

async def download_media(url: str, message: Message, bot: Bot, platform: str = None) -> Optional[str]:
    """Универсальная функция загрузки с работающим прогресс-баром"""
    try:
        progress_msg = await bot.send_message(
            chat_id=message.chat.id,
            text="🔄 Подготовка к загрузке..."
        )

        # Создаем хук прогресса
        progress_hook = AsyncProgressHook(bot, message.chat.id, progress_msg.message_id)
        
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'progress_hooks': [lambda d: asyncio.create_task(progress_hook(d))],
            'logger': DownloadLogger(),
            'retries': 3,
            'extract_flat': False,
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]'
        }

        if platform == 'twitter':
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                'extractor_args': {'twitter': {'username': None, 'password': None}}
            })
        elif platform == 'vk':
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                'referer': 'https://vk.com/'
            })

        def sync_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        # Запускаем загрузку в отдельном потоке
        filename = await asyncio.get_event_loop().run_in_executor(
            None,
            sync_download
        )

        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="✅ Загрузка завершена! Обработка видео..."
        )

        return filename

    except Exception as e:
        logger.error(f"Download error: {e}")
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=f"❌ Ошибка: {str(e)}"
        )
        return None
    finally:
        try:
            await bot.delete_message(chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
        except:
            pass

# Функции для обратной совместимости
async def download_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    return await download_media(url, message, bot)

async def download_twitter_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    return await download_media(url, message, bot, 'twitter')

async def download_vk_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    return await download_media(url, message, bot, 'vk')