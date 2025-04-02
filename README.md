# Video Download Bot

Этот бот для Telegram позволяет загружать видео с популярных платформ, таких как YouTube, Instagram, TikTok, Twitter/X, VK, Reddit и Dzen.

## 📌 Функционал
- 📥 Скачивание видео с поддерживаемых платформ.
- 🎥 Автоматическое сжатие видео при необходимости.
- 📂 Ограничение на размер файла (50MB).

## 🚀 Установка и запуск
### 1. Клонирование репозитория
```sh
git clone https://github.com/your-repo/video-download-bot.git
cd video-download-bot
```

### 2. Установка зависимостей
```sh
pip install -r requirements.txt
```

### 3. Создание `.env` файла
Создайте файл `token.env` и добавьте в него ваш токен бота:
```
BOT_TOKEN=your_telegram_bot_token
```

### 4. Запуск бота
```sh
python main.py
```

## 🛠 Используемые технологии
- [Aiogram](https://github.com/aiogram/aiogram) – асинхронная работа с Telegram API.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) – загрузка видео.
- [FFmpeg](https://ffmpeg.org/) – обработка видео.
- [dotenv](https://pypi.org/project/python-dotenv/) – управление переменными окружения.

## 📌 Поддерживаемые платформы
- YouTube
- Instagram
- TikTok
- Twitter/X
- VK
- Reddit
- Dzen

## 📜 Лицензия
Этот проект распространяется под лицензией MIT.

