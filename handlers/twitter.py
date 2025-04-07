from aiogram import types, Bot
from aiogram.types import BufferedInputFile
from services.downloader import download_media
from handlers.media import send_media_group
import logging
import os
from config import MAX_FILE_SIZE
from services.utils import compress_video

logger = logging.getLogger(__name__)

class TwitterHandler:
    async def handle_post(self, message: types.Message, url: str, bot: Bot):
        try:
            # Получаем информацию о посте
            content = await self._get_twitter_content(url)
            if not content:
                raise ValueError("Не удалось получить контент")

            if content.get('text'):
                await self._send_text(message, content['text'])
            
            if content.get('media'):
                await self._handle_media(message, content['media'], bot)

        except Exception as e:
            logger.error(f"Twitter error: {str(e)}", exc_info=True)
            await message.answer(f"❌ Ошибка: {str(e)}")

    async def _get_twitter_content(self, url: str) -> dict:
        """Получаем контент поста (заглушка - реализуйте ваш парсер)"""
        return {'text': 'Пример текста', 'media': {'videos': [url]}}

    async def _send_text(self, message: types.Message, text: str):
        await message.answer(
            f"📝 <b>Текст поста:</b>\n{text}",
            parse_mode="HTML"
        )

    async def _handle_media(self, message: types.Message, media: dict, bot: Bot):
        if media.get('videos'):
            await self._handle_video(message, media['videos'][0], bot)
        elif media.get('images'):
            await send_media_group(message, media['images'], [])

    async def _handle_video(self, message: types.Message, video_url: str, bot: Bot):
        try:
            video_path = await download_media(video_url, message, bot, 'twitter')
            if not video_path:
                raise ValueError("Не удалось скачать видео")

            # Проверка размера файла
            if os.path.getsize(video_path) > MAX_FILE_SIZE:
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
                    video=BufferedInputFile(f.read(), "twitter_video.mp4"),
                    caption="🎥 Видео из Twitter"
                )
        except Exception as e:
            logger.error(f"Video error: {str(e)}")
            await message.answer(f"❌ Ошибка видео: {str(e)}")
        finally:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.remove(video_path)

twitter_handler = TwitterHandler()

async def handle_twitter_post(message: types.Message, url: str, bot: Bot):
    await twitter_handler.handle_post(message, url, bot)