from pathlib import Path
import requests
from selenium.webdriver.common.by import By
import yt_dlp
import os
import time
import re
import logging
from typing import Optional
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, PLATFORMS
from services.utils import compress_video
from yt_dlp import YoutubeDL
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

def get_ydl_opts(url: str) -> dict:
    """Возвращает параметры скачивания для разных платформ"""
    base_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': False,
        'no_warnings': False,
        'retries': 3,
        'merge_output_format': 'mp4',
    }

    # Проверяем URL без использования скомпилированного паттерна
    if re.search(r"(youtube\.com|youtu\.be)", url, re.IGNORECASE):
        return {**base_opts, 'format': 'bv*[height<=720][ext=mp4]+ba/b[height<=720]'}
    
    if re.search(r"instagram\.com", url, re.IGNORECASE):
        return {**base_opts, 'format': 'bv*+ba/b'}
    
    if re.search(r"(x\.com|twitter\.com)", url, re.IGNORECASE):
        return {
            **base_opts,
            'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b',
            'extractor_args': {'twitter': {'username': None, 'password': None}}
        }
    
    # Для всех остальных платформ
    return base_opts

def get_vk_ydl_opts():
    """Оптимальные настройки для VK"""
    return {
        'outtmpl': os.path.join(DOWNLOAD_DIR, 'vk_%(id)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'retries': 3,
        'socket_timeout': 30,
        'extract_flat': False,
        'referer': 'https://vk.com/',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
        },
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'cookiefile': None,  # Явно отключаем сохранение cookies
        'no_cookies': True,   # Запрещаем yt-dlp использовать cookies, если не указан файл
        'merge_output_format': 'mp4',
        'windows_filenames': True,
        'restrictfilenames': True
    }

async def download_video(url: str) -> str:
    """Скачивание видео с обработкой ошибок"""
    try:
        ydl_opts = get_ydl_opts(url)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                # Ищем любой видеофайл в папке загрузок
                files = [f for f in os.listdir('downloads') 
                        if f.endswith(('.mp4', '.mkv', '.webm'))]
                if files:
                    filename = os.path.join('downloads', files[0])
                else:
                    raise FileNotFoundError("Не удалось найти скачанный файл")
            
            return filename
            
    except yt_dlp.DownloadError as e:
        logger.error(f"Ошибка скачивания: {str(e)}")
        raise ValueError(f"Не удалось скачать видео: {str(e)}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}")
        raise

async def download_twitter_video(url: str) -> str:
    """Улучшенное скачивание Twitter видео"""
    ydl_opts = {
        'outtmpl': 'downloads/twitter_%(id)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'retries': 5,
        'socket_timeout': 60,
        'extractor_args': {
            'twitter': {
                'username': os.getenv('TWITTER_USERNAME'),
                'password': os.getenv('TWITTER_PASSWORD')
            }
        },
        'logger': logging.getLogger('yt-dlp'),
    }
    
    try:
        # Сначала пробуем стандартный метод
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                # Если файл не найден, ищем любой видеофайл в папке загрузок
                files = [f for f in os.listdir('downloads') 
                        if f.startswith('twitter_') and f.endswith('.mp4')]
                if files:
                    filename = os.path.join('downloads', files[0])
                else:
                    raise FileNotFoundError("Видеофайл не найден после скачивания")
            
            return filename
            
    except Exception as e:
        logger.error(f"Twitter video download failed: {str(e)}")
        raise ValueError(f"Не удалось скачать видео: {str(e)}")

async def download_vk_video(url: str) -> str:
    """Улучшенная загрузка видео из VK"""
    try:
        # Создаем директорию, если не существует
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        ydl_opts = get_vk_ydl_opts()
        filename = None

        with YoutubeDL(ydl_opts) as ydl:
            # Сначала получаем информацию о видео
            info_dict = ydl.extract_info(url, download=False)
            video_id = info_dict.get('id', 'video')
            ext = info_dict.get('ext', 'mp4')
            filename = os.path.join(DOWNLOAD_DIR, f'vk_{video_id}.{ext}')
            
            # Удаляем старый файл, если существует
            if os.path.exists(filename):
                os.remove(filename)
            
            # Скачиваем видео
            ydl.download([url])
            
            # Проверяем, что файл создан
            if not os.path.exists(filename):
                # Ищем файл по шаблону, если не найден
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(f'vk_{video_id}') and f.endswith(('.mp4', '.mkv', '.webm')):
                        filename = os.path.join(DOWNLOAD_DIR, f)
                        break
                else:
                    raise FileNotFoundError("Файл видео не найден после загрузки")
            
            return filename

    except Exception as e:
        logger.error(f"Ошибка загрузки VK видео: {str(e)}", exc_info=True)
        if filename and os.path.exists(filename):
            os.remove(filename)
        raise ValueError(f"Не удалось скачать видео: {str(e)}")


    
