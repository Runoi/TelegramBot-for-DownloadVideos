import aiohttp
import asyncio
import logging
import os
import re
import time
import subprocess
import shutil
from typing import List, Tuple, Optional, Dict
from pathlib import Path
from datetime import datetime

import instaloader
from config import (
    DOWNLOAD_DIR,
    INSTAGRAM_API_ENDPOINT,
    INSTAGRAM_API_KEY,
    USE_INSTAGRAM_API,
    MAX_RETRIES,
    MAX_FILE_SIZE,
    FFMPEG_PATH,
    MAX_MERGED_VIDEO_SIZE,
    MAX_TELEGRAM_VIDEO_SIZE,
    PHOTO_DURATION
)

logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.use_api = USE_INSTAGRAM_API
        if not self.use_api:
            import instaloader
            self.loader = instaloader.Instaloader(
                quiet=True,
                download_pictures=True,
                download_videos=True,
                save_metadata=True,
                filename_pattern="{shortcode}",
                dirname_pattern=DOWNLOAD_DIR,
                post_metadata_txt_pattern="{shortcode}_caption.txt"
            )
        self._ensure_directory_exists(DOWNLOAD_DIR)
        logger.info(f"Download directory: {os.path.abspath(DOWNLOAD_DIR)}")

    def _ensure_directory_exists(self, path: str):
        """Создает директорию если она не существует"""
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {str(e)}")
            raise

    def _safe_path(self, path: str) -> str:
        """Обрабатывает пути для Windows и других ОС"""
        path = os.path.abspath(path)
        if os.name == 'nt':  # Для Windows
            if not path.startswith('\\\\?\\'):
                path = '\\\\?\\' + path
        return path

    async def download_content(self, url: str, merge_all: bool = False) -> Tuple[Dict[str, List[str]], str]:
        """
        Основной метод загрузки контента
        :return: ({'media': [...], 'text': [...]}, status)
        """
        try:
            self._check_disk_space()
            result = {'media': [], 'text': []}
            
            # Загрузка контента
            media_files, status = await self._download_content_raw(url)
            result['media'] = media_files
            
            if not media_files:
                return result, status
                
            # Извлечение текста
            text_file = await self._extract_post_text(url)
            if text_file:
                result['text'].append(text_file)
            if '/stories/' in url:
                merge_all = True
                # Объединение медиа если требуется
                if merge_all and len(media_files) > 1:
                    merged_file = await self._merge_all_media(media_files)
                    if merged_file:
                        # Удаляем оригиналы и добавляем объединенный файл
                        for f in media_files:
                            await self._safe_remove_file(f)
                        result['media'] = [merged_file]
                        status += " (media merged)"
            
            # Сжатие видео если нужно
            final_media = []
            for file in result['media']:
                if file.lower().endswith(('.mp4', '.mov')):
                    compressed = await self._process_video_file(file)
                    final_media.append(compressed if compressed else file)
                else:
                    final_media.append(file)
            result['media'] = final_media

            return result, status

        except Exception as e:
            logger.error(f"Download content failed: {str(e)}")
            return {'media': [], 'text': []}, f"Error: {str(e)}"

    def _check_disk_space(self):
        """Проверяет доступное место на диске"""
        try:
            total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
            min_space = 500 * 1024 * 1024  # 500MB минимально
            if free < min_space:
                raise RuntimeError(
                    f"Not enough disk space. Need {min_space//(1024*1024)}MB, "
                    f"available {free//(1024*1024)}MB"
                )
        except Exception as e:
            logger.error(f"Disk space check failed: {str(e)}")
            raise

    async def _merge_all_media(self, media_files: List[str]) -> Optional[str]:
        """Объединяет фото и видео в одно видео"""
        if not media_files:
            return None

        # Создаем уникальную временную папку
        temp_dir = self._safe_path(os.path.join(DOWNLOAD_DIR, f"temp_{int(time.time())}"))
        self._ensure_directory_exists(temp_dir)

        output_file = self._safe_path(os.path.join(DOWNLOAD_DIR, f"merged_{int(time.time())}.mp4"))

        try:
            # 1. Конвертируем все медиафайлы в видео сегменты
            video_segments = []
            for i, file in enumerate(media_files):
                if not os.path.exists(file):
                    logger.error(f"Исходный файл не найден: {file}")
                    continue

                ext = os.path.splitext(file)[1].lower()
                segment_path = self._safe_path(os.path.join(temp_dir, f"segment_{i}.mp4"))

                if ext in ('.jpg', '.jpeg', '.png', '.webp'):
                    cmd = [
                        FFMPEG_PATH,
                        '-loop', '1',
                        '-i', self._safe_path(file),
                        '-c:v', 'libx264',
                        '-t', str(PHOTO_DURATION),
                        '-pix_fmt', 'yuv420p',
                        '-crf', '28',  # Немного больше сжатия для ускорения
                        '-movflags', '+faststart',
                        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                        '-y',
                        segment_path
                    ]
                elif ext in ('.mp4', '.mov'):
                    cmd = [
                        FFMPEG_PATH,
                        '-i', self._safe_path(file),
                        '-c', 'copy',
                        '-crf', '28',  # Немного больше сжатия для ускорения
                        '-movflags', '+faststart',
                        '-y',
                        segment_path
                    ]
                else:
                    continue

                try:
                    process = await asyncio.create_subprocess_exec(*cmd)
                    await process.wait()
                    
                    if process.returncode == 0 and os.path.exists(segment_path):
                        video_segments.append(segment_path)
                    else:
                        logger.error(f"Не удалось создать сегмент {i}")
                except Exception as e:
                    logger.error(f"Ошибка обработки сегмента {i}: {str(e)}")

            if not video_segments:
                logger.error("Не создано ни одного валидного видео сегмента")
                return None

            # 2. Создаем список для конкатенации
            list_file = self._safe_path(os.path.join(temp_dir, "concat_list.txt"))
            try:
                with open(list_file, 'w') as f:
                    for segment in video_segments:
                        # Используем абсолютные пути в списке конкатенации
                        f.write(f"file '{segment}'\n")
            except Exception as e:
                logger.error(f"Ошибка создания списка конкатенации: {str(e)}")
                return None

            # 3. Выполняем объединение
            concat_cmd = [
                FFMPEG_PATH,
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,  # Абсолютный путь к списку
                '-c', 'copy',
                '-crf', '28',  # Немного больше сжатия для ускорения
                '-movflags', '+faststart',
                '-y',
                output_file  # Абсолютный путь к выходному файлу
            ]

            try:
                # Создаем родительские директории для выходного файла
                self._ensure_directory_exists(os.path.dirname(output_file))
                
                process = await asyncio.create_subprocess_exec(
                    *concat_cmd,
                    cwd=temp_dir
                )
                await process.wait()

                # Улучшенная проверка результата
                if process.returncode != 0 or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                    logger.error(f"Конкатенация не удалась. Код возврата: {process.returncode}")
                    if os.path.exists(output_file):
                        os.remove(output_file)
                    return None
                    
                return output_file
                
            except Exception as e:
                logger.error(f"Ошибка при конкатенации: {str(e)}")
                return None

        except Exception as e:
            logger.error(f"Неожиданная ошибка при объединении медиа: {str(e)}")
            return None
            
        finally:
            # Добавляем небольшую задержку перед очисткой
            await asyncio.sleep(1)
            self._cleanup_temp_directory(temp_dir)

    def _cleanup_temp_directory(self, temp_dir: str):
        """Рекурсивно удаляет временную директорию"""
        try:
            if os.path.exists(temp_dir):
                for root, dirs, files in os.walk(temp_dir, topdown=False):
                    for name in files:
                        try:
                            os.remove(os.path.join(root, name))
                        except Exception as e:
                            logger.error(f"Failed to remove file {name}: {str(e)}")
                    for name in dirs:
                        try:
                            os.rmdir(os.path.join(root, name))
                        except Exception as e:
                            logger.error(f"Failed to remove directory {name}: {str(e)}")
                os.rmdir(temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning temp directory: {str(e)}")

    async def _process_video_file(self, file_path: str) -> Optional[str]:
        """Сжимает видео если превышен лимит размера"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"Video file not found: {file_path}")
                return None

            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            
            if file_size > MAX_TELEGRAM_VIDEO_SIZE:
                compressed_path = self._safe_path(
                    f"{os.path.splitext(file_path)[0]}_compressed.mp4"
                )
                if await self._compress_video(file_path, compressed_path):
                    await self._safe_remove_file(file_path)
                    return compressed_path
        except Exception as e:
            logger.error(f"Video processing failed: {str(e)}")
        return None

    async def _compress_video(self, input_path: str, output_path: str) -> bool:
        """Сжимает видео с сохранением качества"""
        try:
            duration = await self._get_video_duration(input_path)
            if not duration or duration <= 0:
                logger.error(f"Invalid video duration: {duration}")
                return False
                
            target_bitrate = int((MAX_TELEGRAM_VIDEO_SIZE * 8192) / duration)

            cmd = [
                FFMPEG_PATH,
                '-i', self._safe_path(input_path),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-maxrate', f'{target_bitrate}k',
                '-bufsize', f'{target_bitrate * 2}k',
                '-vf', 'scale=-2:720',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-y',
                self._safe_path(output_path)
            ]

            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()
            
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0

        except Exception as e:
            logger.error(f"Compression failed: {str(e)}")
            return False

    async def _get_video_duration(self, video_path: str) -> Optional[float]:
        """Получает длительность видео в секундах"""
        try:
            cmd = [
                FFMPEG_PATH,
                '-i', self._safe_path(video_path),
                '-f', 'null',
                '-'
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE
            )
            _, stderr = await process.communicate()
            
            duration_match = re.search(
                r"Duration: (\d+):(\d+):(\d+\.\d+)", 
                stderr.decode(errors='ignore')
            )
            if duration_match:
                hours = float(duration_match.group(1))
                minutes = float(duration_match.group(2))
                seconds = float(duration_match.group(3))
                return hours * 3600 + minutes * 60 + seconds
            return None
        except Exception as e:
            logger.error(f"Failed to get duration: {str(e)}")
            return None

    async def _extract_post_text(self, url: str) -> Optional[str]:
        """Извлекает текст поста"""
        if '/p/' not in url and '/reel/' not in url and '/tv/' not in url:
            return None
            
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            return None
            
        # Для Instaloader проверяем файл с текстом
        caption_file = self._safe_path(
            os.path.join(DOWNLOAD_DIR, f"{shortcode}_caption.txt")
        )
        if os.path.exists(caption_file):
            return caption_file
            
        # Для API или если файл не создан
        try:
            if not self.use_api:
                post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
                caption = post.caption
                if caption:
                    with open(caption_file, 'w', encoding='utf-8') as f:
                        f.write(caption)
                    return caption_file
        except Exception as e:
            logger.error(f"Failed to extract text: {str(e)}")
            
        return None

    async def _download_content_raw(self, url: str) -> Tuple[List[str], str]:
        """Базовая загрузка контента без обработки"""
        for attempt in range(MAX_RETRIES):
            try:
                if self.use_api:
                    result = await self._download_via_api(url)
                    print(result)
                    # if not result[0]:
                    #     result = await self._download_via_instaloader(url)
                else:
                    result = await self._download_via_instaloader(url)
                
                if result[0]:
                    return result
                
                if attempt == MAX_RETRIES - 1:
                    return result
                
                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    return [], f"Failed after {MAX_RETRIES} attempts: {str(e)}"
                await asyncio.sleep(2 ** attempt)

        return [], "Unknown error occurred"

    async def _download_via_api(self, url: str) -> Tuple[List[str], str]:
        """Загрузка через API"""
        content_type, payload = self._prepare_api_payload(url)
        if not content_type:
            return [], "Unsupported URL type"

        headers = {
            'x-avatar-key': INSTAGRAM_API_KEY,
            'Content-Type': 'application/json'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    INSTAGRAM_API_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        error_msg = await response.text()
                        return [], f"API error {response.status}: {error_msg}"

                    data = await response.json()
                    
                    if not data.get('success'):
                        return [], "API request failed"
                    
                    media_items = data.get('data', [])
                    if not media_items:
                        return [], "No media data found"
                    
                    downloaded_files = []
                    for item in media_items:
                        media_url = item.get('url')
                        if not media_url:
                            continue
                        
                        ext = self._get_file_extension(media_url, item)
                        filename = self._safe_path(
                            os.path.join(
                                DOWNLOAD_DIR,
                                f"insta_{content_type}_{int(time.time())}_{len(downloaded_files)}{ext}"
                            )
                        )
                        
                        if await self._download_media_file(session, media_url, filename):
                            downloaded_files.append(filename)
                    
                    if downloaded_files:
                        return downloaded_files, "Download successful via API"
                    return [], "No downloadable media found"

        except asyncio.TimeoutError:
            return [], "API request timed out"
        except aiohttp.ClientError as e:
            return [], f"Network error: {str(e)}"
        except Exception as e:
            logger.exception("API processing error")
            return [], f"API error: {str(e)}"

    async def _download_media_file(self, session: aiohttp.ClientSession, url: str, filename: str) -> bool:
        """Загрузка одного медиафайла"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    return False
                
                content_size = int(response.headers.get('Content-Length', 0))
                if content_size > MAX_FILE_SIZE * 1024 * 1024:
                    return False
                
                self._ensure_directory_exists(os.path.dirname(filename))
                with open(self._safe_path(filename), 'wb') as f:
                    downloaded = 0
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > MAX_FILE_SIZE * 1024 * 1024:
                            return False
                
                return os.path.exists(filename) and os.path.getsize(filename) > 0

        except Exception as e:
            logger.error(f"Download failed: {url} - {str(e)}")
            return False

    async def _download_via_instaloader(self, url: str) -> Tuple[List[str], str]:
        """Загрузка через Instaloader"""
        try:
            if '/stories/' in url:
                return await self._download_story_instaloader(url)
            return await self._download_post_instaloader(url)
        except Exception as e:
            logger.error(f"Instaloader error: {str(e)}")
            return [], f"Instaloader error: {str(e)}"

    async def _download_post_instaloader(self, url: str) -> Tuple[List[str], str]:
        """Загрузка поста/рила"""
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            return [], "Invalid Instagram URL"

        try:
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            self.loader.download_post(post, target=shortcode)
            await asyncio.sleep(2)

            media_files = self._find_downloaded_files(shortcode)
            if not media_files:
                alt_files = self._find_files_recursive(shortcode)
                if alt_files:
                    return alt_files, "Download successful"
                return [], "Files not found after download"

            return media_files, "Download successful"

        except Exception as e:
            logger.error(f"Post download failed: {str(e)}")
            return [], f"Download failed: {str(e)}"

    async def _download_story_instaloader(self, url: str) -> Tuple[List[str], str]:
        """Загрузка сторис"""
        username, story_id = self._extract_story_info(url)
        if not username or not story_id:
            return [], "Invalid story URL"

        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            stories = list(self.loader.get_stories([profile.userid]))
            
            if not stories:
                return [], "No stories available"

            target_item = next(
                (item for story in stories for item in story.get_items() 
                 if str(item.mediaid) == story_id),
                None
            )

            if not target_item:
                return [], "Story not found"

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{username}_story_{timestamp}"
            self.loader.download_storyitem(target_item, filename=filename)

            media_files = []
            for ext in ['.jpg', '.mp4']:
                path = self._safe_path(os.path.join(DOWNLOAD_DIR, f"{filename}{ext}"))
                if os.path.exists(path):
                    media_files.append(path)

            return media_files if media_files else [], "Downloaded files not found"

        except Exception as e:
            logger.error(f"Story download failed: {str(e)}")
            return [], f"Story download failed: {str(e)}"

    def _find_downloaded_files(self, shortcode: str) -> List[str]:
        """Поиск скачанных файлов по shortcode"""
        media_files = []
        for ext in ['.jpg', '.jpeg', '.png', '.mp4', '.webp']:
            path = self._safe_path(os.path.join(DOWNLOAD_DIR, f"{shortcode}{ext}"))
            if os.path.exists(path):
                media_files.append(path)
        
        if not media_files:
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(shortcode) and f.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.webp')):
                    media_files.append(self._safe_path(os.path.join(DOWNLOAD_DIR, f)))
        
        return media_files

    def _find_files_recursive(self, pattern: str) -> List[str]:
        """Рекурсивный поиск файлов"""
        files = []
        for root, _, filenames in os.walk(DOWNLOAD_DIR):
            for f in filenames:
                if f.startswith(pattern) and f.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.webp')):
                    files.append(self._safe_path(os.path.join(root, f)))
        return files

    def _prepare_api_payload(self, url: str) -> Tuple[Optional[str], dict]:
        """Подготовка запроса к API"""
        if '/stories/' in url:
            username, _ = self._extract_story_info(url)
            if not username:
                return None, {}
            return 'story', {
                "type": "insta_story",
                "user_id": username,
                "video_url": url
            }
        
        if '/reel/' in url:
            return 'reel', {
                "type": "instagram",
                "video_url": url
            }
        
        if '/p/' in url:
            return 'post', {
                "type": "instagram",
                "video_url": url
            }
        
        if '/tv/' in url:
            return 'igtv', {
                "type": "instagram",
                "video_url": url
            }
        
        return None, {}

    def _get_file_extension(self, url: str, item: dict) -> str:
        """Определение расширения файла"""
        url_lower = url.lower()
        if '.mp4' in url_lower:
            return '.mp4'
        if '.jpg' in url_lower or '.jpeg' in url_lower:
            return '.jpg'
        if '.png' in url_lower:
            return '.png'
        if '.webp' in url_lower:
            return '.webp'
        return '.mp4'

    def _extract_shortcode(self, url: str) -> Optional[str]:
        """Извлечение shortcode из URL"""
        patterns = [
            r"(?:https?://)?(?:www\.)?instagram\.com/p/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/reel/([^/?#]+)",
            r"(?:https?://)?(?:www\.)?instagram\.com/tv/([^/?#]+)"
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_story_info(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Извлечение информации о сторис"""
        pattern = r"instagram\.com/stories/([^/]+)/(\d+)"
        match = re.search(pattern, url, re.IGNORECASE)
        return (match.group(1), match.group(2)) if match else (None, None)

    async def _safe_remove_file(self, path: str):
        """Безопасное удаление файла"""
        try:
            if path and os.path.exists(path):
                os.remove(self._safe_path(path))
        except Exception as e:
            logger.error(f"Failed to remove file: {path} - {str(e)}")