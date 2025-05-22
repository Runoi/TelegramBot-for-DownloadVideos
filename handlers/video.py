from aiogram import Bot, types
import os
from config import MAX_FILE_SIZE
from services.downloader import download_video
from services.utils import compress_video
import logging

logger = logging.getLogger(__name__)

async def handle_video_download(message: types.Message, url: str,bot:Bot):
    """Обрабатывает запрос на скачивание видео"""
    print(url)
    try:
        await message.answer("⏳ Подготовка к загрузке (до 500 сек.)...")
        filename = await download_video(url,message,bot)
        
        # if os.path.getsize(filename) > MAX_FILE_SIZE:
        #     compressed = f"{filename}_compressed.mp4"
        #     if await compress_video(filename, compressed):
        #         os.remove(filename)
        #         filename = compressed
        
        with open(filename, 'rb') as f:
            await message.answer_video(
                video=types.BufferedInputFile(f.read(), filename=os.path.basename(filename)),
                caption="Ваше видео готово! @prorusaver_bot"
            )
        os.remove(filename)
        
    except Exception as e:
        logger.info(str(e))
        await message.answer(f"Что-то пошло не так, попробуйте снова")
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)