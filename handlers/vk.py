from services.vk_parser import vk_parser
from aiogram import types
import logging

logger = logging.getLogger(__name__)

async def handle_vk_post(message: types.Message, url: str):
    """Улучшенный обработчик VK контента"""
    try:
        await message.answer("⏳ Получаю данные из VK...")
        data = await vk_parser.parse_vk_url(url)
        
        if not data:
            raise ValueError("Не удалось получить данные. Попробуйте позже или проверьте ссылку.")

        if data['type'] == 'video':
            await _handle_vk_media(message, data, is_video=True)
        elif data['type'] == 'post':
            await _handle_vk_wall_post(message, data)
        else:
            raise ValueError("Неизвестный тип контента")
            
    except Exception as e:
        logger.error(f"VK error: {str(e)}", exc_info=True)
        await message.answer(f"❌ Ошибка VK: {str(e)}")

async def _handle_vk_media(message: types.Message, data: dict, is_video: bool):
    """Обработка видео/клипов"""
    try:
        media_type = "видео" if is_video else "клип"
        
        if data.get('thumb'):
            await message.answer_photo(
                data['thumb'],
                caption=f"🎥 {data.get('title', media_type.capitalize() + ' VK')}"
            )
        
        if data.get('url'):
            await message.answer(f"🔗 Ссылка на {media_type}:\n{data['url']}")
        else:
            raise ValueError(f"Не найдена ссылка на {media_type}")
            
    except Exception as e:
        raise ValueError(f"Ошибка обработки {media_type}: {str(e)}")

async def _handle_vk_wall_post(message: types.Message, data: dict):
    """Обработка постов"""
    try:
        if data.get('text'):
            await message.answer(f"📝 Текст поста:\n\n{data['text']}")
        
        if not data.get('attachments'):
            await message.answer("ℹ️ В посте нет медиавложений")
            return
            
        for attach in data['attachments']:
            if attach['type'] == 'photo':
                await message.answer_photo(attach['url'])
            elif attach['type'] == 'video':
                await message.answer(f"🎥 Видео в посте: {attach['url']}")
                
    except Exception as e:
        raise ValueError(f"Ошибка обработки поста: {str(e)}")