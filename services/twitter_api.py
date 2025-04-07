import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

async def try_nitter(url: str) -> Optional[Dict]:
    """Пытается получить данные через Nitter (анонимный Twitter фронтенд)"""
    try:
        nitter_url = url.replace('twitter.com', 'nitter.net').replace('x.com', 'nitter.net')
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(nitter_url, timeout=10) as resp:
                soup = BeautifulSoup(await resp.text(), 'html.parser')
                
                tweet_text = ""
                if content_div := soup.find('div', class_='tweet-content'):
                    tweet_text = content_div.get_text('\n').strip()
                
                images = []
                if gallery := soup.find('div', class_='attachments'):
                    images = [
                        f'https://nitter.net{img["src"]}' 
                        for img in gallery.find_all('img') 
                        if img.get('src')
                    ]
                
                return {
                    'success': bool(tweet_text or images),
                    'data': {
                        'text': tweet_text,
                        'images': images[:4]
                    }
                }
    except Exception:
        return None

async def get_twitter_post(url: str) -> Dict:
    """Основной метод получения Twitter поста"""
    if nitter_data := await try_nitter(url):
        return nitter_data['data']
    
    raise ValueError("Не удалось получить содержимое поста")