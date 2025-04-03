import json
import os
import re
import aiohttp
import logging
from typing import Optional, Dict
from urllib.parse import unquote

logger = logging.getLogger(__name__)

class VKParser:
    def __init__(self, access_token: str = None, api_version: str = "5.199"):
        self.access_token = access_token
        self.api_version = api_version
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
        }

    async def parse_vk_url(self, url: str) -> Optional[Dict]:
        """Универсальный парсер для всех типов контента VK"""
        try:
            # Нормализация URL
            url = self._normalize_url(url)
            
            if self._is_clip(url):
                return await self._parse_clip(url)
            elif self._is_video(url):
                return await self._parse_video(url)
            elif self._is_wall_post(url):
                return await self._parse_wall_post(url)
                
            raise ValueError("Неподдерживаемый тип ссылки VK")
        except Exception as e:
            logger.error(f"Ошибка парсинга: {str(e)}", exc_info=True)
            return None

    def _normalize_url(self, url: str) -> str:
        """Приводим URL к стандартному виду"""
        if 'vkvideo.ru' in url:
            return url.replace('vkvideo.ru', 'vk.com/video')
        return url

    def _is_clip(self, url: str) -> bool:
        return any(p in url for p in ['/clip-', 'vk.com/clip'])

    def _is_video(self, url: str) -> bool:
        return any(p in url for p in ['/video-', 'vk.com/video', 'video_ext.php'])

    def _is_wall_post(self, url: str) -> bool:
        return any(p in url for p in ['/wall', 'w=wall'])

    async def _parse_clip(self, url: str) -> Dict:
        """Парсинг клипов VK"""
        clip_id = self._extract_id(url, is_clip=True)
        if not clip_id:
            raise ValueError("Не удалось извлечь ID клипа")

        # Пробуем API
        if self.access_token:
            api_data = await self._get_video_via_api(clip_id)
            if api_data:
                return api_data

        # Fallback через HTML
        return await self._parse_via_html(url, is_clip=True)

    async def _parse_video(self, url: str) -> Dict:
        """Парсинг обычных видео"""
        video_id = self._extract_id(url)
        if not video_id:
            raise ValueError("Не удалось извлечь ID видео")

        # Пробуем API
        if self.access_token:
            api_data = await self._get_video_via_api(video_id)
            if api_data:
                return api_data

        # Fallback через HTML
        return await self._parse_via_html(url)

    def _extract_id(self, url: str, is_clip: bool = False) -> Optional[str]:
        """Извлекает ID из URL"""
        patterns = [
            r'clip-(\d+_\d+)' if is_clip else r'video-(\d+_\d+)',
            r'vid=(\d+_\d+)',
            r'oid=(\d+)&id=(\d+)',
            r'\/(\d+_\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                if len(match.groups()) > 1:
                    return f"{match.group(1)}_{match.group(2)}"
                return match.group(1)
        return None

    async def _get_video_via_api(self, video_id: str) -> Optional[Dict]:
        """Получение видео через API"""
        params = {
            'access_token': self.access_token,
            'v': self.api_version,
            'videos': video_id,
            'extended': 1
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.vk.com/method/video.get', params=params) as resp:
                    data = await resp.json()
                    if 'error' in data:
                        logger.warning(f"API error: {data['error']}")
                        return None
                    
                    item = data['response']['items'][0]
                    return {
                        'type': 'video',
                        'url': item.get('player'),
                        'title': item.get('title'),
                        'duration': item.get('duration'),
                        'thumb': max(item.get('image', []), key=lambda x: x.get('width', 0))['url'] if item.get('image') else None
                    }
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            return None

    async def _parse_via_html(self, url: str, is_clip: bool = False) -> Dict:
        """Парсинг через HTML страницу"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as resp:
                    html = await resp.text()
                    
                    # Ищем JSON с данными
                    json_match = re.search(r'var\s+videoPlayer\s*=\s*({.+?});', html)
                    if json_match:
                        data = json.loads(unquote(json_match.group(1)))
                        return {
                            'type': 'video',
                            'url': data.get('url'),
                            'title': 'Клип VK' if is_clip else 'Видео VK',
                            'thumb': data.get('poster')
                        }
                    
                    # Альтернативный поиск
                    url_match = re.search(r'"url":"(https:\\/\\/[^"]+\.mp4)', html)
                    if url_match:
                        return {
                            'type': 'video',
                            'url': url_match.group(1).replace('\\/', '/'),
                            'title': 'Клип VK' if is_clip else 'Видео VK'
                        }
                    
                    raise ValueError("Не найдены данные видео")
        except Exception as e:
            logger.error(f"HTML parsing failed: {str(e)}")
            raise ValueError("Не удалось обработать страницу")

    async def _parse_wall_post(self, url: str) -> Dict:
        """Парсинг постов"""
        post_id = self._extract_post_id(url)
        if not post_id:
            raise ValueError("Неверный URL поста")

        params = {
            'access_token': self.access_token,
            'v': self.api_version,
            'posts': post_id,
            'extended': 1
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.vk.com/method/wall.getById', params=params) as resp:
                    data = await resp.json()
                    if 'error' in data:
                        logger.warning(f"API error: {data['error']}")
                        raise ValueError(data['error']['error_msg'])
                    
                    post = data['response']['items'][0]
                    attachments = []
                    
                    for attach in post.get('attachments', []):
                        if attach['type'] == 'photo':
                            sizes = attach['photo'].get('sizes', [])
                            if sizes:
                                attachments.append({
                                    'type': 'photo',
                                    'url': max(sizes, key=lambda x: x.get('width', 0))['url']
                                })
                        elif attach['type'] == 'video':
                            attachments.append({
                                'type': 'video',
                                'url': f"https://vk.com/video{attach['video']['owner_id']}_{attach['video']['id']}",
                                'title': attach['video'].get('title')
                            })
                    
                    return {
                        'type': 'post',
                        'text': post.get('text', ''),
                        'attachments': attachments
                    }
        except Exception as e:
            logger.error(f"Post parsing failed: {str(e)}")
            raise ValueError("Не удалось получить данные поста")

    def _extract_post_id(self, url: str) -> Optional[str]:
        """Извлекает ID поста из разных форматов ссылок"""
        patterns = [
            r'wall(-?\d+_\d+)',  # Стандартный формат
            r'w=wall(-?\d+_\d+)',  # Для ссылок вида ?w=wall-...
            r'\/wall(\d+_\d+)',    # Для коротких ссылок
            r'\?z=wall(-?\d+_\d+)'  # Для мобильных ссылок
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    async def extract_video_url(self, url: str) -> Optional[str]:
        """
        Специальный метод для обработчика vk_video.py
        Возвращает только прямую ссылку на видео
        """
        data = await self.parse_vk_url(url)
        if not data or data.get('type') != 'video':
            return None
        
        # Для vkvideo.ru добавляем параметры качества
        if 'vkvideo.ru' in url:
            return f"{data['url']}?extra=1&hd=1"
        
        return data.get('url')
    async def _parse_video(self, url: str) -> Optional[Dict]:
        """Улучшенный парсинг видео"""
        video_id = self._extract_id(url)
        if not video_id:
            raise ValueError("Неверный URL видео")

        # Пробуем API
        api_data = await self._get_video_via_api(video_id)
        if api_data:
            return api_data

        # Fallback 1: Парсинг HTML
        html_data = await self._parse_via_html(url)
        if html_data:
            return html_data

        # Fallback 2: Для vkvideo.ru
        if 'vkvideo.ru' in url:
            return {
                'type': 'video',
                'url': f"https://vkvideo.ru/{video_id.replace('_', '/')}",
                'title': 'Видео из VK'
            }

        raise ValueError("Не удалось получить данные видео")

vk_parser = VKParser(
    access_token=os.getenv('VK_ACCESS_TOKEN'),
    api_version=os.getenv('VK_API_VERSION', '5.199')
)