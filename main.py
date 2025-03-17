import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.filters import Command
from config import TOKEN
from handlers import start, profile, search, favorites, rated_games, not_interested, recommendations, menu
from handlers.menu import show_menu
from services.update_games import start_scheduled_updates


async def reset_state(message: Message, state: FSMContext):
    """Сбрасывает состояние пользователя и отправляет в главное меню"""
    await state.clear()  # Сбрасываем состояние
    await message.answer("🔄 *Состояние сброшено. Возвращаем вас в главное меню...*")
    await menu.show_menu(message)  # Показываем главное меню


async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Регистрация обработчиков
    start.register_handlers(dp)
    profile.register_handlers(dp)
    search.register_handlers(dp)
    favorites.register_handlers(dp)
    rated_games.register_handlers(dp)
    not_interested.register_handlers(dp)
    recommendations.register_handlers(dp)
    menu.register_handlers(dp)

    # Регистрация команды /reset
    dp.message.register(reset_state, Command("reset"))

    await start_scheduled_updates()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
