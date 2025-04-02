import os
import re
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
import yt_dlp

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
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Поддерживаемые платформы
PLATFORMS = {
    "youtube": r"(youtube\.com|youtu\.be)",
    "instagram": r"instagram\.com",
    "tiktok": r"tiktok\.com|vm\.tiktok\.com",
    "twitter": r"(x\.com|twitter\.com)",
    "vk": r"vk\.com",
    "reddit": r"(reddit\.com|packaged-media\.redd\.it)",
    #"dzen": r"dzen\.ru",
}

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_ydl_opts(url: str) -> dict:
    """Возвращает параметры скачивания для разных платформ"""
    base_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': False,
        'no_warnings': False,
        'retries': 3,
        'logger': logger,
    }

    if re.search(PLATFORMS["twitter"], url, re.IGNORECASE):
        return {
            **base_opts,
            'format': 'bv*[ext=mp4][vcodec!*=av01]+ba[ext=m4a]/b[ext=mp4]/b',
            'merge_output_format': 'mp4',
        }
    
    if re.search(PLATFORMS["instagram"], url, re.IGNORECASE):
        return {
            **base_opts,
            'format': 'bv*[vcodec!*=av01]+ba/b[vcodec!*=av01]',  # Жёсткий запрет AV1
            'socket_timeout': 30,
            'force_ipv4': True,
        }

    return {
        **base_opts,
        'format': 'bv*[height<=720][ext=mp4][vcodec!*=av01]+ba/b[height<=720][vcodec!*=av01]',
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
    ydl_opts = get_ydl_opts(url)
    
    try:
        logger.info(f"Начало загрузки: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"Успешно скачано: {filename}")
            return filename
            
    except yt_dlp.DownloadError as e:
        if "Requested format is not available" in str(e):
            logger.warning("Запрошенный формат недоступен, пробую любой доступный")
            ydl_opts['format'] = 'best'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
        raise

@dp.message(Command("start"))
async def start(message: Message):
    logger.info(f"Новый пользователь: {message.from_user.id}")
    await message.answer(
        "🔻 Отправьте ссылку на видео с:\n"
        "YouTube, Instagram, TikTok, Twitter/X\n"
        "VK, Reddit или Dzen\n\n"
        "Я скачаю и отправлю вам видео!"
    )

@dp.message(F.text)
async def handle_links(message: Message):
    url = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"Запрос от {user_id}: {url}")
    
    if url.startswith('/'):
        return
    
    if not any(re.search(pattern, url, re.IGNORECASE) for pattern in PLATFORMS.values()):
        logger.warning(f"Неподдерживаемая платформа: {url}")
        await message.answer("❌ Эта платформа не поддерживается.")
        return

    try:
        await message.answer("⏳ Скачиваю видео...")
        filename = await download_video(url)
        
        # Проверка размера
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

        # Отправка видео
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
        # Очистка временных файлов
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