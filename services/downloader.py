import os
import asyncio
import logging
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

async def download_media(url: str, message: Message, bot: Bot, platform: str = None) -> Optional[str]:
    """Универсальная функция загрузки с работающим прогресс-баром"""
    progress_msg = None
    try:
        # Создаем сообщение о начале загрузки
        progress_msg = await bot.send_message(
            chat_id=message.chat.id,
            text="⏳ Подготовка к загрузке..."
        )

        # Создаем очередь для обмена данными о прогрессе
        progress_queue = asyncio.Queue()

        # Функция-обработчик прогресса
        def progress_hook(d):
            if d['status'] == 'downloading':
                asyncio.create_task(progress_queue.put(d))

        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'logger': DownloadLogger(),
            'retries': 3,
            'extract_flat': False,
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]'
        }

        if platform == 'twitter':
            ydl_opts.update({
                'extractor_args': {'twitter': {'username': None, 'password': None}}
            })
        elif platform == 'vk':
            ydl_opts.update({
                'referer': 'https://vk.com/'
            })

        # Задача для обновления прогресса
        async def update_progress():
            last_percent = 0
            while True:
                d = await progress_queue.get()
                current_percent = float(d.get('_percent_str', '0%').strip('%'))
                
                # Обновляем только если процент изменился
                if current_percent > last_percent:
                    last_percent = current_percent
                    progress = min(int(current_percent / 10), 10)
                    progress_bar = '⬜' * progress + '⬛' * (10 - progress)
                    
                    text = (
                        f"⏳ Загрузка видео...\n\n"
                        f"{progress_bar} {d.get('_percent_str', '0%')}\n"
                        f"🚀 Скорость: {d.get('_speed_str', 'N/A')}\n"
                        f"⏱ Осталось: {d.get('_eta_str', 'N/A')}"
                    )
                    
                    try:
                        await bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=progress_msg.message_id,
                            text=text
                        )
                    except Exception as e:
                        logger.error(f"Ошибка обновления прогресса: {e}")

        # Запускаем задачу обновления прогресса
        progress_task = asyncio.create_task(update_progress())

        # Запускаем загрузку в отдельном потоке
        def sync_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        filename = await asyncio.get_event_loop().run_in_executor(
            None,
            sync_download
        )

        # Отменяем задачу обновления прогресса
        progress_task.cancel()

        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text="✅ Загрузка завершена! Обработка видео..."
        )

        return filename

    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        if progress_msg:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
                text=f"❌ Ошибка: {str(e)}"
            )
        return None
    finally:
        if progress_msg:
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