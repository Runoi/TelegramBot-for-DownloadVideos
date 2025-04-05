from aiogram.types import InputMediaPhoto, InputMediaVideo, Message
import logging
from typing import List, Optional
import os

logger = logging.getLogger(__name__)

async def send_media_group(
    message: Message,
    image_urls: Optional[List[str]] = None,
    video_urls: Optional[List[str]] = None
) -> bool:
    """Универсальная отправка медиагруппы"""
    try:
        if not image_urls and not video_urls:
            logger.warning("Нет медиа для отправки")
            return False

        media = []
        
        # Обработка изображений
        if image_urls:
            for url in image_urls[:10]:  # Ограничение Telegram - 10 медиа в группе
                try:
                    media.append(InputMediaPhoto(media=url))
                except Exception as e:
                    logger.error(f"Ошибка добавления фото {url}: {str(e)}")

        # Обработка видео
        if video_urls:
            for url in video_urls[:10 - len(media)]:  # Учитываем уже добавленные фото
                try:
                    media.append(InputMediaVideo(media=url))
                except Exception as e:
                    logger.error(f"Ошибка добавления видео {url}: {str(e)}")

        if not media:
            logger.error("Не удалось подготовить ни одного медиа")
            return False

        # Отправка группой
        await message.bot.send_media_group(
            chat_id=message.chat.id,
            media=media
        )
        return True

    except Exception as e:
        logger.error(f"Ошибка отправки медиагруппы: {str(e)}", exc_info=True)
        return False