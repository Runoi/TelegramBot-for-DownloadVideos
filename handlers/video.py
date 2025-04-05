from aiogram import types
import os
from config import MAX_FILE_SIZE
from services.downloader import download_video
from services.utils import compress_video
import logging

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("video_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def handle_video_download(message: types.Message, url: str):
    """Обрабатывает запрос на скачивание видео"""
    try:
        await message.answer("⏳ Скачиваю видео...")
        filename = await download_video(url)
        
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

# async def handle_video_download_dzen(message: types.Message, url: str):
#     """Обработчик для видео с Dzen"""
#     try:
#         await message.answer("⏳ Начинаю скачивание видео с Dzen...")
        
#         if "dzen.ru/video/watch/" in url:
#             filename = await download_dzen_video(url)
#         else:
#             filename = await download_video(url)
        
#         if os.path.getsize(filename) > MAX_FILE_SIZE:
#             compressed = f"{filename}_compressed.mp4"
#             if await compress_video(filename, compressed):
#                 os.remove(filename)
#                 filename = compressed
        
#         with open(filename, 'rb') as f:
#             await message.answer_video(
#                 video=types.BufferedInputFile(f.read(), filename=os.path.basename(filename)),
#                 caption="Ваше видео готово!"
#             )
#         os.remove(filename)
        
#     except Exception as e:
#         await message.answer(f"❌ Ошибка: {str(e)}")
#         if 'filename' in locals() and os.path.exists(filename):
#             os.remove(filename)