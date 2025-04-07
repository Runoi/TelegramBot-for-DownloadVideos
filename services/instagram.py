import instaloader
from pathlib import Path
from config import DOWNLOAD_DIR
import asyncio
import re
import logging

logger = logging.getLogger(__name__)

class InstagramDownloader:
    def __init__(self):
        self.loader = instaloader.Instaloader(
            quiet=True,
            dirname_pattern=str(Path(DOWNLOAD_DIR)/'insta'),
            filename_pattern='{shortcode}'
        )

    async def download(self, url: str) -> dict:
        """Унифицированный метод загрузки"""
        try:
            if 'stories' in url:
                return await self._download_story(url)
            return await self._download_post(url)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return {'media': [], 'text': ''}

    async def _download_post(self, url: str) -> dict:
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            return {'media': [], 'text': ''}

        post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
        self.loader.download_post(post, target=shortcode)
        
        media = list(Path(DOWNLOAD_DIR).glob(f"{shortcode}.*"))
        caption = post.caption or ''
        
        return {
            'media': [str(f) for f in media if f.suffix in ('.jpg', '.mp4')],
            'text': caption
        }

    async def _download_story(self, url: str) -> dict:
        username, story_id = re.search(r'/stories/([^/]+)/(\d+)', url).groups()
        profile = instaloader.Profile.from_username(self.loader.context, username)
        
        filename = f"{username}_story_{story_id}"
        self.loader.download_storyitem(
            next(s for s in profile.get_stories() if str(s.mediaid) == story_id),
            filename=filename
        )
        
        return {
            'media': [str(f) for f in Path(DOWNLOAD_DIR).glob(f"{filename}.*")],
            'text': ''
        }

    def _extract_shortcode(self, url: str) -> str:
        return re.search(r'(?:/p/|/reel/|/tv/)([^/]+)', url).group(1)