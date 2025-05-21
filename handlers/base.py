import re
from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PLATFORMS, CHANNEL_ID, CHANNEL_LINK, SUPPORT_LINK, NEURAL_NETWORK_POST
from handlers.instagram import handle_instagram
from handlers.vk import handle_vk_post
from handlers.video import handle_video_download
from handlers.vk_video import handle_vk_video_download
import logging

logger = logging.getLogger(__name__)
router = Router()

class UserState(StatesGroup):
    waiting_instagram = State()
    waiting_vk = State()
    waiting_youtube = State()

def get_main_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Instagram", callback_data="platform_instagram"),
                InlineKeyboardButton(text="VKontakte", callback_data="platform_vk"),
                InlineKeyboardButton(text="Youtube", callback_data="platform_youtube")
            ],
            [
                InlineKeyboardButton(text="Нейросети", url=NEURAL_NETWORK_POST),
                InlineKeyboardButton(text="Тех.поддержка", url=SUPPORT_LINK)
            ]
        ]
    )

def get_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main")]
        ]
    )

async def check_subscription(user_id: int, bot: Bot):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {str(e)}")
        return True  # Разрешаем работу если канал недоступен

@router.message(Command("start"))
async def start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    
    if not await check_subscription(message.from_user.id, bot):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_LINK)],
                [InlineKeyboardButton(text="Я подписался", callback_data="check_subscription")]
            ]
        )
        await message.answer(
            "📢 Для использования бота необходимо подписаться на наш канал!",
            reply_markup=keyboard
        )
        return
    
    await show_main_menu(message)

async def show_main_menu(message: Message):
    await message.answer(
        "📥 Я умею скачивать видео из Instagram, VKontakte, Youtube без водяных знаков - HD в лучшем качестве бесплатно.\n\n"
        "• Выберите соцсеть - отправьте ссылку - получите видео.\n\n"
        "(Также умею работать с нейросетями и создавать текст, музыку, графику и др😼)",
        reply_markup=get_main_inline_keyboard()
    )

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, bot: Bot):
    if await check_subscription(callback.from_user.id, bot):
        await callback.message.delete()
        await show_main_menu(callback.message)
    else:
        await callback.answer("Вы ещё не подписались на канал!", show_alert=True)

@router.callback_query(F.data.startswith("platform_"))
async def platform_button_handler(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split("_")[1]
    
    if platform == "instagram":
        await state.set_state(UserState.waiting_instagram)
        text = "Отправьте ссылку на видео из Instagram для скачивания 👇"
    elif platform == "vk":
        await state.set_state(UserState.waiting_vk)
        text = "Отправьте ссылку на видео из VKontakte для скачивания 👇"
    elif platform == "youtube":
        await state.set_state(UserState.waiting_youtube)
        text = "Отправьте ссылку на видео из Youtube для скачивания 👇"
    else:
        await callback.answer()
        return
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(callback.message)
    await callback.answer()

@router.message(UserState.waiting_instagram, F.text)
async def handle_instagram_link(message: Message, bot: Bot, state: FSMContext):
    url = message.text.strip()
    if not re.search(PLATFORMS["instagram"], url, re.IGNORECASE):
        await message.answer(
            "Это не похоже на ссылку Instagram. Попробуйте еще раз.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.clear()
    await handle_instagram(message, url, bot)
    await show_main_menu(message)

@router.message(UserState.waiting_vk, F.text)
async def handle_vk_link(message: Message, bot: Bot, state: FSMContext):
    url = message.text.strip()
    if not re.search(PLATFORMS["vk"], url, re.IGNORECASE):
        await message.answer(
            "Это не похоже на ссылку VK. Попробуйте еще раз.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.clear()
    if any(p in url for p in ['/clip']):
        await handle_vk_video_download(message, url, bot)
    elif any(p in url for p in ['wall-', '?w=wall']):
        await handle_vk_post(message, url)
    else:
        await message.answer("Укажите прямую ссылку на видео или пост VK")
    
    await show_main_menu(message)

@router.message(UserState.waiting_youtube, F.text)
async def handle_youtube_link(message: Message, bot: Bot, state: FSMContext):
    url = message.text.strip()
    if not re.search(PLATFORMS["youtube"], url, re.IGNORECASE):
        await message.answer(
            "Это не похоже на ссылку YouTube. Попробуйте еще раз.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.clear()
    await handle_video_download(message, url, bot)
    await show_main_menu(message)

def register_base_handlers(dp):
    dp.include_router(router)
    