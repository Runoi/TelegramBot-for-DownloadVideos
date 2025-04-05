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
    'vk.com/video',
    'vk.com/clip',
    'vk.com/wall',
    'vkvideo.ru/video',
    '/video-',
    '/clip-',
    '/wall'
]

INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')
INSTAGRAM_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
INSTAGRAM_REQUEST_DELAY = 10  # Задержка между запросами
MAX_RETRIES = 2  # Максимальное количество попыток
os.makedirs(DOWNLOAD_DIR, exist_ok=True)