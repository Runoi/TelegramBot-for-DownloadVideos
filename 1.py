import os
import re
import asyncio
import logging
from datetime import datetime
from functools import lru_cache
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
import yt_dlp
import aiohttp
from bs4 import BeautifulSoup

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("video_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv('token.env')

# Конфигурация 
BOT_TOKEN = os.getenv('BOT_TOKEN')
VK_ACCESS_TOKEN = os.getenv('VK_ACCESS_TOKEN')
VK_API_VERSION = '5.199'
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
SELENIUM_REMOTE_URL = os.getenv('SELENIUM_REMOTE_URL')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Поддерживаемые платформы
PLATFORMS = {
    "youtube": r"(youtube\.com|youtu\.be)",
    "instagram": r"instagram\.com",
    "tiktok": r"tiktok\.com|vm\.tiktok\.com",
    "twitter": r"(x\.com|twitter\.com)",
    "vk": r"vk\.com",
    "reddit": r"(reddit\.com|packaged-media\.redd\.it)",
}

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@lru_cache(maxsize=100)
def normalize_twitter_url(url: str) -> str:
    """Нормализация URL изображений Twitter"""
    if not url or 'pbs.twimg.com' not in url:
        return url
    
    base = url.split('?')[0]
    return f"{base}?name=orig"

def get_selenium_driver():
    """Инициализация драйвера Selenium с автоматической загрузкой ChromeDriver"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
    
    if SELENIUM_REMOTE_URL:
        return webdriver.Remote(
            command_executor=SELENIUM_REMOTE_URL,
            options=options
        )
    else:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(10)
        return driver

def clean_downloads():
    """Очистка директории загрузок"""
    for file in os.listdir(DOWNLOAD_DIR):
        file_path = os.path.join(DOWNLOAD_DIR, file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {file_path}: {e}")

async def download_twitter_image(url: str, filename: str) -> str:
    """Специальная функция для загрузки изображений с Twitter"""
    try:
        base_url = url.split('?')[0]
        qualities = ['orig', 'large', 'medium', 'small']
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://twitter.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            for quality in qualities:
                try:
                    img_url = f"{base_url}?format=jpg&name={quality}"
                    async with session.get(img_url, timeout=10) as response:
                        if response.status == 200:
                            filepath = os.path.join(DOWNLOAD_DIR, filename)
                            with open(filepath, 'wb') as f:
                                async for chunk in response.content.iter_chunked(1024):
                                    f.write(chunk)
                            return filepath
                except:
                    continue
            
            raise ValueError("Не удалось загрузить изображение ни в одном качестве")
    except Exception as e:
        logger.error(f"Ошибка загрузки Twitter изображения {url}: {str(e)}")
        raise

async def download_image(url: str, filename: str) -> str:
    """Универсальная загрузка изображений"""
    if 'pbs.twimg.com' in url:
        return await download_twitter_image(url, filename)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    with open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(1024):
                            f.write(chunk)
                    return filepath
                raise ValueError(f"HTTP ошибка: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения {url}: {str(e)}")
        raise

async def get_vk_post(url: str) -> dict:
    """Получение данных поста ВКонтакте через API"""
    try:
        match = re.search(r'wall(-?\d+)_(\d+)', url)
        if not match:
            raise ValueError("Некорректный URL поста VK")
        
        owner_id, post_id = match.groups()
        
        params = {
            'access_token': VK_ACCESS_TOKEN,
            'v': VK_API_VERSION,
            'posts': f"{owner_id}_{post_id}",
            'extended': 1,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.vk.com/method/wall.getById', params=params) as response:
                data = await response.json()
                
                if 'error' in data:
                    raise ValueError(f"VK API error: {data['error']['error_msg']}")
                
                post = data['response']['items'][0]
                post_text = post.get('text', '')
                
                attachments = post.get('attachments', [])
                images = []
                
                for attachment in attachments:
                    if attachment['type'] == 'photo':
                        photo = attachment['photo']
                        sizes = photo.get('sizes', [])
                        if sizes:
                            max_size = max(sizes, key=lambda x: x.get('width', 0))
                            images.append(max_size['url'])
                    elif attachment['type'] == 'video':
                        video = attachment['video']
                        if 'image' in video:
                            images.extend([
                                img['url'] for img in video['image'] 
                                if isinstance(img, dict) and 'url' in img
                            ])
                
                return {
                    'text': post_text,
                    'images': images[:10]
                }
    except Exception as e:
        logger.error(f"Ошибка VK API: {str(e)}")
        raise

async def try_nitter(url: str) -> dict:
    """Попытка получить данные через Nitter"""
    try:
        nitter_url = url.replace('twitter.com', 'nitter.net').replace('x.com', 'nitter.net')
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(nitter_url, headers=headers, timeout=10) as response:
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')

                tweet_text = ""
                content_div = soup.find('div', class_='tweet-content')
                if content_div:
                    tweet_text = content_div.get_text('\n').strip()

                images = []
                videos = []
                gallery = soup.find('div', class_='attachments')
                if gallery:
                    for img in gallery.find_all('img'):
                        if img.get('src'):
                            img_url = img['src']
                            if img_url.startswith('/pic/'):
                                img_url = f'https://nitter.net{img_url}'
                            images.append(img_url)
                    
                    for video in gallery.find_all('video'):
                        if video.get('src'):
                            videos.append(video['src'])
                        for source in video.find_all('source'):
                            if source.get('src'):
                                videos.append(source['src'])

                return {
                    'success': bool(tweet_text or images or videos),
                    'data': {
                        'text': tweet_text,
                        'images': images[:4],
                        'videos': videos[:2]
                    }
                }
    except Exception as e:
        logger.warning(f"Nitter не сработал: {str(e)}")
        return {'success': False}

async def get_twitter_video_url(driver, url: str) -> str:
    """Получаем прямую ссылку на видео через Selenium"""
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//video'))
        )
        
        # Получаем все видео элементы
        videos = driver.find_elements(By.XPATH, '//video')
        for video in videos:
            try:
                # Пробуем получить src или source
                video_url = video.get_attribute('src')
                if video_url and not video_url.startswith('blob:'):
                    return video_url
                
                # Ищем source внутри video
                sources = video.find_elements(By.XPATH, './/source')
                for source in sources:
                    source_url = source.get_attribute('src')
                    if source_url and not source_url.startswith('blob:'):
                        return source_url
            except:
                continue
        
        # Альтернативный метод - извлекаем из data-атрибутов
        for video in videos:
            try:
                video_url = video.get_attribute('data-video-url')
                if video_url:
                    return video_url
            except:
                continue
        
        return None
    except Exception as e:
        logger.error(f"Ошибка получения видео URL: {str(e)}")
        return None

async def download_twitter_video(url: str) -> str:
    """Скачивание видео с Twitter с использованием yt-dlp и обходных методов"""
    clean_downloads()
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': False,
        'no_warnings': False,
        'retries': 3,
        'logger': logger,
        'extract_flat': True,
    }
    
    try:
        # Пробуем скачать через yt-dlp с обходными методами
        logger.info(f"Попытка скачать через yt-dlp: {url}")
        
        # Добавляем обходные параметры для Twitter
        ydl_opts['extractor_args'] = {
            'twitter': {
                'username': os.getenv('TWITTER_USERNAME'),
                'password': os.getenv('TWITTER_PASSWORD')
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if os.path.exists(filename):
                return filename
            
            # Если не получилось, пробуем альтернативный метод
            files = [f for f in os.listdir(DOWNLOAD_DIR) 
                    if f.endswith('.mp4') and os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
            if files:
                return os.path.join(DOWNLOAD_DIR, files[0])
            
            raise Exception("Не удалось найти скачанный файл")
            
    except Exception as e:
        logger.error(f"Ошибка скачивания видео: {str(e)}")
        raise ValueError(f"Не удалось скачать видео: {str(e)}")

async def extract_media_urls(driver) -> dict:
    """Извлечение URL всех медиа (изображения, видео, гифки)"""
    media_urls = []
    video_urls = []
    
    # 1. Изображения
    try:
        img_elements = driver.find_elements(By.XPATH,
            '//div[@data-testid="tweetPhoto"]//img | '
            '//div[contains(@class, "media-image")]//img')
        
        for img in img_elements:
            try:
                src = img.get_attribute('src') or img.get_attribute('srcset')
                if src and not src.startswith('blob:'):
                    if ',' in src:
                        src = src.split(',')[-1].strip().split()[0]
                    base_url = src.split('?')[0]
                    media_urls.append(f"{base_url}?name=orig")
            except Exception as e:
                logger.warning(f"Ошибка обработки изображения: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка поиска изображений: {str(e)}")

    # 2. Видео и GIF - ищем ссылки на твит с видео
    try:
        video_links = driver.find_elements(By.XPATH,
            '//a[contains(@href, "/status/") and contains(@href, "/video/")]')
        
        for link in video_links:
            try:
                href = link.get_attribute('href')
                if href and 'twitter.com' in href:
                    video_urls.append(href)
            except Exception as e:
                logger.warning(f"Ошибка обработки видео-ссылки: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка поиска видео-ссылок: {str(e)}")

    # 3. Мета-теги (OpenGraph)
    try:
        meta_images = driver.find_elements(By.XPATH,
            '//meta[@property="og:image"] | '
            '//meta[@name="twitter:image"]')
        
        for meta in meta_images:
            try:
                img_url = meta.get_attribute('content')
                if img_url and img_url not in media_urls and not img_url.startswith('blob:'):
                    media_urls.append(img_url)
            except Exception as e:
                logger.warning(f"Ошибка обработки meta-тега: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка поиска meta-тегов: {str(e)}")

    return {
        'images': media_urls,
        'videos': list(set(video_urls))  # Удаляем дубликаты
    }

async def try_selenium_parsing(url: str) -> dict:
    """Улучшенный парсинг Twitter/X с обработкой твитов без текста"""
    driver = None
    try:
        driver = get_selenium_driver()
        driver.get(url)
        
        # Увеличиваем время ожидания
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, 'article')))
        
        # Прокрутка для загрузки медиа
        driver.execute_script("window.scrollBy(0, 500);")
        await asyncio.sleep(2)

        tweet_text = ""
        try:
            # Пробуем несколько вариантов поиска текста
            text_elements = driver.find_elements(By.XPATH, 
                '//div[@data-testid="tweetText"] | '
                '//div[contains(@class, "tweet-text")] | '
                '//div[@lang]')
            
            for elem in text_elements:
                if elem.text.strip():
                    tweet_text = elem.text
                    break
        except Exception as e:
            logger.warning(f"Текст не найден: {str(e)}")

        # Поиск всех типов медиа
        media_data = await extract_media_urls(driver)
        
        return {
            'success': bool(tweet_text or media_data['images'] or media_data['videos']),
            'data': {
                'text': tweet_text,
                'images': media_data['images'][:10],  # Ограничиваем количество
                'videos': media_data['videos'][:3]    # Ограничиваем количество видео
            }
        }
    except Exception as e:
        logger.error(f"Selenium парсинг не сработал: {str(e)}")
        return {'success': False}
    finally:
        if driver:
            driver.quit()

async def get_twitter_post(url: str) -> dict:
    """Улучшенный метод получения постов Twitter/X"""
    try:
        nitter_data = await try_nitter(url)
        if nitter_data['success']:
            return nitter_data['data']

        selenium_data = await try_selenium_parsing(url)
        if selenium_data['success']:
            return selenium_data['data']

        raise ValueError("Все методы получения данных не сработали")
    except Exception as e:
        logger.error(f"Ошибка Twitter/X: {str(e)}")
        raise ValueError("Не удалось получить содержимое поста. Twitter/X ограничивает доступ.")

def get_ydl_opts(url: str) -> dict:
    """Возвращает параметры скачивания для разных платформ"""
    base_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': False,
        'no_warnings': False,
        'retries': 3,
        'logger': logger,
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }]
    }

    if re.search(PLATFORMS["twitter"], url, re.IGNORECASE):
        return {
            **base_opts,
            'format': 'bv*[ext=mp4][vcodec!=av01]+ba[ext=m4a]/b[ext=mp4]/b',
        }
    
    if re.search(PLATFORMS["instagram"], url, re.IGNORECASE):
        return {
            **base_opts,
            'format': 'bv*[vcodec!=av01]+ba/b[vcodec!=av01]',
            'socket_timeout': 30,
            'force_ipv4': True,
        }

    return {
        **base_opts,
        'format': 'bv*[height<=720][ext=mp4][vcodec!=av01]+ba/b[height<=720][vcodec!=av01]',
    }

async def compress_video(input_path: str, output_path: str, crf: int = 28) -> bool:
    """Асинхронное сжатие видео через FFmpeg"""
    try:
        logger.info(f"Сжатие видео: {input_path} -> {output_path}")
        
        process = await asyncio.create_subprocess_exec(
            'ffmpeg',
            '-i', input_path,
            '-vf', 'scale=1280:720',
            '-vcodec', 'libx264',
            '-crf', str(crf),
            '-c:a', 'aac',
            '-b:a', '128k',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y',
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Ошибка FFmpeg: {stderr.decode()}")
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка сжатия: {str(e)}")
        return False

async def download_video(url: str) -> str:
    """Скачивание видео с обработкой ошибок"""
    clean_downloads()
    ydl_opts = get_ydl_opts(url)
    
    try:
        logger.info(f"Начало загрузки: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
                if files:
                    filename = os.path.join(DOWNLOAD_DIR, files[0])
                    logger.warning(f"Используем первый найденный файл: {filename}")
                else:
                    raise FileNotFoundError("Не удалось найти скачанный файл")
            
            logger.info(f"Успешно скачано: {filename}")
            return filename
            
    except yt_dlp.DownloadError as e:
        if "Requested format is not available" in str(e):
            logger.warning("Запрошенный формат недоступен, пробую любой доступный")
            ydl_opts['format'] = 'best'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if not os.path.exists(filename):
                    files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
                    if files:
                        filename = os.path.join(DOWNLOAD_DIR, files[0])
                
                return filename
        raise

@dp.message(Command("start"))
async def start(message: Message):
    logger.info(f"Новый пользователь: {message.from_user.id}")
    await message.answer(
        "🔻 Отправьте ссылку на видео с:\n"
        "YouTube, Instagram, TikTok, Twitter/X\n"
        "VK, Reddit\n\n"
        "Или отправьте ссылку на пост с:\n"
        "VK или Twitter/X (текст + картинки)\n\n"
        "Я скачаю и отправлю вам контент!"
    )

async def send_media_group(message: Message, images: list, videos: list):
    """Отправка медиагруппы с разделением изображений и видео"""
    try:
        media_group = []
        
        # Добавляем изображения
        for i, img_url in enumerate(images[:10]):
            try:
                filename = f"image_{i}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                img_path = await download_image(img_url, filename)
                
                with open(img_path, 'rb') as img_file:
                    media_group.append(
                        types.InputMediaPhoto(
                            media=types.BufferedInputFile(
                                img_file.read(),
                                filename=filename
                            )
                        )
                    )
                os.remove(img_path)
            except Exception as e:
                logger.error(f"Ошибка обработки изображения {img_url}: {str(e)}")
                continue
        
        # Добавляем видео превью (как изображения)
        for i, video_url in enumerate(videos[:10 - len(media_group)]):
            try:
                filename = f"video_preview_{i}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                img_path = await download_image(video_url, filename)
                
                with open(img_path, 'rb') as img_file:
                    media_group.append(
                        types.InputMediaPhoto(
                            media=types.BufferedInputFile(
                                img_file.read(),
                                filename=filename
                            )
                        )
                    )
                os.remove(img_path)
            except Exception as e:
                logger.error(f"Ошибка обработки видео превью {video_url}: {str(e)}")
                continue
        
        if media_group:
            await bot.send_media_group(
                chat_id=message.chat.id,
                media=media_group
            )
    except Exception as e:
        logger.error(f"Ошибка отправки медиагруппы: {str(e)}")
        raise

async def handle_post_with_images(message: Message, post_data: dict):
    """Обработка поста с медиа"""
    try:
        # Отправляем текст если есть
        if post_data.get('text'):
            await message.answer(f"📝 Текст поста:\n\n{post_data['text']}")
        
        # Отправляем медиа
        if post_data.get('images'):
            await send_media_group(message, post_data['images'], [])
        else:
            await message.answer("ℹ️ В посте нет доступных медиафайлов.")
            
    except Exception as e:
        logger.error(f"Ошибка обработки поста: {str(e)}")
        await message.answer(f"❌ Ошибка при обработке поста: {str(e)}")

async def determine_twitter_post_type(driver, url: str) -> str:
    """Точное определение типа Twitter поста (video/photo/text)"""
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//article')))
        
        # 1. Проверяем наличие видео-контента
        video_containers = driver.find_elements(By.XPATH,
            '//div[@data-testid="videoPlayer"] | '
            '//div[contains(@class, "video-container")]')
        
        if video_containers:
            return "video"
        
        # 2. Проверяем наличие нескольких изображений
        image_galleries = driver.find_elements(By.XPATH,
            '//div[@data-testid="tweetPhoto"] | '
            '//div[contains(@class, "media-image")]')
        
        if image_galleries:
            return "photo"
        
        # 3. Проверяем одиночные медиа-вложения
        media_tags = driver.find_elements(By.XPATH,
            '//img[contains(@src, "twimg.com/media/")] | '
            '//video[contains(@src, "twimg.com/media/")]')
        
        if media_tags:
            for tag in media_tags:
                if tag.tag_name == 'video':
                    return "video"
            return "photo"
        
        return "text"
    
    except Exception as e:
        logger.error(f"Ошибка определения типа поста: {str(e)}")
        return "unknown"

async def handle_twitter_video_post(message: Message, url: str):
    """Специальная обработка видео-постов"""
    try:
        await message.answer("⏳ Пытаюсь скачать видео...")
        
        # Пробуем скачать через yt-dlp
        try:
            filename = await download_twitter_video(url)
            
            # Проверяем размер файла
            file_size = os.path.getsize(filename)
            if file_size > MAX_FILE_SIZE:
                compressed_path = f"{filename}_compressed.mp4"
                await message.answer("⚠️ Видео слишком большое, сжимаю...")
                
                if await compress_video(filename, compressed_path):
                    compressed_size = os.path.getsize(compressed_path)
                    if compressed_size <= MAX_FILE_SIZE:
                        os.remove(filename)
                        filename = compressed_path
                    else:
                        os.remove(compressed_path)
                        raise ValueError("Не удалось сжать видео")
            
            # Отправляем видео
            with open(filename, "rb") as video_file:
                await message.answer_video(
                    video=types.BufferedInputFile(
                        video_file.read(),
                        filename="twitter_video.mp4"
                    ),
                    caption="🎥 Видео из Twitter/X"
                )
            os.remove(filename)
            return True
            
        except Exception as e:
            logger.warning(f"Не удалось скачать видео (попытка 1): {str(e)}")
            await message.answer("⚠️ Первый метод не сработал, пробую альтернативный...")
        
        # Альтернативный метод через Selenium
        driver = get_selenium_driver()
        try:
            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//video')))
            
            # Получаем ссылку на видео
            video_element = driver.find_element(By.XPATH, '//video')
            video_url = video_element.get_attribute('src')
            
            if not video_url:
                # Пробуем получить из source
                source_element = video_element.find_element(By.XPATH, './/source')
                video_url = source_element.get_attribute('src')
            
            if video_url and video_url.startswith('http'):
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://twitter.com/'
                }
                
                filename = os.path.join(DOWNLOAD_DIR, f"twitter_video_{datetime.now().timestamp()}.mp4")
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(video_url) as response:
                        if response.status == 200:
                            with open(filename, 'wb') as f:
                                async for chunk in response.content.iter_chunked(1024):
                                    f.write(chunk)
                            
                            # Отправляем видео
                            with open(filename, "rb") as video_file:
                                await message.answer_video(
                                    video=types.BufferedInputFile(
                                        video_file.read(),
                                        filename="twitter_video.mp4"
                                    ),
                                    caption="🎥 Видео из Twitter/X"
                                )
                            os.remove(filename)
                            return True
            return False
            
        except Exception as e:
            logger.error(f"Не удалось скачать видео (попытка 2): {str(e)}")
            return False
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Критическая ошибка обработки видео: {str(e)}")
        return False

async def handle_twitter_post(message: Message, url: str):
    """Финальная обработка Twitter постов"""
    try:
        # Сначала определяем тип поста
        driver = get_selenium_driver()
        try:
            post_type = await determine_twitter_post_type(driver, url)
            await message.answer(f"⏳ Обнаружен {post_type} пост, обрабатываю...")

            # Для видео-постов
            if post_type == "video":
                success = await handle_twitter_video_post(message, url)
                if success:
                    return
                else:
                    await message.answer("⚠️ Не удалось скачать видео, показываю превью...")

            # Общая обработка для всех типов постов
            # Получаем текст поста
            tweet_text = ""
            try:
                text_elements = driver.find_elements(By.XPATH, 
                    '//div[@data-testid="tweetText"] | '
                    '//div[contains(@class, "tweet-text")] | '
                    '//div[@lang]')
                
                for elem in text_elements:
                    if elem.text.strip():
                        tweet_text = elem.text
                        break
            except:
                logger.warning("Не удалось извлечь текст твита")

            # Получаем медиа
            media_urls = []
            try:
                media_elements = driver.find_elements(By.XPATH,
                    '//div[@data-testid="tweetPhoto"]//img | '
                    '//div[contains(@class, "media-image")]//img | '
                    '//video[@poster]')
                
                for elem in media_elements:
                    if elem.tag_name == 'img':
                        src = elem.get_attribute('src') or elem.get_attribute('srcset')
                        if src and not src.startswith('blob:'):
                            if ',' in src:
                                src = src.split(',')[-1].strip().split()[0]
                            media_urls.append(src.split('?')[0])
                    elif elem.tag_name == 'video':
                        poster = elem.get_attribute('poster')
                        if poster:
                            media_urls.append(poster)
            except:
                logger.warning("Не удалось извлечь медиа")

            # Отправляем результат
            if tweet_text:
                await message.answer(f"📝 Текст поста:\n\n{tweet_text}")
            
            if media_urls:
                await message.answer(f"🖼️ Медиа из поста ({len(media_urls)}):")
                await send_media_group(message, media_urls[:10], [])
            elif not tweet_text:
                await message.answer("ℹ️ В посте не найдено текста или медиа")
                
        except Exception as e:
            logger.error(f"Ошибка обработки поста: {str(e)}")
            await message.answer("❌ Не удалось обработать пост. Twitter/X ограничивает доступ.")
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Критическая ошибка обработки Twitter: {str(e)}")
        await message.answer(f"❌ Произошла ошибка: {str(e)}")

@dp.message(F.text)
async def handle_links(message: Message):
    url = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"Запрос от {user_id}: {url}")
    
    if url.startswith('/'):
        return
    
    # Обработка Twitter/X
    twitter_patterns = ['/status/', 'x.com/', 'twitter.com/']
    if re.search(PLATFORMS["twitter"], url, re.IGNORECASE) and any(p in url for p in twitter_patterns):
        await handle_twitter_post(message, url)
        return
    
    # Обработка поста VK
    vk_patterns = ['/wall', 'vk.com/wall', 'w=wall']
    if re.search(PLATFORMS["vk"], url, re.IGNORECASE) and any(p in url for p in vk_patterns):
        try:
            await message.answer("⏳ Получаю пост из VK...")
            post_data = await get_vk_post(url)
            await handle_post_with_images(message, post_data)
            return
        except Exception as e:
            logger.error(f"Ошибка VK: {str(e)}")
            await message.answer(f"❌ Ошибка при получении поста VK: {str(e)}")
            return
    
    # Обработка видео с других платформ
    if not any(re.search(pattern, url, re.IGNORECASE) for pattern in PLATFORMS.values()):
        logger.warning(f"Неподдерживаемая платформа: {url}")
        await message.answer("❌ Эта платформа не поддерживается.")
        return

    try:
        await message.answer("⏳ Скачиваю видео...")
        filename = await download_video(url)
        
        file_size = os.path.getsize(filename)
        logger.info(f"Размер файла: {file_size//1024//1024}MB")
        
        if file_size > MAX_FILE_SIZE:
            compressed_path = f"{filename}_compressed.mp4"
            await message.answer("⚠️ Сжимаю видео...")
            
            if await compress_video(filename, compressed_path):
                compressed_size = os.path.getsize(compressed_path)
                logger.info(f"Размер после сжатия: {compressed_size//1024//1024}MB")
                
                if compressed_size > MAX_FILE_SIZE:
                    logger.warning("Файл слишком большой после сжатия")
                    await message.answer("❌ Не удалось сжать видео до допустимого размера.")
                    os.remove(filename)
                    if os.path.exists(compressed_path):
                        os.remove(compressed_path)
                    return
                
                filename = compressed_path

        with open(filename, "rb") as video_file:
            logger.info("Отправка видео пользователю")
            await message.answer_video(
                video=types.BufferedInputFile(
                    video_file.read(),
                    filename=os.path.basename(filename)
                ),
                caption=f"🎥 {os.path.basename(filename)[:100]}"
            )

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)
        if 'compressed_path' in locals() and os.path.exists(compressed_path):
            os.remove(compressed_path)

async def main():
    logger.info("Запуск бота")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)