from aiogram.types import Message, BufferedInputFile,InputMediaPhoto
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_TELEGRAM_VIDEO_SIZE
import os
import logging
import asyncio
from aiogram import Bot

logger = logging.getLogger(__name__)

downloader = InstagramDownloader()

async def handle_instagram(message: Message, url: str, bot: Bot):
    """Обработчик для Instagram с объединением медиа"""
    try:
        status_msg = await message.answer("🔄 Подготовка к загрузке (до 500 сек.)..")
        
        # Загружаем с объединением фото и видео
        result, status = await downloader.download_content(url, merge_all=False)
        
        if not result['media']:
            await message.answer(f"❌ Ошибка: {status}")
            return
        
        # Отправляем текст если есть
        if result['text']:
            with open(result['text'][0], 'r', encoding='utf-8') as f:
                text = f.read()
                # Разбиваем длинный текст на части
                for i in range(0, len(text), 4000):
                    await message.answer(f"📝 Текст {'(продолжение)' if i > 0 else ''}:\n{text[i:i+4000]}")
        
        # Группируем изображения для отправки медиагруппой
        photos = [f for f in result['media'] if os.path.basename(f).lower().endswith(('.jpg', '.jpeg', '.png'))]
        videos = [f for f in result['media'] if os.path.basename(f).lower().endswith(('.mp4', '.mov'))]
        
        # Отправляем фото медиагруппой (если есть)
        if photos:
            try:
                await _send_photos_as_group(message, photos, bot)
            except Exception as e:
                logger.error(f"Failed to send photos: {str(e)}")
                # Если не получилось группой, пробуем по одному
                for photo in photos:
                    try:
                        await _send_single_photo(message, photo, bot)
                    except Exception as e:
                        logger.error(f"Failed to send photo {photo}: {str(e)}")
                    finally:
                        await downloader._safe_remove_file(photo)
            finally:
                for photo in photos:
                    await downloader._safe_remove_file(photo)
        
        
        # Отправляем видео по одному
        for video in videos:
            try:
                await _send_single_video(message, video, bot)
            except Exception as e:
                logger.error(f"Failed to send video {video}: {str(e)}")
            finally:
                await downloader._safe_remove_file(video)
        
        # Удаляем текстовый файл
        if result['text']:
            await downloader._safe_remove_file(result['text'][0])
        
        await message.bot.delete_message(message.chat.id, status_msg.message_id)
        
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        await message.answer("💥 Произошла критическая ошибка")

async def _send_photos_as_group(message: Message, photo_paths: list, bot: Bot):
    """Отправка группы фото одним сообщением"""
    media_group = []
    
    for photo_path in photo_paths:
        filename = os.path.basename(photo_path)
        with open(photo_path, 'rb') as f:
            media_group.append(
                InputMediaPhoto(
                    media=BufferedInputFile(
                        file=f.read(),
                        filename=filename
                    )
                )
            )
    
    await bot.send_media_group(chat_id=message.chat.id, media=media_group)

async def _send_single_photo(message: Message, photo_path: str, bot: Bot):
    """Отправка одного фото"""
    filename = os.path.basename(photo_path)
    with open(photo_path, 'rb') as f:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=BufferedInputFile(
                file=f.read(),
                filename=filename
            )
        )

async def _send_single_video(message: Message, video_path: str, bot: Bot):
    """Отправка одного видео с проверкой размера"""
    file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
    
    if file_size > MAX_TELEGRAM_VIDEO_SIZE:
        await message.answer(f"📦 Видео слишком большое ({file_size:.1f}MB)")
        return
    
    filename = os.path.basename(video_path)
    with open(video_path, 'rb') as f:
        await bot.send_video(
            chat_id=message.chat.id,
            video=BufferedInputFile(
                file=f.read(),
                filename=filename
            )
        )
