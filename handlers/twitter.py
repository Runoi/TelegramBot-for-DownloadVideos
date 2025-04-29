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
        """Основной обработчик Twitter-поста с улучшенной обработкой ошибок"""
        try:
            logger.info(f"Начало обработки Twitter-поста: {url}")
            
            # 1. Получение контента
            twitter_service = TwitterService()
            content, error = await twitter_service.get_twitter_content(url)
            
            if error or not content:
                error_msg = error or "Не удалось получить контент"
                logger.error(f"Ошибка получения контента: {error_msg}")
                raise ValueError(error_msg)

            logger.debug(f"Полученный контент: {content}")

            # 2. Отправка текста (если есть)
            if content.get('text'):
                try:
                    await self._send_text(message, content['text'])
                    logger.debug("Текст поста успешно отправлен")
                except Exception as text_error:
                    logger.error(f"Ошибка отправки текста: {str(text_error)}")

            # 3. Отправка медиа
            if content.get('media'):
                try:
                    await self._handle_media(
                        message, 
                        content['media'], 
                        content.get('type', ''), 
                        bot
                    )
                    logger.debug("Медиа успешно обработано")
                except Exception as media_error:
                    logger.error(f"Ошибка обработки медиа: {str(media_error)}")
                    await message.answer("⚠️ Не удалось отправить медиа-контент")

            logger.info("Обработка поста завершена успешно")

        except ValueError as ve:
            logger.error(f"Ошибка значений: {str(ve)}")
            await message.answer(f"❌ {str(ve)}")
        except Exception as e:
            logger.critical(f"Критическая ошибка обработки: {str(e)}", exc_info=True)
            await message.answer("💥 Произошла критическая ошибка при обработке поста")
        finally:
            # Очистка ресурсов при необходимости
            if 'twitter_service' in locals():
                await twitter_service._close_driver()

    async def _send_text(self, message: types.Message, text: str):
        """Отправка текста с форматированием"""
        if len(text) > 4000:
            text = text[:4000] + "... [текст обрезан]"
        await message.answer(f"Текст поста:\n{text}")

    async def _handle_media(self, message: types.Message, media: dict, post_type: str, bot: Bot):
        """Обработка всех типов медиа с улучшенной обработкой ошибок"""
        try:
            logger.info(f"Начало обработки медиа. Тип: {post_type}, данные: {media.keys()}")

            # 1. Обработка изображений (если есть)
            if media.get('images'):
                logger.debug(f"Найдены изображения: {len(media['images'])} шт.")
                try:
                    await self._handle_images(message, media['images'], bot)
                    logger.info("Изображения успешно обработаны")
                except Exception as img_error:
                    logger.error(f"Ошибка обработки изображений: {str(img_error)}", exc_info=True)
                    await message.answer("⚠️ Не удалось отправить изображения")

            # 2. Обработка видео (только если тип поста - видео и есть ссылки)
            if post_type == 'video' and media.get('videos'):
                logger.debug(f"Найдены видео: {len(media['videos'])} шт.")
                if not media['videos'][0]:
                    logger.warning("Пустая ссылка на видео")
                    return

                try:
                    await self._handle_video(message, media['videos'][0], bot)
                    logger.info("Видео успешно обработано")
                except Exception as video_error:
                    logger.error(f"Ошибка обработки видео: {str(video_error)}", exc_info=True)
                    await message.answer("⚠️ Не удалось отправить видео")

        except Exception as e:
            logger.critical(f"Критическая ошибка в _handle_media: {str(e)}", exc_info=True)
            await message.answer("💥 Произошла ошибка при обработке медиа")
        finally:
            logger.debug("Завершение обработки медиа")

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
        """Загрузка и отправка видео с улучшенной обработкой ошибок"""
        video_path = None
        compressed_path = None
        
        try:
            # 1. Логирование начала процесса
            logger.info(f"Начало обработки видео: {video_url}")
            
            # 2. Скачивание видео
            try:
                video_path = await download_twitter_video(video_url, message, bot)
                if not video_path or not os.path.exists(video_path):
                    raise ValueError("Не удалось скачать видео")
                logger.debug(f"Видео скачано: {video_path} ({os.path.getsize(video_path)/1024/1024:.2f} MB)")
            except Exception as download_error:
                logger.error(f"Ошибка загрузки видео: {str(download_error)}")
                raise ValueError("Ошибка загрузки видео с Twitter")

            # 3. Проверка и обработка размера видео
            original_size = os.path.getsize(video_path)
            needs_compression = original_size > MAX_FILE_SIZE
            
            if needs_compression:
                logger.info(f"Видео требует сжатия (размер: {original_size/1024/1024:.2f} MB)")
                compressed_path = f"{video_path}_compressed.mp4"
                
                try:
                    success = await compress_video(video_path, compressed_path)
                    if not success or not os.path.exists(compressed_path):
                        raise ValueError("Ошибка сжатия видео")
                    
                    compressed_size = os.path.getsize(compressed_path)
                    logger.debug(f"Видео сжато: {compressed_size/1024/1024:.2f} MB")
                    
                    if compressed_size > MAX_FILE_SIZE:
                        raise ValueError(f"Видео слишком большое после сжатия ({compressed_size/1024/1024:.2f} MB)")
                    
                    # Удаляем оригинал, если сжатие успешно
                    try:
                        os.remove(video_path)
                        video_path = compressed_path
                    except Exception as remove_error:
                        logger.error(f"Ошибка удаления оригинала: {str(remove_error)}")
                        raise ValueError("Ошибка обработки видео")
                        
                except Exception as compression_error:
                    logger.error(f"Ошибка сжатия: {str(compression_error)}")
                    if compressed_path and os.path.exists(compressed_path):
                        try:
                            os.remove(compressed_path)
                        except:
                            pass
                    raise ValueError("Не удалось обработать видео")

            # 4. Отправка видео в Telegram
            try:
                with open(video_path, 'rb') as f:
                    await bot.send_video(
                        chat_id=message.chat.id,
                        video=BufferedInputFile(
                            f.read(),
                            filename="twitter_video.mp4"
                        ),
                        caption="Видео из Twitter, @prorusaver_bot",
                        supports_streaming=True,
                        width=1280,  # Оптимальное разрешение
                        height=720,
                        parse_mode="HTML"
                    )
                logger.info("Видео успешно отправлено")
                
            except Exception as send_error:
                logger.error(f"Ошибка отправки видео: {str(send_error)}")
                raise ValueError("Не удалось отправить видео")

        except ValueError as ve:
            logger.error(f"Ошибка обработки видео: {str(ve)}")
            await message.answer(f"❌ {str(ve)}")
        except Exception as e:
            logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
            await message.answer("💥 Произошла критическая ошибка при обработке видео")
        finally:
            # 5. Очистка временных файлов
            for path in [video_path, compressed_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        logger.debug(f"Временный файл удален: {path}")
                    except Exception as clean_error:
                        logger.error(f"Ошибка удаления {path}: {str(clean_error)}")

twitter_handler = TwitterHandler()

async def handle_twitter_post(message: types.Message, url: str, bot: Bot):
    await twitter_handler.handle_post(message, url, bot)