import os
import re
import asyncio
import logging
from functools import lru_cache
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Dict, Optional, Tuple
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class TwitterService:
    def __init__(self):
        self.media_pattern = re.compile(r'https://pbs\.twimg\.com/media/[^\?]+')
        self.driver = None

    async def init_driver(self):
        """Инициализация Selenium драйвера"""
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
        
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)
            return True
        except Exception as e:
            logger.error(f"Driver init failed: {str(e)}")
            return False

    async def close_driver(self):
        """Закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing driver: {str(e)}")
            self.driver = None

    @lru_cache(maxsize=100)
    def normalize_image_url(self, url: str) -> str:
        """Нормализация URL изображений Twitter"""
        if not url or 'pbs.twimg.com' not in url:
            return url
        
        base = url.split('?')[0]
        return f"{base}?name=orig"

    async def get_twitter_content(self, url: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Основной метод получения контента"""
        try:
            # Сначала пробуем через Nitter
            nitter_data = await self._try_nitter(url)
            if nitter_data['success']:
                return nitter_data['data'], None

            # Если Nitter не сработал, используем Selenium
            if not await self.init_driver():
                return None, "Failed to initialize browser"

            return await self._parse_with_selenium(url)
        except Exception as e:
            logger.error(f"Twitter error: {str(e)}", exc_info=True)
            return None, str(e)
        finally:
            await self.close_driver()

    async def _try_nitter(self, url: str) -> Dict:
        """Попытка получить данные через Nitter"""
        try:
            nitter_url = url.replace('twitter.com', 'nitter.net').replace('x.com', 'nitter.net')
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(nitter_url, timeout=10) as resp:
                    soup = BeautifulSoup(await resp.text(), 'html.parser')
                    
                    tweet_text = ""
                    if content_div := soup.find('div', class_='tweet-content'):
                        tweet_text = content_div.get_text('\n').strip()
                    
                    images = []
                    if gallery := soup.find('div', class_='attachments'):
                        images = [
                            f'https://nitter.net{img["src"]}' 
                            for img in gallery.find_all('img') 
                            if img.get('src')
                        ]
                    
                    return {
                        'success': bool(tweet_text or images),
                        'data': {
                            'text': tweet_text,
                            'images': [self.normalize_image_url(img) for img in images[:4]],
                            'videos': []
                        }
                    }
        except Exception:
            return {'success': False}

    async def _parse_with_selenium(self, url: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Парсинг через Selenium"""
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, '//article')))
            
            # Дополнительная прокрутка
            self.driver.execute_script("window.scrollBy(0, 500);")
            await asyncio.sleep(2)

            # Получаем текст
            text_elements = self.driver.find_elements(By.XPATH, '//div[@data-testid="tweetText"]')
            text = "\n".join([el.text for el in text_elements if el.text]) or None

            # Получаем медиа
            media = await self._extract_media()
            
            return {
                'text': text,
                'type': 'video' if media['videos'] else 'photo' if media['images'] else 'text',
                'media': media
            }, None
        except Exception as e:
            return None, f"Selenium parsing error: {str(e)}"

    async def _extract_media(self) -> Dict:
        """Извлечение медиа"""
        media = {'images': [], 'videos': []}
        
        # Изображения
        img_elements = self.driver.find_elements(By.XPATH, '//img[contains(@src, "twimg.com")]')
        for img in img_elements:
            if src := img.get_attribute('src'):
                media['images'].append(self.normalize_image_url(src))
        
        # Видео
        video_elements = self.driver.find_elements(By.XPATH, '//video | //div[@data-testid="videoPlayer"]')
        for video in video_elements:
            if src := video.get_attribute('src') or video.get_attribute('data-video-url'):
                media['videos'].append(src.split('?')[0])
        
        return media

# Глобальный экземпляр сервиса
twitter_service = TwitterService()

async def get_twitter_post(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Публичный интерфейс для получения Twitter поста"""
    return await twitter_service.get_twitter_content(url)