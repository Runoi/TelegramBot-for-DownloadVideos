from aiogram.types import Message, BufferedInputFile
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR, MAX_TELEGRAM_VIDEO_SIZE
import os
import logging
import asyncio

logger = logging.getLogger(__name__)
downloader = InstagramDownloader()

async def handle_instagram_post(message: Message, url: str):
    """Основной обработчик для Instagram постов"""
    try:
        # Статусное сообщение
        status_msg = await message.answer("🔄 Начинаю загрузку...")
        
        # Получаем контент через сервис
        content, status = await downloader.download_content(url)
        
        if not content['media']:
            await message.answer(f"❌ Ошибка: {status}")
            return

        # Отправляем медиафайлы
        for file in content['media']:
            if file and os.path.exists(file):
                await send_media_to_telegram(message, file)
                await downloader.cleanup_file(file)  # Удаляем после отправки

        # Отправляем текст если есть
        if content.get('text'):
            await send_post_text(message, content['text'][0])
            await downloader.cleanup_file(content['text'][0])

        await message.bot.delete_message(
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )

    except Exception as e:
        logger.error(f"Ошибка обработки: {str(e)}")
        await message.answer("⚠️ Произошла ошибка при обработке поста")

async def send_media_to_telegram(message: Message, file_path: str):
    """Отправка медиа в Telegram с проверкой размера"""
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
    
    if file_size > MAX_TELEGRAM_VIDEO_SIZE:
        await message.answer(f"📦 Файл слишком большой ({file_size:.1f}MB)")
        return

    with open(file_path, 'rb') as f:
        file_data = f.read()
        filename = os.path.basename(file_path)
        
        if filename.lower().endswith(('.mp4', '.mov')):
            await message.answer_video(
                BufferedInputFile(file_data, filename)
            )
        else:
            await message.answer_photo(
                BufferedInputFile(file_data, filename)
            )

async def send_post_text(message: Message, text_file: str):
    """Отправка текста поста частями"""
    if not text_file or not os.path.exists(text_file):
        return
        
    with open(text_file, 'r', encoding='utf-8') as f:
        text = f.read()
        for i in range(0, len(text), 4000):
            await message.answer(
                f"📝 {'(продолжение)' if i > 0 else ''}\n{text[i:i+4000]}"
            )