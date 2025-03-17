from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

router = Router()

# Клавиатура для главного меню
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Поиск игры"), KeyboardButton(text="🎮 Личный кабинет")],
        [KeyboardButton(text="⭐ Рекомендации")]
    ],
    resize_keyboard=True
)

@router.message(Command("menu"))
async def show_menu(message: Message):
    """Показывает главное меню с описанием функций"""
    text = (
        "📌 **Главное меню**\n\n"
        "🔍 **Поиск игры** — найди информацию о любой игре.\n"
        "🎮 **Личный кабинет** — настрой свои предпочтения и посмотри сохраненные игры.\n"
        "⭐ **Рекомендации** — получи список игр, которые могут тебе понравиться.\n\n"
        "⚠️ **Обратите внимание:** любые отправленные здесь сообщения будут автоматически удалены."
    )
    await message.answer(text, reply_markup=menu_keyboard, parse_mode="Markdown")

@router.message()
async def delete_unwanted_messages(message: Message):
    """Удаляет любое сообщение, отправленное в меню"""
    await message.delete()

def register_handlers(dp):
    dp.include_router(router)
