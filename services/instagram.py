import os
import re
import logging
import shutil
import time
import instaloader
import asyncio
import subprocess
from typing import Dict, List, Tuple, Optional
from config import DOWNLOAD_DIR, FFMPEG_PATH, PHOTO_DURATION, MAX_MERGED_VIDEO_SIZE

logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.loader = instaloader.Instaloader(
            quiet=True,
            dirname_pattern=os.path.join(DOWNLOAD_DIR, 'insta'),
            filename_pattern='{shortcode}',
            download_pictures=True,
            download_videos=True,
            save_metadata=False
        )

    async def download_content(self, url: str, merge_all: bool = False) -> Tuple[Dict, str]:
        """Загрузка контента с опцией объединения"""
        try:
            # Загрузка исходных файлов
            media_files, status = await self._download_raw_content(url)
            if not media_files:
                return {'media': [], 'text': []}, status

            # Объединение медиа если требуется
            if merge_all and len(media_files) > 1:
                merged_file = await self._merge_media_files(media_files)
                if merged_file:
                    # Заменяем оригинальные файлы объединённым
                    for f in media_files:
                        await self.cleanup_file(f)
                    media_files = [merged_file]

            # Обработка текста
            text_file = await self._extract_post_text(url)
            
            return {
                'media': media_files,
                'text': [text_file] if text_file else []
            }, status

        except Exception as e:
            logger.error(f"Ошибка загрузки: {str(e)}")
            return {'media': [], 'text': []}, f"Ошибка: {str(e)}"

    async def _merge_media_files(self, files: List[str]) -> Optional[str]:
        """Объединение медиафайлов в одно видео"""
        try:
            temp_dir = os.path.join(DOWNLOAD_DIR, f"temp_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 1. Конвертируем все файлы в MP4 сегменты
            segments = []
            for i, file in enumerate(files):
                segment_path = os.path.join(temp_dir, f"segment_{i}.mp4")
                if file.endswith(('.jpg', '.jpeg', '.png')):
                    cmd = [
                        FFMPEG_PATH, '-loop', '1', '-i', file,
                        '-c:v', 'libx264', '-t', str(PHOTO_DURATION),
                        '-pix_fmt', 'yuv420p', '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                        '-y', segment_path
                    ]
                else:  # Видео файлы
                    cmd = [
                        FFMPEG_PATH, '-i', file, '-c', 'copy', '-y', segment_path
                    ]
                
                process = await asyncio.create_subprocess_exec(*cmd)
                await process.wait()
                if process.returncode == 0:
                    segments.append(segment_path)

            # 2. Создаём список для конкатенации
            list_file = os.path.join(temp_dir, "list.txt")
            with open(list_file, 'w') as f:
                for seg in segments:
                    f.write(f"file '{seg}'\n")

            # 3. Объединяем сегменты
            output_file = os.path.join(DOWNLOAD_DIR, f"merged_{int(time.time())}.mp4")
            cmd = [
                FFMPEG_PATH, '-f', 'concat', '-safe', '0', '-i', list_file,
                '-c', 'copy', '-movflags', '+faststart', '-y', output_file
            ]
            
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()
            
            # Проверяем результат
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                return output_file
            return None

        except Exception as e:
            logger.error(f"Ошибка объединения: {str(e)}")
            return None
        finally:
            # Очистка временных файлов
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)

    async def _download_raw_content(self, url: str) -> Tuple[List[str], str]:
        """Базовая загрузка без обработки"""
        if '/stories/' in url:
            return await self._download_story(url)
        return await self._download_post(url)

    # ... (остальные методы из предыдущей версии остаются без изменений)