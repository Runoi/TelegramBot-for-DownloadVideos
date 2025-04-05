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

# class ZenParser:
#     def __init__(self):
#         self.driver = None
#         self.timeout = 30
#         self.retry_count = 3

#     async def _init_driver(self):
#         """Инициализация ChromeDriver с современными настройками"""
#         options = webdriver.ChromeOptions()
#         options.add_argument("--headless=false")
#         options.add_argument("--disable-gpu")
#         options.add_argument("--no-sandbox")
#         options.add_argument("--disable-dev-shm-usage")
#         options.add_argument("--window-size=1280,720")
#         options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
#         # Настройки для обхода блокировок
#         options.add_argument("--disable-blink-features=AutomationControlled")
#         options.add_experimental_option("excludeSwitches", ["enable-automation"])
#         options.add_experimental_option("useAutomationExtension", False)

#         try:
#             service = Service(ChromeDriverManager().install())
#             self.driver = webdriver.Chrome(service=service, options=options)
#             self.driver.set_page_load_timeout(self.timeout)
            
#             # Маскируем WebDriver
#             self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
#                 "source": """
#                     Object.defineProperty(navigator, 'webdriver', {
#                         get: () => undefined
#                     })
#                 """
#             })
#             return True
#         except Exception as e:
#             logger.error(f"Ошибка инициализации драйвера: {str(e)}")
#             return False

#     async def _scroll_page(self):
#         """Плавная прокрутка с паузами"""
#         for _ in range(3):
#             self.driver.execute_script("""
#                 window.scrollBy({
#                     top: window.innerHeight * 0.7,
#                     behavior: 'smooth'
#                 });
#             """)
#             await asyncio.sleep(1.5)

#     async def _extract_content(self):
#         """Извлечение контента с исключением комментариев и рекламы"""
#         content = {
#             "title": "",
#             "text": "",
#             "media": {"images": [], "videos": []},
#             "type": "article"
#         }

#         try:
#             # Ожидаем загрузки основного контейнера
#             article = WebDriverWait(self.driver, 15).until(
#                 EC.presence_of_element_located((By.XPATH, """
#                     //article[.//p] |
#                     //div[contains(@class, 'article-content')] |
#                     //div[contains(@class, 'article-root')]
#                 """))
#             )

#             # Удаляем нежелательные блоки через JavaScript
#             self.driver.execute_script("""
#                 const unwantedSelectors = [
#                     'div[class*="comment"]',
#                     'div[class*="discuss"]',
#                     'div[class*="footer"]',
#                     'div[class*="ad"]', 
#                     'div[class*="banner"]',
#                     'div[class*="recommend"]',
#                     'div[class*="promo"]',
#                     'div[class*="sponsor"]',
#                     'div[data-testid*="ad"]',
#                     'aside',
#                     'footer',
#                     'div[class*="teaser"]',
#                     'div[class*="social"]',
#                     'div[class*="subscribe"]'
#                 ];
#                 unwantedSelectors.forEach(selector => {
#                     document.querySelectorAll(selector).forEach(el => el.remove());
#                 });
#             """)

#             # Извлечение заголовка
#             try:
#                 title = article.find_element(By.XPATH, """
#                     .//h1[not(ancestor::div[contains(@class, 'comment')])]
#                 """)
#                 content["title"] = title.text.strip()
#             except:
#                 pass

#             # Извлечение текста с явным исключением комментариев
#             paragraphs = article.find_elements(By.XPATH, """
#                 .//*[not(ancestor::div[contains(@class, 'comment')])
#                 [not(ancestor::div[contains(@class, 'discuss')])
#                 [not(ancestor::footer)]
#                 [self::p or self::div[contains(@class, 'paragraph')]]
#                 [string-length(text()) > 50]
#             """)
            
#             # Дополнительная фильтрация
#             content["text"] = '\n\n'.join({
#                 p.text.strip() for p in paragraphs
#                 if not any(word in p.text.lower() for word in 
#                         ['комментар', 'ответить', 'reply', 'comment'])
#                 and len(p.text.strip()) > 30
#             })

#             # Извлечение медиа с фильтрацией
#             media_elements = article.find_elements(By.XPATH, """
#                 .//*[not(ancestor::div[contains(@class, 'comment')])]
#                 [not(ancestor::div[contains(@class, 'discuss')])]
#                 [self::img or self::video/source]
#                 [not(contains(@src, 'ad'))]
#                 [not(contains(@alt, 'реклама'))]
#             """)
            
