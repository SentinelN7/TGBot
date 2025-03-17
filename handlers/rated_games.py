from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.database import get_rated_games, update_game_rating, remove_game_rating
from handlers.profile import ProfileState, show_profile

router = Router()

@router.callback_query(lambda c: c.data == "rated_games")
async def show_rated_games(callback: CallbackQuery, state: FSMContext):
    """Выводит список оцененных игр"""
    user_id = callback.from_user.id
    rated_games = get_rated_games(user_id)

    if not rated_games:
        text = "❌ *Вы ещё не оценивали игры*"
    else:
        text = format_rated_games(rated_games)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Удалить/изменить оценку", callback_data="modify_rating")],
        [InlineKeyboardButton(text="🔙 Вернуться в личный кабинет", callback_data="back_to_profile")]
    ])

    message = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.update_data(last_rated_message=message.message_id)


def format_rated_games(rated_games):
    """Форматирует список оцененных игр"""
    sorted_games = sorted(rated_games, key=lambda x: x[1])  # Сортируем по названию
    text = "⭐ *Оцененные вами игры:*\n\n"

    for i, (_, game_name, rating) in enumerate(sorted_games, start=1):
        text += f"{i}. {game_name}: {rating}/10\n"

    return text


@router.callback_query(lambda c: c.data == "modify_rating")
async def ask_game_number(callback: CallbackQuery, state: FSMContext):
    """Запрашивает у пользователя номер игры для изменения или удаления оценки"""
    await callback.answer()
    await callback.message.answer("Введите номер игры, оценку которой хотите изменить:")
    await state.set_state(ProfileState.waiting_for_rating_change)


@router.message(ProfileState.waiting_for_rating_change)
async def modify_rating(message: Message, state: FSMContext):
    """Изменяет или удаляет оценку игры"""
    user_id = message.from_user.id
    rated_games = get_rated_games(user_id)

    if not rated_games:
        await message.answer("❌ У вас нет оцененных игр.")
        await state.clear()
        return

    # Сортируем список так же, как в format_rated_games
    sorted_games = sorted(rated_games, key=lambda x: x[1])

    try:
        game_index = int(message.text) - 1
        if game_index < 0 or game_index >= len(sorted_games):
            await message.answer("❌ Неверный номер игры. Попробуйте снова.")
            return
    except ValueError:
        await message.answer("❌ Введите число, соответствующее номеру игры.")
        return

    game_id, game_name, _ = sorted_games[game_index]  # Теперь индекс соответствует списку
    await state.update_data(selected_game_id=game_id, selected_game_name=game_name)
    await message.answer(f"Введите новую оценку для игры «{game_name}» (от 1 до 10) или 0 для удаления:")
    await state.set_state(ProfileState.waiting_for_new_rating)


@router.message(ProfileState.waiting_for_new_rating)
async def set_new_rating(message: Message, state: FSMContext):
    """Устанавливает новую оценку или удаляет игру из списка оцененных"""
    user_id = message.from_user.id
    data = await state.get_data()
    game_id = data.get("selected_game_id")
    game_name = data.get("selected_game_name")

    try:
        new_rating = int(message.text)
        if new_rating < 0 or new_rating > 10:
            await message.answer("❌ Введите число от 1 до 10 или 0 для удаления.")
            return
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return

    if new_rating == 0:
        remove_game_rating(user_id, game_id)
        action_text = "удалена из списка оцененных игр."
    else:
        update_game_rating(user_id, game_id, new_rating)
        action_text = f"обновлена до {new_rating}/10."

    # Удаляем последнее сообщение со списком оцененных игр
    last_message_id = data.get("last_rated_message")
    if last_message_id:
        try:
            await message.chat.delete_message(last_message_id)
        except Exception:
            pass  # Игнорируем ошибку, если сообщение уже удалено

    await message.answer(f"✅ *Оценка игры «{game_name}» {action_text}*", parse_mode="Markdown")
    await show_profile(message, state)  # Возвращаемся в личный кабинет


def register_handlers(dp):
    dp.include_router(router)
