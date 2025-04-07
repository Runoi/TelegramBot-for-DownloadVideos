import os
import asyncio
import logging
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service  # Добавлен импорт Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

class TwitterParser:
    def __init__(self):
        self.driver = None

    async def init_driver(self):
        """Инициализация Selenium драйвера"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.binary_location = '/opt/google/chrome/chrome'
        
        try:
            # Явное создание Service объекта
            service = Service(executable_path='/usr/local/bin/chromedriver')
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)
            return True
        except Exception as e:
            logger.error(f"Driver init failed: {str(e)}")
            return False

    async def get_twitter_content(self, url: str) -> Optional[Dict]:
        """Получение контента через Selenium"""
        if not await self.init_driver():
            return None

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, '//article'))
            )
            
            # Прокрутка для загрузки медиа
            self.driver.execute_script("window.scrollBy(0, 500);")
            await asyncio.sleep(2)

            # Получаем текст
            text = self._extract_text()
            
            # Получаем медиа
            media = self._extract_media()
            
            return {
                'text': text,
                'media': media
            }
        except Exception as e:
            logger.error(f"Parsing error: {str(e)}")
            return None
        finally:
            await self.close_driver()

    def _extract_text(self) -> str:
        """Извлечение текста поста"""
        try:
            elements = self.driver.find_elements(By.XPATH, '//div[@data-testid="tweetText"]')
            return "\n".join([el.text for el in elements if el.text]) or ""
        except Exception as e:
            logger.warning(f"Text extraction error: {str(e)}")
            return ""

    def _extract_media(self) -> Dict:
        """Улучшенное извлечение медиа контента"""
        media = {'images': [], 'videos': []}
        
        # 1. Извлечение изображений
        try:
            imgs = self.driver.find_elements(
                By.XPATH, 
                '//div[@data-testid="tweetPhoto"]//img | '  # Основные изображения
                '//div[contains(@class, "media-image")]//img | '  # Альтернативный вариант
                '//img[contains(@src, "twimg.com/media/")]'  # Прямые ссылки на изображения
            )
            media['images'] = [
                img.get_attribute('src') or img.get_attribute('srcset') 
                for img in imgs 
                if img.get_attribute('src') or img.get_attribute('srcset')
            ]
        except Exception as e:
            logger.warning(f"Image extraction error: {str(e)}")

        # 2. Извлечение видео
        try:
            # Ищем видео-контейнеры
            video_containers = self.driver.find_elements(
                By.XPATH,
                '//div[@data-testid="videoPlayer"] | '  # Основной видео-плеер
                '//div[contains(@class, "video-container")] | '  # Альтернативный вариант
                '//video'  # Прямые теги видео
            )
            
            for container in video_containers:
                # Пробуем получить ссылку из data-атрибутов
                video_url = (
                    container.get_attribute('src') or 
                    container.get_attribute('data-video-url') or
                    container.get_attribute('poster')  # Превью видео
                )
                
                if video_url and 'http' in video_url:
                    media['videos'].append(video_url.split('?')[0])
                    
        except Exception as e:
            logger.warning(f"Video extraction error: {str(e)}")

        return media

    async def close_driver(self):
        """Закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Driver close error: {str(e)}")
            finally:
                self.driver = None