#             for media in media_elements:
#                 src = media.get_attribute('src') or media.get_attribute('data-src')
#                 if src and 'http' in src:
#                     if media.tag_name == 'img':
#                         content["media"]["images"].append(src.split('?')[0])
#                     else:
#                         content["media"]["videos"].append(src.split('?')[0])

#             # Удаление дубликатов
#             content["media"]["images"] = list(set(content["media"]["images"]))
#             content["media"]["videos"] = list(set(content["media"]["videos"]))

#         except Exception as e:
#             logger.error(f"Ошибка извлечения: {str(e)}")
#             return await self._alternative_extraction()

#         return content
    
#     def _is_visible(element):
#         """Проверяет, виден ли элемент на экране"""
#         try:
#             return element.is_displayed() and element.size['width'] > 0 and element.size['height'] > 0
#         except:
#             return False

#     async def get_zen_content(self, url: str) -> Tuple[Optional[Dict], Optional[str]]:
#         """Основной метод с улучшенной обработкой"""
#         try:
#             if not await self._init_driver():
#                 return None, "Не удалось инициализировать браузер"

#             logger.info(f"Загрузка страницы: {url}")
#             self.driver.get(url)
            
#             # Проверка на капчу/блокировку
#             if "Доступ ограничен" in self.driver.page_source:
#                 return None, "Обнаружена блокировка доступа"

#             # Ожидание загрузки контента
#             await asyncio.sleep(3)  # Базовое ожидание
            
#             # Прокрутка для подгрузки
#             for _ in range(2):
#                 self.driver.execute_script("window.scrollBy(0, window.innerHeight)")
#                 await asyncio.sleep(2)

#             content = await self._extract_content()
            
#             # Валидация контента
#             if not content["text"] and not content["media"]["images"]:
#                 logger.warning("Основной метод не дал результатов, пробуем альтернативный")
#                 content = await self._alternative_extraction()

#             return content, None

#         except Exception as e:
#             logger.error(f"Ошибка при парсинге: {str(e)}")
#             return None, f"Ошибка парсинга: {str(e)}"
#         finally:
#             await self._close_driver()

#     async def _prepare_page(self):
#         """Подготовка страницы перед парсингом"""
#         # Прокрутка вниз
#         self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
#         await asyncio.sleep(1.5)
        
#         # Прокрутка вверх к основному контенту
#         self.driver.execute_script("window.scrollTo(0, 0)")
#         await asyncio.sleep(1)
        
#         # Удаление плавающих элементов
#         self.driver.execute_script("""
#             document.querySelectorAll('div[class*="fixed"]').forEach(el => el.remove());
#         """)

#     async def _alternative_extraction(self):
#         """Альтернативный метод с усиленной фильтрацией комментариев"""
#         content = {
#             "title": "",
#             "text": "",
#             "media": {"images": [], "videos": []},
#             "type": "article"
#         }

#         try:
#             # Получаем весь видимый текст с фильтрацией
#             body = self.driver.find_element(By.TAG_NAME, 'body')
#             all_text = body.text.split('\n')
            
#             # Фильтрация комментариев и рекламы
#             content["text"] = '\n'.join(
#                 line for line in all_text
#                 if len(line.strip()) > 40
#                 and not any(word in line.lower() for word in 
#                         ['комментар', 'ответить', 'reply', 'comment',
#                             'реклама', 'партнер', 'спонсор'])
#             )

#             # Фильтрация изображений
#             images = self.driver.find_elements(By.TAG_NAME, 'img')
#             content["media"]["images"] = [
#                 img.get_attribute('src').split('?')[0]
#                 for img in images
#                 if img.get_attribute('src')
#                 and 'http' in img.get_attribute('src')
#                 and not any(word in (img.get_attribute('alt') or '').lower() 
#                     for word in ['реклама', 'comment', 'аватар'])
#             ]

#         except Exception as e:
#             logger.error(f"Ошибка альтернативного извлечения: {str(e)}")

#         return content

#     async def _close_driver(self):
#         """Корректное закрытие драйвера"""
#         if self.driver:
#             try:
#                 self.driver.quit()
#             except Exception as e:
#                 logger.error(f"Ошибка закрытия драйвера: {str(e)}")
#             self.driver = None

# zen_parser = ZenParser()

twitter_parser = TwitterParser()

async def get_twitter_content(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    return await twitter_parser.get_twitter_content(url)

__all__ = ['get_twitter_content']