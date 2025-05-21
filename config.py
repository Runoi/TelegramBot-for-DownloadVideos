import os
import re
from dotenv import load_dotenv
import logging
from typing import Dict, List, Pattern

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

# Основные настройки
BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
VK_ACCESS_TOKEN: str = os.getenv('VK_ACCESS_TOKEN', '')
VK_API_VERSION: str = '5.199'
DOWNLOAD_DIR: str = "downloads"
MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
SELENIUM_REMOTE_URL: str = os.getenv('SELENIUM_REMOTE_URL', '')
TWITTER_USERNAME: str = os.getenv('TWITTER_USERNAME', '')
TWITTER_PASSWORD: str = os.getenv('TWITTER_PASSWORD', '')

# Поддерживаемые платформы
PLATFORMS = {
    "yandex_zen": r"zen\.yandex\.ru|dzen\.ru",
    "youtube": r"(youtube\.com|youtu\.be)",
    "instagram": r"instagram\.com",
    "tiktok": r"tiktok\.com|vm\.tiktok\.com",
    "twitter": r"(x\.com|twitter\.com)",
    "vk": r"(vk\.com|vkvideo\.ru)",  # Объединенные паттерны
    "reddit": r"(reddit\.com|packaged-media\.redd\.it)",
    # "dzen": r"dzen\.ru/video/watch"
}

# Паттерны для определения типа контента
TWITTER_PATTERNS: List[str] = ['/status/', 'x.com/', 'twitter.com/']
VK_PATTERNS = [
    'vkvideo.ru/',
    'vkvideo.ru',
    'vk.com/video',
    'vk.com/clip',
    'vk.com/wall',
    'vkvideo.ru/video',
    '/video-',
    '/clip-',
    '/wall',
    'vkvideo.ru/video-',  # для ссылок вида video-XXXXX_YYYYY
    'vkvideo.ru/clip-'    # для ссылок вида clip-XXXXX_YYYYY
]
FFMPEG_PATH = "ffmpeg"
# Instagram Settings
INSTAGRAM_API_ENDPOINT = "https://apihut.in/api/download/videos"
USE_INSTAGRAM_API = True  # Set to True to use API instead of Instaloader
MAX_MERGED_VIDEO_SIZE = 50  # MB
INSTAGRAM_API_KEY = os.getenv('INSTAGRAM_API_KEY')  # If required by your AP
MAX_TELEGRAM_VIDEO_SIZE = 45  # MB (Telegram limit)
MAX_RETRIES = 2  # Максимальное количество попыток
MAX_PARALLEL_MERGES = 2  # Безопасное значение
MAX_API_REQUESTS_PER_MIN = 30    # Лимит запросов к Instagram API
PHOTO_DURATION = 3  # Длительность фото в объединенном видео (сек)
MAX_BOT_REQUESTS_PER_SEC = 20  # Лимит Telegram API

CHANNEL_ID = "@hassanmaxim"
SUPPORT_LINK = "https://t.me/dropsupport"  # Ссылка на поддержку
NEURAL_NETWORK_POST = "https://t.me/hassanmaxim/84"  # Ссылка на пост про нейросети
CHANNEL_LINK = "https://t.me/hassanmaxim"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)