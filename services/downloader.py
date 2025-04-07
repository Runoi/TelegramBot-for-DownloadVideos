import os
import re
import asyncio
import logging
import glob
import time
import yt_dlp
from typing import Optional
from pathlib import Path
from aiogram import Bot, types
from concurrent.futures import ThreadPoolExecutor
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, PLATFORMS
from services.utils import compress_video
from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)

# Ограничение параллельных загрузок
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

class DownloadLogger:
    """Кастомный логгер для yt-dlp"""
    def debug(self, msg):
        if msg.startswith('[download]'):
            logger.info(f"YT-DLP: {msg}")

    def warning(self, msg):
        logger.warning(f"YT-DLP: {msg}")

    def error(self, msg):
        logger.error(f"YT-DLP: {msg}")

class DownloadProgressHook:
    """Класс для отображения прогресса загрузки"""
    def __init__(self, message: types.Message, bot: Bot):
        self.message = message
        self.bot = bot
        self.last_update = 0
        self.start_time = time.time()

    async def progress_hook(self, d):
        if d['status'] == 'downloading':
            now = time.time()
            # Обновляем не чаще чем раз в 3 секунды
            if now - self.last_update > 3 or d['_percent_str'] == '100.0%':
                self.last_update = now
                try:
                    percent = float(d['_percent_str'].replace('%', ''))
                    progress_bar = self._create_progress_bar(percent)
                    elapsed = int(now - self.start_time)
                    
                    text = (
                        f"⏳ Скачивание видео...\n\n"
                        f"{progress_bar} {d['_percent_str']}\n"
                        f"⏱ Время: {elapsed} сек\n"
                        f"🚀 Скорость: {d['_speed_str']}\n"
                        f"⏳ Осталось: {d['_eta_str']}"
                    )
                    
                    await self.bot.edit_message_text(
                        text,
                        chat_id=self.message.chat.id,
                        message_id=self.message.message_id
                    )
                except Exception as e:
                    logger.error(f"Progress update error: {e}")

    def _create_progress_bar(self, percent, length=10):
        filled = int(length * percent // 100)
        return '⬜' * filled + '⬛' * (length - filled)

def get_ydl_opts(url: str, platform: str = None) -> dict:
    """Возвращает параметры скачивания для разных платформ"""
    base_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'retries': 3,
        'fragment_retries': 3,
        'skip_unavailable_fragments': True,
        'merge_output_format': 'mp4',
        'logger': DownloadLogger(),
        'windows_filenames': True,
        'restrictfilenames': True,
        'nooverwrites': True,
        'continuedl': True,
        'noprogress': True,
        'concurrent_fragment_downloads': 2,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    }

    if not platform:
        if re.search(r"(youtube\.com|youtu\.be)", url, re.IGNORECASE):
            platform = 'youtube'
        elif re.search(r"instagram\.com", url, re.IGNORECASE):
            platform = 'instagram'
        elif re.search(r"(x\.com|twitter\.com)", url, re.IGNORECASE):
            platform = 'twitter'
        elif re.search(r"vk\.com", url, re.IGNORECASE):
            platform = 'vk'

    if platform == 'youtube':
        base_opts.update({
            'format': 'bv*[height<=720][ext=mp4]+ba/b[height<=720]',
            'throttled_rate': '2M'
        })
    elif platform == 'instagram':
        base_opts.update({
            'format': 'bestvideo+bestaudio/best',
            'extractor_args': {'instagram': {'post': {'format': 'video'}}}
        })
    elif platform == 'twitter':
        base_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'extractor_args': {
                'twitter': {
                    'username': os.getenv('TWITTER_USERNAME'),
                    'password': os.getenv('TWITTER_PASSWORD')
                }
            },
            'throttled_rate': '1M'
        })
    elif platform == 'vk':
        base_opts.update({
            'referer': 'https://vk.com/',
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        })

    return base_opts

async def download_video(url: str, message: types.Message, bot: Bot, timeout: int = 300) -> str:
    """Основная функция скачивания с индикатором прогресса"""
    async with DOWNLOAD_SEMAPHORE:
        try:
            # Создаем директорию для загрузок
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            
            # Отправляем начальное сообщение
            progress_msg = await bot.send_message(
                message.chat.id,
                "🔄 Подготовка к загрузке..."
            )
            
            # Определяем платформу
            platform = None
            if 'twitter.com' in url or 'x.com' in url:
                platform = 'twitter'
            elif 'vk.com' in url:
                platform = 'vk'
            
            # Настраиваем хук прогресса
            progress_hook = DownloadProgressHook(progress_msg, bot)
            ydl_opts = get_ydl_opts(url, platform)
            ydl_opts['progress_hooks'] = [lambda d: asyncio.create_task(progress_hook.progress_hook(d))]

            # Функция для синхронного выполнения
            def sync_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info)

            # Запускаем загрузку с таймаутом
            filename = await asyncio.wait_for(
                asyncio.to_thread(sync_download),
                timeout=timeout
            )

            # Проверяем результат
            if not os.path.exists(filename):
                files = find_video_files(DOWNLOAD_DIR)
                if files:
                    filename = files[0]
                else:
                    raise FileNotFoundError("Видеофайл не найден")

            # Финальное сообщение
            await bot.edit_message_text(
                "✅ Загрузка завершена! Обрабатываю видео...",
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )

            return filename

        except asyncio.TimeoutError:
            await bot.edit_message_text(
                "⏱ Превышено время ожидания загрузки",
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )
            raise ValueError("Превышено время загрузки")
        except yt_dlp.DownloadError as e:
            await bot.edit_message_text(
                "❌ Ошибка при скачивании видео",
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )
            raise ValueError(f"Ошибка загрузки: {str(e)}")
        except Exception as e:
            await bot.edit_message_text(
                f"⚠️ Неожиданная ошибка: {str(e)}",
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )
            raise
        finally:
            clean_temp_files(DOWNLOAD_DIR)

def find_video_files(directory: str, prefix: str = None) -> list:
    """Поиск видеофайлов в директории"""
    video_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(('.mp4', '.mkv', '.webm')):
                if prefix and not file.startswith(prefix):
                    continue
                video_files.append(os.path.join(root, file))
    
    # Сортировка по времени изменения (новые сначала)
    video_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return video_files

def clean_temp_files(directory: str):
    """Очистка временных файлов"""
    for pattern in ['*.part', '*.ytdl', '*.tmp']:
        for file in glob.glob(os.path.join(directory, pattern)):
            try:
                os.remove(file)
            except Exception:
                pass

async def download_twitter_video(url: str, message: types.Message, bot: Bot, timeout: int = 240) -> str:
    """Специализированная функция для Twitter"""
    return await download_video(url, message, bot, timeout)

async def download_vk_video(url: str, message: types.Message, bot: Bot, timeout: int = 240) -> str:
    """Специализированная функция для VK"""
    return await download_video(url, message, bot, timeout)