from aiogram import types, Bot
from aiogram.types import BufferedInputFile
from services.twitter_parser import TwitterParser
from services.downloader import download_twitter_video
from handlers.media import send_media_group
import logging
import os
from config import MAX_FILE_SIZE
from services.utils import compress_video

logger = logging.getLogger(__name__)

class TwitterHandler:
    def __init__(self):
        self.parser = TwitterParser()

    async def handle_post(self, message: types.Message, url: str, bot: Bot):
        """Основной обработчик Twitter постов с индикатором прогресса"""
        try:
            # Отправляем начальное сообщение
            progress_msg = await message.answer("⏳ Подключаюсь к Twitter...")
            
            content = await self.parser.get_twitter_content(url)
            if not content:
                raise ValueError("Не удалось получить контент")

            if content.get('text'):
                await self._send_text(message, content['text'])
            
            await self._handle_media(message, content.get('media', {}), bot, progress_msg)
            
        except Exception as e:
            logger.error(f"Twitter error: {str(e)}", exc_info=True)
            await message.answer(f"❌ Ошибка: {str(e)}")

    async def _send_text(self, message: types.Message, text: str):
        """Отправка текста поста с экранированием HTML"""
        await message.answer(
            f"📝 <b>Текст поста:</b>\n{text}",
            parse_mode="HTML"
        )

    async def _handle_media(self, message: types.Message, media: dict, bot: Bot, progress_msg: types.Message):
        """Обработка медиа с индикатором прогресса"""
        if not media:
            return

        if media.get('videos'):
            await self._handle_video(message, media['videos'][0], bot, progress_msg)
        
        if media.get('images'):
            await send_media_group(message, media['images'], [])

    async def _handle_video(self, message: types.Message, video_url: str, bot: Bot, progress_msg: types.Message):
        """Обработка видео с индикатором загрузки"""
        try:
            await bot.edit_message_text(
                "⏳ Скачиваю видео...",
                chat_id=progress_msg.chat.id,
                message_id=progress_msg.message_id
            )
            
            video_path = await download_twitter_video(video_url, message, bot)
            
            # Проверка размера файла
            file_size = os.path.getsize(video_path)
            if file_size > MAX_FILE_SIZE:
                await bot.edit_message_text(
                    "⚠️ Видео слишком большое, пробую сжать...",
                    chat_id=progress_msg.chat.id,
                    message_id=progress_msg.message_id
                )
                
                compressed_path = f"{video_path}_compressed.mp4"
                if await compress_video(video_path, compressed_path):
                    if os.path.getsize(compressed_path) <= MAX_FILE_SIZE:
                        os.remove(video_path)
                        video_path = compressed_path
                    else:
                        os.remove(compressed_path)
                        raise ValueError("Не удалось сжать видео")

            # Отправка видео
            with open(video_path, 'rb') as f:
                await bot.send_video(
                    chat_id=message.chat.id,
                    video=BufferedInputFile(f.read(), filename="twitter_video.mp4"),
                    caption="🎥 Видео из Twitter"
                )
                
        except Exception as e:
            logger.error(f"Video error: {str(e)}")
            await message.answer(f"❌ Ошибка видео: {str(e)}")
            if 'video_url' in locals():
                await message.answer(f"Ссылка: {video_url}")
        finally:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.remove(video_path)
            try:
                await bot.delete_message(progress_msg.chat.id, progress_msg.message_id)
            except:
                pass

twitter_handler = TwitterHandler()

async def handle_twitter_post(message: types.Message, url: str, bot: Bot):
    await twitter_handler.handle_post(message, url, bot)