"""
Пакет моделей данных.
Содержит схемы данных для работы с API платформ.
"""

from .schemas import (
    VKPostData,
    TwitterPostData,
    MediaItem,
    VideoInfo
)

__all__ = [
    'VKPostData',
    'TwitterPostData',
    'MediaItem',
    'VideoInfo'
]