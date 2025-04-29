from aiogram import types, Bot
from aiogram.types import BufferedInputFile, InputMediaPhoto
from services.downloader import download_image, download_twitter_video
import logging
import os
from config import MAX_FILE_SIZE
from services.utils import compress_video
from services.twitter import TwitterService
import asyncio
from typing import List

logger = logging.getLogger(__name__)

class TwitterHandler:
    MAX_IMAGES = 4  # Лимит Telegram на медиагруппу
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

    async def handle_post(self, message: types.Message, url: str, bot: Bot):
        """Основной обработчик Twitter-поста"""
        try:
            twitter_service = TwitterService()
            content, error = await twitter_service.get_twitter_content(url)
            if error or not content:
                raise ValueError(error or "Не удалось получить контент")

            # Отправка текста
            if content.get('text'):
                await self._send_text(message, content['text'])

            # Отправка медиа
            if content.get('media'):
                await self._handle_media(message, content['media'], content.get('type', ''), bot)

        except Exception as e:
            logger.error(f"Twitter error: {str(e)}", exc_info=True)
            await message.answer(f"❌ Ошибка в хэндлере: {str(e)}")

    async def _send_text(self, message: types.Message, text: str):
        """Отправка текста с форматированием"""
        if len(text) > 4000:
            text = text[:4000] + "... [текст обрезан]"
        await message.answer(f"Текст поста:\n{text}")

    async def _handle_media(self, message: types.Message, media: dict, post_type: str, bot: Bot):
        """Обработка всех типов медиа"""
        try:
            # Обработка изображений
            if media.get('images'):
                await self._handle_images(message, media['images'], bot)

            # Обработка видео (только если тип поста - видео)
            if post_type == 'video' and media.get('videos'):
                await self._handle_video(message, media['videos'][0], bot)

        except Exception as e:
            logger.error(f"Media error: {str(e)}")
            await message.answer(f"❌ Ошибка медиа: {str(e)}")

    async def _handle_images(self, message: types.Message, image_urls: List[str], bot: Bot):
        """Загрузка и отправка изображений с фильтрацией аватарок"""
        if not image_urls:
            return

        downloaded_images = []
        try:
            # Фильтруем только реальные изображения поста (не аватарки)
            filtered_urls = [
                url for url in image_urls 
                if '/media/' in url and not any(x in url for x in ['_normal.', '_bigger.', '_mini.'])
            ]

            if not filtered_urls:
                logger.warning("No valid post images found, only profile avatars")
                return

            # Загружаем изображения (не более MAX_IMAGES)
            for url in filtered_urls[:self.MAX_IMAGES]:
                try:
                    image_path = await download_image(url)
                    if image_path and os.path.getsize(image_path) <= self.MAX_IMAGE_SIZE:
                        downloaded_images.append(image_path)
                except Exception as e:
                    logger.error(f"Error downloading image {url}: {str(e)}")
                    continue

            # Отправка медиагруппы
            if downloaded_images:
                media_group = []
                for img_path in downloaded_images:
                    with open(img_path, 'rb') as f:
                        media_group.append(InputMediaPhoto(
                            media=BufferedInputFile(f.read(), os.path.basename(img_path))
                        ))
                
                await bot.send_media_group(chat_id=message.chat.id, media=media_group)

        finally:
            # Очистка временных файлов
            for img_path in downloaded_images:
                try:
                    if os.path.exists(img_path):
                        os.remove(img_path)
                except:
                    pass

    async def _handle_video(self, message: types.Message, video_url: str, bot: Bot):
        """Загрузка и отправка видео"""
        video_path = None
        compressed_path = None
        
        try:
            # Скачивание видео
            video_path = await download_twitter_video(video_url, message, bot)
            if not video_path or not os.path.exists(video_path):
                raise ValueError("Не удалось скачать видео")

            # Проверка размера и сжатие
            if os.path.getsize(video_path) > MAX_FILE_SIZE:
                compressed_path = f"{video_path}_compressed.mp4"
                if await compress_video(video_path, compressed_path):
                    if os.path.exists(compressed_path) and os.path.getsize(compressed_path) <= MAX_FILE_SIZE:
                        os.remove(video_path)
                        video_path = compressed_path
                    else:
                        if compressed_path and os.path.exists(compressed_path):
                            os.remove(compressed_path)
                        raise ValueError("Видео слишком большое после сжатия")

            # Отправка видео
            with open(video_path, 'rb') as f:
                await bot.send_video(
                    chat_id=message.chat.id,
                    video=BufferedInputFile(f.read(), "twitter_video.mp4"),
                    caption="Видео из Twitter, @prorusaver_bot",
                    supports_streaming=True
                )

        except Exception as e:
            logger.error(f"Video error: {str(e)}")
            raise
        finally:
            # Очистка временных файлов
            for path in [video_path, compressed_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass

twitter_handler = TwitterHandler()

async def handle_twitter_post(message: types.Message, url: str, bot: Bot):
    await twitter_handler.handle_post(message, url, bot)