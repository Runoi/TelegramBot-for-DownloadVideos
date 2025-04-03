import os
import re
from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from config import MAX_FILE_SIZE, PLATFORMS, TWITTER_PATTERNS, VK_PATTERNS
from handlers.twitter import handle_twitter_post
from handlers.vk import handle_vk_post
from handlers.video import handle_video_download
import logging
from typing import Optional

from handlers.vk_video import handle_vk_video_download
from services.downloader import download_vk_video

logger = logging.getLogger(__name__)

async def start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "🔻 Отправьте ссылку на видео с:\n"
        "YouTube, Instagram, TikTok, Twitter/X\n"
        "VK, Reddit\n\n"
        "Или отправьте ссылку на пост с:\n"
        "VK или Twitter/X (текст + картинки)\n\n"
        "Я скачаю и отправлю вам контент!"
    )

async def handle_links(message: Message):
    url = message.text.strip()
    try:
        # Обработка VK
        if 'vk.com' in url:
            if any(p in url for p in ['/video', '/clip', 'video_ext.php']):
                await handle_vk_video_download(message, url)
            elif any(p in url for p in ['wall-', '?w=wall', '?z=wall']):  # Добавлены новые форматы
                await handle_vk_post(message, url)
            else:
                await message.answer("ℹ️ Укажите прямую ссылку на видео или пост VK")
            return

        # Проверка Twitter/X
        if re.search(PLATFORMS["twitter"], url, re.IGNORECASE) and any(p in url for p in TWITTER_PATTERNS):
            await handle_twitter_post(message, url)
            return

        # Проверка других платформ
        platform_detected = False
        for platform, pattern in PLATFORMS.items():
            if platform in ["vk", "twitter"]:
                continue  # Уже обработаны выше
                
            if re.search(pattern, url, re.IGNORECASE):
                platform_detected = True
                await handle_video_download(message, url)
                break

        if not platform_detected:
            await message.answer("❌ Платформа не поддерживается. Отправьте ссылку на:\n"
                               "- Видео (YouTube, Instagram, TikTok, VK)\n"
                               "- Пост (Twitter/X, VK)")

    except Exception as e:
        logger.error(f"Ошибка обработки ссылки: {str(e)}", exc_info=True)
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")

def register_base_handlers(dp):
    """Регистрация обработчиков"""
    dp.message.register(start, Command("start"))
    dp.message.register(handle_links, F.text)