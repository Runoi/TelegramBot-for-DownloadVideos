import re
import aiohttp
from typing import Dict, List
from config import VK_ACCESS_TOKEN, VK_API_VERSION
import logging

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

async def get_vk_post(url: str) -> Dict[str, List[str]]:
    """
    Получает данные поста VK через API
    Возвращает словарь с текстом и списком URL изображений
    """
    match = re.search(r'wall(-?\d+)_(\d+)', url)
    if not match:
        raise ValueError("Invalid VK post URL")

    owner_id, post_id = match.groups()
    
    params = {
        'access_token': VK_ACCESS_TOKEN,
        'v': VK_API_VERSION,
        'posts': f"{owner_id}_{post_id}",
        'extended': 1,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.vk.com/method/wall.getById', params=params) as resp:
            data = await resp.json()
            
            if 'error' in data:
                raise ValueError(f"VK API error: {data['error']['error_msg']}")
            
            post = data['response']['items'][0]
            result = {
                'text': post.get('text', ''),
                'images': []
            }
            
            for attachment in post.get('attachments', []):
                if attachment['type'] == 'photo':
                    sizes = attachment['photo'].get('sizes', [])
                    if sizes:
                        max_size = max(sizes, key=lambda x: x.get('width', 0))
                        result['images'].append(max_size['url'])
            
            return result