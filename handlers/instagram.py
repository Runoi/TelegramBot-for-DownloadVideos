from aiogram.types import Message, BufferedInputFile
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
downloader = InstagramDownloader()

async def handle_instagram(message: Message, url: str):
    """Основной обработчик для Instagram"""
    try:
        content = await downloader.download_content(url)
        if not content['media']:
            await message.answer("❌ Не удалось загрузить контент")
            return

        for file in content['media']:
            if Path(file).exists():
                await send_media(message, file)
                Path(file).unlink()

        if content.get('text'):
            await message.answer(f"📝 Текст поста:\n{content['text']}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer("⚠️ Ошибка обработки")

async def send_media(message: Message, path: str):
    """Универсальная отправка медиа"""
    with open(path, 'rb') as f:
        data = f.read()
        if path.endswith('.mp4'):
            await message.answer_video(BufferedInputFile(data, "video.mp4"))
        else:
            await message.answer_photo(BufferedInputFile(data, "photo.jpg"))