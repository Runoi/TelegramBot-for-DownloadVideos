from aiogram import types
from aiogram.types import InputMediaPhoto, BufferedInputFile
from services.utils import download_image
import os
import time
import logging
from typing import List

logger = logging.getLogger(__name__)

async def send_media_group(message: types.Message, image_urls: List[str], video_urls: List[str]):
    """Улучшенная отправка медиагруппы с обработкой ошибок"""
    media = []
    downloaded_files = []
    
    try:
        # Обработка изображений
        for i, url in enumerate(image_urls[:10]):
            try:
                filename = f"img_{i}_{int(time.time())}.jpg"
                img_path = await download_image(url, filename)
                downloaded_files.append(img_path)
                
                with open(img_path, 'rb') as f:
                    media.append(InputMediaPhoto(
                        media=BufferedInputFile(f.read(), filename=filename),
                        caption=f"Изображение {i+1}" if i == 0 else None
                    ))
            except Exception as e:
                logger.error(f"Ошибка загрузки изображения {url}: {str(e)}")
                continue
        
        # Если есть медиа для отправки
        if media:
            await message.bot.send_media_group(
                chat_id=message.chat.id,
                media=media
            )
        else:
            await message.answer("⚠️ Не удалось загрузить изображения")
            
    except Exception as e:
        logger.error(f"Ошибка отправки медиагруппы: {str(e)}")
        await message.answer("❌ Произошла ошибка при отправке медиа")
    finally:
        # Очистка временных файлов
        for file_path in downloaded_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"Ошибка удаления файла {file_path}: {str(e)}")