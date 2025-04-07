from aiogram import types
from aiogram.types import BufferedInputFile
from services.twitter_parser import TwitterParser
from services.downloader import download_twitter_video
from handlers.media import send_media_group
import logging
import html
import os
from config import MAX_FILE_SIZE
from services.utils import compress_video

logger = logging.getLogger(__name__)

class TwitterHandler:
    def __init__(self):
        self.parser = TwitterParser()

    async def handle_post(self, message: types.Message, url: str):
        """Основной обработчик Twitter постов"""
        try:
            await message.answer("⏳ Получаю контент из Twitter...")
            
            # Получаем данные через Selenium
            content = await self.parser.get_twitter_content(url)
            
            if not content:
                raise ValueError("Не удалось получить контент")

            # Отправка текста
            if content.get('text'):
                await self._send_text(message, content['text'])
            
            # Обработка медиа
            await self._handle_media(message, content.get('media', {}))
            
        except Exception as e:
            logger.error(f"Twitter error: {str(e)}", exc_info=True)
            await message.answer(f"❌ Ошибка: {str(e)}")

    async def _send_text(self, message: types.Message, text: str):
        """Отправка текста поста"""
        safe_text = text
        await message.answer(
            f"📝 <b>Текст поста:</b>\n{safe_text}",
            parse_mode="HTML"
        )

    async def _handle_media(self, message: types.Message, media: dict):
        """Обработка медиа контента"""
        if not media:
            return

        # Видео имеет приоритет
        if media.get('videos'):
            await self._handle_video(message, media['videos'][0])
        
        # Затем изображения
        if media.get('images'):
            await send_media_group(message, media['images'], [])
    async def _handle_video(self, message: types.Message, video_url: str):
        """Улучшенная обработка Twitter видео"""
        try:
            await message.answer("⏳ Скачиваю видео... Это может занять до минуты")
            
            # Пробуем скачать видео
            video_path = await download_twitter_video(video_url)
            
            # Проверяем размер файла
            file_size = os.path.getsize(video_path)
            if file_size > MAX_FILE_SIZE:
                compressed_path = f"{video_path}_compressed.mp4"
                await message.answer("⚠️ Видео слишком большое, пробую сжать...")
                
                if await compress_video(video_path, compressed_path):
                    if os.path.getsize(compressed_path) <= MAX_FILE_SIZE:
                        os.remove(video_path)
                        video_path = compressed_path
                    else:
                        os.remove(compressed_path)
                        raise ValueError("Не удалось сжать видео до допустимого размера")
            
            # Отправляем видео
            with open(video_path, 'rb') as f:
                await message.answer_video(
                    video=BufferedInputFile(
                        f.read(),
                        filename="twitter_video.mp4"
                    ),
                    caption="🎥 Видео из Twitter"
                )
                
        except Exception as e:
            logger.error(f"Video handling error: {str(e)}")
            await message.answer(f"❌ Не удалось обработать видео: {str(e)}")
            
            # Пробуем отправить хотя бы превью
            try:
                if 'video_url' in locals():
                    await message.answer(f"Ссылка на видео: {video_url}")
            except:
                pass
        finally:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.remove(video_path)
    # Глобальный экземпляр обработчика
twitter_handler = TwitterHandler()

async def handle_twitter_post(message: types.Message, url: str):
    """Публичный интерфейс для обработки Twitter"""
    await twitter_handler.handle_post(message, url)