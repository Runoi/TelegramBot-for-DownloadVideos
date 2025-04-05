from aiogram.types import Message, BufferedInputFile
from services.instagram import InstagramDownloader
from config import DOWNLOAD_DIR, MAX_FILE_SIZE
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

downloader = InstagramDownloader()

async def handle_instagram(message: Message, url: str):
    """Финальная исправленная версия обработчика"""
    try:
        status_msg = await message.answer("🔄 Загружаю контент...")
        
        files, status = await downloader.download_content(url)  # Изменено с error на status
        
        # Успешная загрузка, но файлов нет
        if status == "Download successful" and not files:
            logger.error(f"Файлы не найдены. Статус: {status}")
            await message.answer("⚠️ Контент загружен, но файлы не обнаружены")
            return
            
        # Реальная ошибка загрузки
        if status != "Download successful":
            await message.answer(f"❌ Ошибка: {status}")
            return

        # Успешная обработка файлов
        success_count = 0
        for file_path in files:
            try:
                if await send_media_file(message, file_path):
                    success_count += 1
            finally:
                await safe_remove_file(file_path)

        # Финализация
        await message.bot.delete_message(message.chat.id, status_msg.message_id)
        if success_count == 0:
            await message.answer("⚠️ Не удалось отправить ни одного файла")

    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}", exc_info=True)
        await message.answer("💥 Критическая ошибка при обработке запроса")

async def send_media_file(message: Message, file_path: str) -> bool:
    """Безопасная отправка файла с контролем размера"""
    if not os.path.exists(file_path):
        logger.warning(f"Файл исчез: {file_path}")
        return False

    file_size = os.path.getsize(file_path) / 1024 / 1024  # MB
    if file_size > MAX_FILE_SIZE:
        await message.answer(
            f"📦 Файл слишком большой ({file_size:.1f}MB > {MAX_FILE_SIZE}MB)\n"
            f"Имя: {os.path.basename(file_path)}"
        )
        return False

    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
            filename = os.path.basename(file_path)
            
            if filename.lower().endswith(('.mp4', '.mov')):
                await message.answer_video(BufferedInputFile(file_data, filename))
            else:
                await message.answer_photo(BufferedInputFile(file_data, filename))
            
            return True
            
    except Exception as e:
        logger.error(f"Send failed: {file_path} - {str(e)}")
        return False

async def safe_remove_file(path: str):
    """Гарантированное удаление файла"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.error(f"File removal error: {path} - {str(e)}")
    