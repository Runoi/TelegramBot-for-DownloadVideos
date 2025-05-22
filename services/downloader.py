import os
import asyncio
import logging
import time
import aiohttp
import yt_dlp
from typing import Optional
from aiogram import Bot
from aiogram.types import Message
from config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)

# В начале файла
ytdl = yt_dlp.YoutubeDL({
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
    'retries': 3,
    'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'http-chunk-size': '64M',
    'no_check_certificate': True,
    'geo_bypass': True,
    'force-ipv4': True,
    'extractor_args': {
        'youtube': {
            'skip': ['dash', 'hls', 'manifest'],
            'player_skip': ['configs', 'webpage', 'js'],
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    },
    'ignore_no_formats_error': True,
    'quiet': False,
    'no_warnings': False,
})

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

async def download_image(url: str) -> Optional[str]:
    """Асинхронная загрузка изображения из Twitter"""
    try:
        if not url or 'pbs.twimg.com' not in url:
            return None

        # Создаем директорию для загрузок, если ее нет
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Генерируем уникальное имя файла
        filename = os.path.join(DOWNLOAD_DIR, f"twitter_img_{int(time.time())}.jpg")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(filename, 'wb') as f:
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)
                    return filename
                else:
                    logger.error(f"Failed to download image. Status: {response.status}")
                    return None

    except Exception as e:
        logger.error(f"Image download error: {str(e)}")
        # Удаляем частично загруженный файл, если он существует
        if 'filename' in locals() and os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass
        return None            

async def download_media(url: str, message: Message, bot: Bot, platform: str = None) -> Optional[str]:
    """Универсальная функция загрузки"""
    
    try:
        
        progress_msg = await bot.send_message(
            text="🔄 Подготовка к загрузке (до 500 сек.)",
            chat_id=message.chat.id,
        )

        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'progress_hooks': [SyncProgressHook(bot, message.chat.id, progress_msg.message_id)],
            'logger': DownloadLogger(),
            'retries': 3,
            'extract_flat': False,
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]',
            'source-address': '0.0.0.0',         # Использовать все сетевые интерфейсы
            'force-ipv4': True,                  # Принудительно использовать IPv4
            'continuedl': True,  # Важно для Linux
            'noprogress': False,
            'noresizebuffer': True,
            'http-chunk-size': '6M',  # Увеличьте для Linux
            'no_check_certificate': True,
            'geo_bypass': True,
            'geo_bypass_country': 'NL',  # Нидерланды
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],  # Упрощаем выбор формата
                    'player_skip': ['configs'],
                }
            },
            # Ускоряем инициализацию
            'lazy_playlist': True,
            'extract_flat': True,
            'ignore_no_formats_error': True,
            'noplaylist': True,
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
            with ytdl:  # Используем предварительно инициализированный экземпляр
                info = ytdl.extract_info(url, download=True)
                return ytdl.prepare_filename(info)

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

    except Exception as e:
        logger.error(f"Download error: {e}")
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=f"❌ Скорей всего, вы скачиваете не видео, а фото"
        )
        return None
    finally:
        try:
            await bot.delete_message(progress_msg.chat.id, progress_msg.message_id)
        except:
            pass

# Функции для обратной совместимости
async def download_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    return await download_media(url, message, bot)

async def download_twitter_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    return await download_media(url, message, bot, 'twitter')

async def download_vk_video(url: str, message: Message, bot: Bot) -> Optional[str]:
    return await download_media(url, message, bot, 'vk')