import logging
import time
import instaloader
import os
import re
from datetime import datetime
from typing import List, Tuple, Optional
from pathlib import Path
from config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.loader = instaloader.Instaloader(
            quiet=False,  # Включаем логирование Instaloader
            download_pictures=True,
            download_videos=True,
            save_metadata=False,
            compress_json=False,
            filename_pattern="{shortcode}",
            dirname_pattern=DOWNLOAD_DIR,
            download_geotags=False,
            download_comments=False,
            post_metadata_txt_pattern=""
        )
        Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
        logger.info(f"Download directory: {os.path.abspath(DOWNLOAD_DIR)}")

    async def download_content(self, url: str) -> Tuple[List[str], str]:
        """Универсальный метод для скачивания"""
        try:
            if '/stories/' in url:
                return await self.download_story(url)
            return await self.download_post_or_reel(url)
        except Exception as e:
            logger.error(f"Download error: {str(e)}", exc_info=True)
            return [], f"Error: {str(e)}"

    async def download_post_or_reel(self, url: str) -> Tuple[List[str], str]:
        """Улучшенное скачивание постов и рилсов"""
        try:
            shortcode = self._extract_shortcode(url)
            if not shortcode:
                return [], "Invalid Instagram URL"

            logger.info(f"Starting download for shortcode: {shortcode}")
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            
            # Скачиваем с таймаутом
            self.loader.download_post(post, target=shortcode)
            time.sleep(2)  # Даем время на сохранение файлов

            # Ищем все возможные файлы
            media_files = self._find_downloaded_files(shortcode)
            logger.info(f"Found files: {media_files}")

            if not media_files:
                # Проверяем альтернативные пути
                alt_files = self._find_files_recursive(shortcode)
                if alt_files:
                    return alt_files, "Download successful"
                
                return [], self._get_debug_info(shortcode)

            return media_files, "Download successful"

        except instaloader.exceptions.PrivateProfileNotFollowedException:
            return [], "Private account - login required"
        except instaloader.exceptions.QueryReturnedBadRequestException:
            return [], "Instagram blocked the request. Try again later."
        except Exception as e:
            logger.error(f"Download failed: {str(e)}", exc_info=True)
            return [], f"Error: {str(e)}"

    def _find_downloaded_files(self, shortcode: str) -> List[str]:
        """Ищет файлы по шаблону"""
        media_files = []
        for ext in ['.jpg', '.jpeg', '.png', '.mp4', '.webp']:
            path = os.path.join(DOWNLOAD_DIR, f"{shortcode}{ext}")
            if os.path.exists(path):
                media_files.append(path)
        
        # Проверяем альтернативные имена (новые версии Instaloader)
        if not media_files:
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(shortcode) and f.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.webp')):
                    media_files.append(os.path.join(DOWNLOAD_DIR, f))
        
        return media_files

    def _find_files_recursive(self, shortcode: str) -> List[str]:
        """Рекурсивный поиск файлов в подпапках"""
        media_files = []
        for root, _, files in os.walk(DOWNLOAD_DIR):
            for f in files:
                if f.startswith(shortcode) and f.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.webp')):
                    media_files.append(os.path.join(root, f))
        return media_files

    def _get_debug_info(self, shortcode: str) -> str:
        """Возвращает информацию для отладки"""
        debug_info = [
            f"Debug info for {shortcode}:",
            f"Download dir: {os.path.abspath(DOWNLOAD_DIR)}",
            f"Files in dir: {os.listdir(DOWNLOAD_DIR)}",
            "Possible reasons:",
            "1. Instaloader saved files with different names",
            "2. Files are in subdirectories",
            "3. Instagram blocked the download",
            "4. Network issues"
        ]
        return "\n".join(debug_info)

    async def download_story(self, story_url: str) -> Tuple[List[str], str]:
        """Специальный метод для скачивания сторис"""
        try:
            username, story_id = self._extract_story_info(story_url)
            if not username or not story_id:
                return [], "Invalid Instagram Story URL"

            profile = instaloader.Profile.from_username(self.loader.context, username)
            stories = list(self.loader.get_stories([profile.userid]))
            
            if not stories:
                return [], "No active stories found"

            # Ищем конкретную сторис
            target_item = next(
                (item for story in stories for item in story.get_items() 
                 if str(item.mediaid) == story_id),
                None
            )

            if not target_item:
                return [], "Story not found or expired"

            # Скачиваем с уникальным именем
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{username}_story_{timestamp}"
            self.loader.download_storyitem(target_item, filename=filename)

            # Проверяем результат
            media_files = []
            for ext in ['.jpg', '.mp4']:
                path = os.path.join(DOWNLOAD_DIR, f"{filename}{ext}")
                if os.path.exists(path):
                    media_files.append(path)

            return media_files if media_files else [], "Downloaded files not found"

        except Exception as e:
            return [], f"Error: {str(e)}"

    def _extract_shortcode(self, url: str) -> Optional[str]:
        """Извлекает shortcode для постов/рилсов"""
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
        """Извлекает username и story_id из URL сторис"""
        pattern = r"instagram\.com/stories/([^/]+)/(\d+)"
        match = re.search(pattern, url, re.IGNORECASE)
        return (match.group(1), match.group(2)) if match else (None, None)