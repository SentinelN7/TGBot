from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.database import get_not_interested_games, remove_not_interested_game, update_recommendations, update_last_activity, update_user_state
from handlers.profile import ProfileState, show_profile

router = Router()

@router.callback_query(lambda c: c.data == "not_interested")
async def show_not_interested(callback: CallbackQuery, state: FSMContext):
    """Выводит список неинтересных игр"""
    user_id = callback.from_user.id
    update_last_activity(user_id)
    update_user_state(user_id, "Not interesting games")
    not_interested_games = get_not_interested_games(user_id)

    if not not_interested_games:
        text = "❌ *Вы ещё не отметили игры как неинтересные*"
    else:
        text = format_not_interested_games(not_interested_games)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить игру", callback_data="remove_not_interested_game")],
        [InlineKeyboardButton(text="🔙 Вернуться в личный кабинет", callback_data="back_to_profile")]
    ])

    message = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.update_data(last_not_interested_message=message.message_id)


def format_not_interested_games(not_interested_games):
    """Форматирует список неинтересных игр в алфавитном порядке"""
    sorted_games = sorted(not_interested_games, key=lambda x: x[1])  # Сортируем по названию
    text = "🚫 *Неинтересные игры:*\n\n"

    for i, (_, game_name) in enumerate(sorted_games, start=1):
        text += f"{i}. {game_name}\n"

    return text


@router.callback_query(lambda c: c.data == "remove_not_interested_game")
async def ask_game_number(callback: CallbackQuery, state: FSMContext):
    """Запрашивает у пользователя номер игры для удаления"""
    update_last_activity(callback.from_user.id)
    await callback.answer()
    await callback.message.answer("Введите номер игры, которую хотите удалить:")
    await state.set_state(ProfileState.waiting_for_not_interested_game_number)


@router.message(ProfileState.waiting_for_not_interested_game_number)
async def remove_game(message: Message, state: FSMContext):
    """Удаляет игру из списка неинтересных по введенному номеру"""
    user_id = message.from_user.id
    not_interested_games = get_not_interested_games(user_id)

    if not not_interested_games:
        await message.answer("❌ У вас нет неинтересных игр.")
        await state.clear()
        return

    # Сортируем список так же, как в format_not_interested_games
    sorted_games = sorted(not_interested_games, key=lambda x: x[1])

    try:
        game_index = int(message.text) - 1
        if game_index < 0 or game_index >= len(sorted_games):
            await message.answer("❌ Неверный номер игры. Попробуйте снова.")
            return
    except ValueError:
        await message.answer("❌ Введите число, соответствующее номеру игры.")
        return

    game_id, game_name = sorted_games[game_index]  # Теперь индекс соответствует списку
    remove_not_interested_game(user_id, game_id)

    # Удаляем последнее сообщение со списком неинтересных игр
    data = await state.get_data()
    last_message_id = data.get("last_not_interested_message")

    if last_message_id:
        try:
            await message.chat.delete_message(last_message_id)
        except Exception:
            pass  # Игнорируем ошибку, если сообщение уже удалено

    await message.answer(f"✅ *Игра «{game_name}» удалена из списка неинтересных.*", parse_mode="Markdown")
    update_recommendations(user_id)
    await show_profile(message, state)  # Возвращаемся в личный кабинет


def register_handlers(dp):
    dp.include_router(router)
