from aiogram import Bot, types
import os
from config import MAX_FILE_SIZE
from services.downloader import download_video
from services.utils import compress_video
import logging

logger = logging.getLogger(__name__)

async def handle_video_download(message: types.Message, url: str,bot:Bot):
    """Обрабатывает запрос на скачивание видео"""
    try:
        await message.answer("⏳ Скачиваю видео...")
        filename = await download_video(url,url,bot)
        
        if os.path.getsize(filename) > MAX_FILE_SIZE:
            compressed = f"{filename}_compressed.mp4"
            if await compress_video(filename, compressed):
                os.remove(filename)
                filename = compressed
        
        with open(filename, 'rb') as f:
            await message.answer_video(
                video=types.BufferedInputFile(f.read(), filename=os.path.basename(filename)),
                caption="Ваше видео готово!"
            )
        os.remove(filename)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)