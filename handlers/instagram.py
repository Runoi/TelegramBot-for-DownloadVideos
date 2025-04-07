from aiogram.types import Message, BufferedInputFile
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR, MAX_TELEGRAM_VIDEO_SIZE
import os
import logging
import asyncio

logger = logging.getLogger(__name__)
downloader = InstagramDownloader()

async def handle_instagram_post(message: Message, url: str):
    """Основной обработчик для Instagram"""
    try:
        if not url or not url.strip():
            await message.answer("❌ Не получена ссылка")
            return

        status_msg = await message.answer("🔄 Загрузка контента...")
        
        # Получаем контент через сервис
        content, status = await downloader.download_content(url)
        
        if not content.get('media'):
            await message.answer(f"❌ {status}")
            return

        # Отправка медиафайлов
        for file in content['media']:
            if file and isinstance(file, str) and os.path.exists(file):
                try:
                    await send_media_to_telegram(message, file)
                except Exception as e:
                    logger.error(f"Ошибка отправки файла {file}: {e}")
                finally:
                    await downloader.cleanup_file(file)

        # Отправка текста
        if content.get('text') and content['text'][0]:
            await send_post_text(message, content['text'][0])
            await downloader.cleanup_file(content['text'][0])

        await message.bot.delete_message(
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )

    except Exception as e:
        logger.error(f"Ошибка обработки: {str(e)}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при обработке запроса")

async def send_media_to_telegram(message: Message, file_path: str):
    """Безопасная отправка медиафайла"""
    try:
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Файл не найден: {file_path}")
            return

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

    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {str(e)}")
        raise

async def send_post_text(message: Message, text_file: str):
    """Отправка текста поста с проверками"""
    if not text_file or not os.path.exists(text_file):
        logger.warning(f"Текстовый файл не найден: {text_file}")
        return

    try:
        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read()
            if not text.strip():
                return
                
            for i in range(0, len(text), 4000):
                await message.answer(
                    f"📝 {'(продолжение)' if i > 0 else ''}\n{text[i:i+4000]}"
                )
    except Exception as e:
        logger.error(f"Ошибка чтения текста: {str(e)}")