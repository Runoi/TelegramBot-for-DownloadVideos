import os
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from typing import Dict, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)

class TwitterParser:
    def __init__(self):
        self.driver = None
        self.media_pattern = re.compile(r'https://pbs\.twimg\.com/media/[^\?]+')

    async def _init_driver(self):
        """Инициализация драйвера с улучшенными настройками"""
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,720")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_argument("--blink-settings=imagesEnabled=true")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(60)
            return True
        except Exception as e:
            logger.error(f"Driver init failed: {str(e)}")
            return False

    async def _close_driver(self):
        """Корректное закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing driver: {str(e)}")
            self.driver = None

    async def _extract_media(self):
        """Извлечение медиа с поста с улучшенным поиском"""
        media = {'images': [], 'videos': []}
        
        # Поиск изображений
        img_elements = self.driver.find_elements(By.TAG_NAME, 'img')
        for img in img_elements:
            src = img.get_attribute('src') or ''
            if match := self.media_pattern.search(src):
                clean_url = match.group(0)
                if clean_url not in media['images']:
                    media['images'].append(clean_url)
        
        # Поиск видео
        video_elements = self.driver.find_elements(By.TAG_NAME, 'video')
        for video in video_elements:
            if src := video.get_attribute('src'):
                clean_url = src.split('?')[0]
                if clean_url not in media['videos']:
                    media['videos'].append(clean_url)
        
        return media

    async def get_twitter_content(self, url: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Улучшенный метод получения контента с Twitter"""
        if not await self._init_driver():
            return None, "Не удалось инициализировать WebDriver"

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 45).until(
                EC.presence_of_element_located((By.XPATH, '//article'))
            )
            
            # Дополнительная прокрутка и ожидание
            for _ in range(3):
                self.driver.execute_script("window.scrollBy(0, 300);")
                await asyncio.sleep(1.5)

            # Получаем текст поста
            text_elements = self.driver.find_elements(By.XPATH, '//div[@data-testid="tweetText"]')
            text = "\n".join([el.text for el in text_elements if el.text]) or None

            # Получаем медиа
            media = await self._extract_media()
            
            # Определяем тип контента
            content_type = "text"
            if media['videos']:
                content_type = "video"
            elif media['images']:
                content_type = "photo"

            return {
                'text': text,
                'type': content_type,
                'media': media
            }, None

        except Exception as e:
            logger.error(f"Twitter parsing error: {str(e)}", exc_info=True)
            return None, f"Ошибка парсинга Twitter: {str(e)}"
        finally:
            await self._close_driver()

twitter_parser = TwitterParser()

async def get_twitter_content(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    return await twitter_parser.get_twitter_content(url)

__all__ = ['get_twitter_content']