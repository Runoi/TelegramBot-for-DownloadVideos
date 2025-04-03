from asyncio import subprocess
import os
import asyncio
from datetime import datetime
from functools import lru_cache
import re
from typing import Optional, List
import aiohttp
import logging
import ffmpeg
from config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def clean_downloads():
    """Очищает директорию загрузок с обработкой ошибок"""
    for filename in os.listdir(DOWNLOAD_DIR):
        try:
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"Ошибка удаления файла {filename}: {str(e)}")

@lru_cache(maxsize=100)
def normalize_twitter_url(url: str) -> Optional[str]:
    """Нормализует URL изображений Twitter для максимального качества"""
    if not url or 'pbs.twimg.com' not in url:
        return url
    
    base = url.split('?')[0]
    return f"{base}?name=orig"

async def get_video_duration(filepath: str) -> float:
    """Асинхронно получает длительность видео в секундах"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        filepath
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await proc.communicate()
    
    if proc.returncode != 0:
        raise ValueError("Не удалось определить длительность видео")
    
    try:
        return float(stdout.decode().strip())
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Некорректная длительность видео: {str(e)}")

async def compress_video(input_path: str, output_path: str, target_size_mb: int = 45) -> bool:
    """Улучшенное сжатие с контролем качества"""
    try:
        # Рассчитываем битрейт (в кбит/с)
        duration = await get_video_duration(input_path)
        target_bitrate = int((target_size_mb * 8192) / duration)  # 8*1024
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-maxrate', f'{target_bitrate}k',
            '-bufsize', f'{target_bitrate * 2}k',
            '-vf', 'scale=-2:720',  # 720p
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y',
            output_path
        ]
        # Запуск процесса
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Ждем завершения
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            return False

        return os.path.exists(output_path)

    except Exception as e:
        logger.error(f"Compression failed: {str(e)}", exc_info=True)
        return False

async def download_image(url: str, filename: str) -> str:
    """Универсальная загрузка изображений с обработкой ошибок"""
    path = os.path.join(DOWNLOAD_DIR, filename)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
    }
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    with open(path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(1024):
                            f.write(chunk)
                    return path
                raise ValueError(f"HTTP Status: {response.status}")
    except Exception as e:
        logger.error(f"Image download failed: {str(e)}")
        raise

async def download_twitter_image(url: str, filename: str) -> str:
    """Улучшенная загрузка Twitter изображений с обходом ограничений"""
    path = os.path.join(DOWNLOAD_DIR, filename)
    
    # Пробуем разные варианты URL
    variants = [
        url.replace("pbs.twimg.com/media", "pbs.twimg.com/media"),
        url.replace("https://", "http://"),
        url + "?format=jpg&name=orig",
        url.split('?')[0] + "?format=png&name=orig",
        url.replace("_normal", ""),
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://twitter.com/',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        for attempt, img_url in enumerate(variants, 1):
            try:
                async with session.get(img_url, timeout=10) as response:
                    if response.status == 200:
                        with open(path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024):
                                f.write(chunk)
                        return path
                    logger.warning(f"Attempt {attempt}: Status {response.status} for {img_url}")
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed: {str(e)}")
                continue
                
        raise ValueError(f"Не удалось загрузить изображение после {len(variants)} попыток")
