from aiogram.types import Message, BufferedInputFile
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_TELEGRAM_VIDEO_SIZE
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

downloader = InstagramDownloader()

async def handle_instagram(message: Message, url: str):
    """Обработчик для Instagram контента с текстом"""
    try:
        status_msg = await message.answer("🔄 Начинаю загрузку контента...")
        
        result, status = await downloader.download_content(url)
        
        if not result['media']:
            await message.answer(f"❌ Ошибка: {status}")
            return
        
        # Отправляем текст если есть
        if result['text']:
            with open(result['text'][0], 'r', encoding='utf-8') as f:
                caption = f.read()
                if len(caption) > 1000:  # Ограничение Telegram на длину подписи
                    caption = caption[:1000] + "..."
                await message.answer(f"📝 Текст поста:\n\n{caption}")
        
        # Отправляем медиафайлы
        for file in result['media']:
            try:
                await _send_media_file(message, file)
            except Exception as e:
                logger.error(f"Failed to send file {file}: {str(e)}")
            finally:
                await downloader._safe_remove_file(file)
        
        # Удаляем текстовый файл
        if result['text']:
            await downloader._safe_remove_file(result['text'][0])
        
        await message.bot.delete_message(message.chat.id, status_msg.message_id)
        
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        await message.answer("💥 Произошла критическая ошибка")

async def _send_media_file(message: Message, file_path: str):
    """Отправка медиафайла с проверкой размера"""
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
    
    if file_size > MAX_TELEGRAM_VIDEO_SIZE:
        await message.answer(f"📦 Файл слишком большой ({file_size:.1f}MB)")
        return
        
    with open(file_path, 'rb') as f:
        file_data = f.read()
        filename = os.path.basename(file_path)
        
        if filename.lower().endswith(('.mp4', '.mov')):
            await message.answer_video(BufferedInputFile(file_data, filename))
        else:
            await message.answer_photo(BufferedInputFile(file_data, filename))

