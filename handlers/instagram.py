from aiogram.types import Message, BufferedInputFile, InputMediaPhoto, InputMediaVideo
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_TELEGRAM_VIDEO_SIZE
import os
import logging
import asyncio
from aiogram import Bot

logger = logging.getLogger(__name__)

downloader = InstagramDownloader()

async def handle_instagram(message: Message, url: str, bot: Bot):
    """Обработчик для Instagram с добавлением текста к медиа-группе"""
    try:
        status_msg = await message.answer("🔄 Подготовка к загрузке (до 500 сек.)..")
        
        # Определяем тип контента для текста
        content_type = "контент"
        if '/stories/' in url:
            content_type = "сторис"
        elif '/reel/' in url:
            content_type = "рилс"
        elif '/p/' in url:
            content_type = "пост"
        elif '/tv/' in url:
            content_type = "IGTV"
        
        # Загружаем контент
        result, status = await downloader.download_content(url, merge_all=False)
        
        if not result['media']:
            await message.answer(f"❌ Ошибка: {status}")
            return
        
        # Формируем текст с упоминанием бота
        caption_text = f"Ваш {content_type} готов! @prorusaver_bot"
        
        # Отправляем медиа с текстом
        photos = [f for f in result['media'] if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        videos = [f for f in result['media'] if f.lower().endswith(('.mp4', '.mov'))]
        
        # Для фото (вся группа с текстом)
        if photos:
            try:
                media_group = [
                    InputMediaPhoto(
                        media=BufferedInputFile(
                            open(photo, 'rb').read(),
                            filename=os.path.basename(photo)
                        )
                    ) for photo in photos
                ]
                # Добавляем текст только к первому элементу группы
                media_group[0].caption = caption_text
                
                await bot.send_media_group(
                    chat_id=message.chat.id,
                    media=media_group
                )
            except Exception as e:
                logger.error(f"Ошибка отправки фото: {str(e)}")
                # Fallback: отправка по одному
                for i, photo in enumerate(photos):
                    try:
                        with open(photo, 'rb') as f:
                            await bot.send_photo(
                                chat_id=message.chat.id,
                                photo=BufferedInputFile(f.read(), os.path.basename(photo)),
                                caption=caption_text if i == 0 else None
                            )
                    except Exception as e:
                        logger.error(f"Ошибка отправки фото {photo}: {str(e)}")
                    finally:
                        await downloader._safe_remove_file(photo)
        
        # Для видео (вся группа с текстом)
        if videos:
            try:
                media_group = [
                    InputMediaVideo(
                        media=BufferedInputFile(
                            open(video, 'rb').read(),
                            filename=os.path.basename(video)
                        )
                    ) for video in videos
                ]
                # Добавляем текст только к первому элементу группы
                media_group[0].caption = caption_text
                
                await bot.send_media_group(
                    chat_id=message.chat.id,
                    media=media_group
                )
            except Exception as e:
                logger.error(f"Ошибка отправки видео: {str(e)}")
                # Fallback: отправка по одному
                for i, video in enumerate(videos):
                    try:
                        with open(video, 'rb') as f:
                            await bot.send_video(
                                chat_id=message.chat.id,
                                video=BufferedInputFile(f.read(), os.path.basename(video)),
                                caption=caption_text if i == 0 else None
                            )
                    except Exception as e:
                        logger.error(f"Ошибка отправки видео {video}: {str(e)}")
                    finally:
                        await downloader._safe_remove_file(video)
        
        # Удаление временных файлов
        for file in result['media']:
            await downloader._safe_remove_file(file)
        if result['text']:
            await downloader._safe_remove_file(result['text'][0])
        
        await bot.delete_message(message.chat.id, status_msg.message_id)
        
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

async def _send_videos_as_group(message: Message, video_paths: list, bot: Bot):
    """Отправка группы видео одним сообщением"""
    media_group = []
    
    for video_path in video_paths:
        file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
        
        if file_size > MAX_TELEGRAM_VIDEO_SIZE:
            await message.answer(f"📦 Видео слишком большое ({file_size:.1f}MB) и не будет отправлено")
            continue
        
        filename = os.path.basename(video_path)
        with open(video_path, 'rb') as f:
            media_group.append(
                InputMediaVideo(
                    media=BufferedInputFile(
                        file=f.read(),
                        filename=filename
                    )
                )
            )
    
    if media_group:  # Отправляем только если есть что отправлять
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