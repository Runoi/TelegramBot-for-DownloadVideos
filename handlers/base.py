import re
from aiogram import F, Bot
from aiogram.filters import Command
from aiogram.types import Message
from config import PLATFORMS, TWITTER_PATTERNS, VK_PATTERNS
from handlers.instagram import handle_instagram
from handlers.twitter import handle_twitter_post
from handlers.vk import handle_vk_post
from handlers.video import handle_video_download
from handlers.vk_video import handle_vk_video_download
import logging

logger = logging.getLogger(__name__)

async def start(message: Message):
    await message.answer(
        "🔻 Отправьте ссылку на видео с:\n"
        "YouTube, Instagram, TikTok, Twitter/X\n"
        "VK, Reddit\n\n"
        "Я скачаю и отправлю вам контент!"
    )

async def handle_links(message: Message, bot: Bot):
    url = message.text.strip()
    try:
        if re.search(PLATFORMS["twitter"], url, re.IGNORECASE) and any(p in url for p in TWITTER_PATTERNS):
            # Экранируем текст сообщения
            status_msg = await message.answer(
                "Подготовка к загрузке Twitter (до 500 сек.)...",
                parse_mode=None
            )
            try:
                await handle_twitter_post(message, url, bot)
            finally:
                try:
                    await bot.delete_message(message.chat.id, status_msg.message_id)
                except Exception as e:
                    logger.error(f"Error deleting status message: {e}")
        elif 'vk.com' in url or 'vkvideo.ru' in url:
            if any(p in url for p in ['/video', '/clip']):
                await handle_vk_video_download(message, url, bot)
            elif any(p in url for p in ['wall-', '?w=wall']):
                await handle_vk_post(message, url)
            else:
                await message.answer("Укажите прямую ссылку на видео или пост VK")
        elif re.search(PLATFORMS["instagram"], url, re.IGNORECASE):
            await handle_instagram(message, url,bot)
            return
        elif 'youtube.com/shorts' in url:
            await handle_video_download(message, url, bot)
        elif 'tiktok.com' in url:
            await handle_video_download(message, url, bot)
    except Exception as e:
        logger.error(f"Ошибка обработки ссылки: {str(e)}", exc_info=True)
        await message.answer(f"⚠️ Ошибка в base: {str(e)}")

def register_base_handlers(dp):
    dp.message.register(start, Command("start"))
    dp.message.register(handle_links, F.text)