from config import MAX_FILE_SIZE
from services.utils import compress_video
from services.vk_parser import vk_parser
from services.downloader import download_vk_video
from aiogram import Bot, types
import logging
import os

logger = logging.getLogger(__name__)

MAX_TELEGRAM_SIZE = 50 * 1024 * 1024  # 50MB в байтах

async def handle_vk_video_download(message: types.Message, url: str,bot:Bot):
    try:
        progress = await message.answer("⏳ Подготовка к загрузке (до 500 сек.)...")
        
        # 1. Загрузка
        video_path = await download_vk_video(url,message,bot)
        file_size = os.path.getsize(video_path)
        
        # 2. Проверка размера
        if file_size > 50 * 1024 * 1024:  # 50MB
            await progress.edit_text("⚠️ Видео слишком большое, сжимаю...")
            compressed_path = f"{video_path}_compressed.mp4"
            
            if not await compress_video(video_path, compressed_path, 45):
                await progress.edit_text("❌ Не удалось сжать видео. Отправляю ссылку...")
                await message.answer(f"Скачайте оригинал: {url}")
                return
                
            os.remove(video_path)
            video_path = compressed_path
        
        # 3. Отправка
        await progress.edit_text("📤 Отправляю видео...")
        with open(video_path, 'rb') as f:
            await bot.send_video(chat_id=message.chat.id,
                video=types.BufferedInputFile(f.read(), filename="video.mp4"),
                caption=f"Ваше видео готово! @prorusaver_bot"
            )
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        
    finally:
        if 'video_path' in locals() and os.path.exists(video_path):
            os.remove(video_path)
        if 'progress' in locals():
            await progress.delete()