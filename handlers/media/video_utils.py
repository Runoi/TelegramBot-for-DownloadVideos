import os
from aiogram.types import Message, BufferedInputFile
from config import MAX_FILE_SIZE
from services.utils import compress_video
import logging

logger = logging.getLogger(__name__)


async def send_video_file(
    message: Message,
    filepath: str,
    caption: str = "",
    remove_after: bool = True
) -> bool:
    """
    Отправляет видеофайл с обработкой размера
    :param message: Объект сообщения aiogram
    :param filepath: Путь к файлу
    :param caption: Подпись к видео
    :param remove_after: Удалять ли файл после отправки
    :return: Статус отправки
    """
    try:
        # Проверка размера и сжатие при необходимости
        if os.path.getsize(filepath) > MAX_FILE_SIZE:
            compressed_path = f"{filepath}_compressed.mp4"
            if await compress_video(filepath, compressed_path):
                if remove_after:
                    os.remove(filepath)
                filepath = compressed_path
        
        with open(filepath, 'rb') as f:
            await message.answer_video(
                video=BufferedInputFile(f.read(), filename=os.path.basename(filepath)),
                caption=caption
            )
        
        if remove_after:
            os.remove(filepath)
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки видео: {str(e)}")
        if 'filepath' in locals() and os.path.exists(filepath) and remove_after:
            os.remove(filepath)
        return False