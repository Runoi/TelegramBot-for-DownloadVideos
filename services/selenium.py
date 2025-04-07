import os
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, 
                                      NoSuchElementException, 
                                      WebDriverException)
from webdriver_manager.chrome import ChromeDriverManager
from typing import Dict, List, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)

class TwitterParser:
    def __init__(self):
        self.driver = None
        self.media_pattern = re.compile(r'https://pbs\.twimg\.com/media/[^\?]+')

    async def _init_driver(self):
        """Инициализация драйвера с ручным управлением"""
        options = webdriver.ChromeOptions()
        
        # Обязательные параметры для работы под root
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Оптимальные настройки
        options.add_argument("--window-size=1280,720")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Указываем явные пути (проверьте актуальность!)
        chrome_bin = "/usr/bin/google-chrome"
        chromedriver_bin = "/usr/local/bin/chromedriver"
        
        # Проверка существования файлов
        if not os.path.exists(chrome_bin):
            raise FileNotFoundError(f"Chrome binary not found at {chrome_bin}")
        if not os.path.exists(chromedriver_bin):
            raise FileNotFoundError(f"ChromeDriver not found at {chromedriver_bin}")
        
        options.binary_location = chrome_bin
        
        try:
            service = Service(
                executable_path=chromedriver_bin,
                service_args=['--verbose'],  # Для отладки
            )
            
            self.driver = webdriver.Chrome(
                service=service,
                options=options,
                service_log_path='/tmp/chromedriver.log'  # Логирование
            )
            
            # Настройки времени ожидания
            self.driver.set_page_load_timeout(30)
            self.driver.set_script_timeout(20)
            
            return True
            
        except Exception as e:
            logger.error(f"Driver init failed: {str(e)}")
            if hasattr(self, 'driver'):
                await self._close_driver()
            raise

    async def _close_driver(self):
        """Корректное закрытие драйвера"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing driver: {str(e)}")
            self.driver = None

    async def _extract_media(self, container) -> dict:
        """Надежное извлечение всех медиафайлов"""
        media = {"images": [], "videos": []}
        
        try:
            # Извлекаем все потенциальные медиа-элементы
            elements = container.find_elements(By.XPATH, """
                .//img[contains(@src, 'http')] |
                .//video/source[contains(@src, 'http')] |
                .//iframe[contains(@src, 'youtube.com') or contains(@src, 'youtu.be')]
            """)
            
            for element in elements:
                try:
                    tag_name = element.tag_name
                    src = element.get_attribute("src")
                    
                    # Обработка изображений
                    if tag_name == "img" and src:
                        clean_url = src.split('?')[0].split('#')[0]
                        if any(ext in clean_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            media["images"].append(clean_url)
                    
                    # Обработка видео
                    elif tag_name == "source" and src:
                        clean_url = src.split('?')[0].split('#')[0]
                        if any(ext in clean_url.lower() for ext in ['.mp4', '.webm', '.mov']):
                            media["videos"].append(clean_url)
                    
                    # Обработка YouTube
                    elif tag_name == "iframe" and "youtube" in src:
                        video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', src)
                        if video_id:
                            media["videos"].append(f"https://youtu.be/{video_id.group(1)}")
                
                except Exception as e:
                    logger.warning(f"Ошибка обработки элемента: {str(e)}")
                    continue
        
        except Exception as e:
            logger.error(f"Ошибка извлечения медиа: {str(e)}")
        
        # Удаляем дубликаты
        media["images"] = list(set(media["images"]))
        media["videos"] = list(set(media["videos"]))
        
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