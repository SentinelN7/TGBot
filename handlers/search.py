from aiogram import Router, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from services.database import connect_db, update_recommendations, update_last_activity, update_user_state
from services.game_api import fetch_game_details
from handlers.menu import show_menu
from services import game_card

router = Router()

class SearchGame(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_game_selection = State()

# Клавиатуры
search_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Поиск новой игры")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ],
    resize_keyboard=True
)


@router.message(lambda msg: msg.text == "🔍 Поиск игры")
async def start_search(message: Message, state: FSMContext):
    update_user_state(message.from_user.id, "Search")
    intro_text = (
        "🔎 *Вы в режиме поиска игр*\n\n"
        "Здесь вы сможете найти нужную вам игру из огромного массива игр, "
        "поставить оценку, почитать информацию или добавить в избранное.\n\n"
        "📌 *Правила:*\n"
        "1️⃣ Название игры можно ввести неполностью, вы сможете выбрать нужную вам игру из найденных вариантов.\n"
        "2️⃣ Название должно быть на *английском языке*, за исключением редких случаев.\n"
        "3️⃣ Не используйте сокращения, например MK, COD, CS и т.д.\n\n"
        "🔄 Для запуска поиска другой игры, после того, как вы нашли искомую, нажмите *Поиск новой игры* в меню.\n"
        "❗ В случае ошибок или если вы не нашли нужную вам игру, обратитесь к разработчику.\n"
        "🎮 *Удачи!*"
    )

    await message.answer(intro_text, parse_mode="Markdown", reply_markup=search_keyboard)
    await start_new_search(message, state)

@router.message(lambda msg: msg.text == "🔄 Поиск новой игры")
async def restart_search(message: Message, state: FSMContext):
    """Повторный поиск игры без вводного сообщения."""
    await start_new_search(message, state)

@router.message(lambda msg: msg.text == "🔙 Вернуться в главное меню")
async def exit_search_mode(message: Message, state: FSMContext):
    await state.clear()
    await show_menu(message)

async def start_new_search(message: Message, state: FSMContext):
    update_last_activity(message.from_user.id)
    await message.answer("Введите название игры для поиска:")
    await state.set_state(SearchGame.waiting_for_search_query)

@router.message(SearchGame.waiting_for_search_query)
async def process_search(message: Message, state: FSMContext):
    """Обрабатывает поиск игры"""
    search_query = message.text.strip().lower()

    try:
        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, title FROM games 
            WHERE LOWER(title) LIKE %s 
            LIMIT 50;
        """, (f"%{search_query}%",))

        games = cursor.fetchall()
        conn.close()

        if not games:
            await message.answer("❌ Игр с таким названием не найдено. Попробуйте еще раз.")
            return

        if len(games) == 1:
            game_id, game_title = games[0]
            await show_game_info(message, game_id)
            await state.clear()
            return

        response = "Найдено несколько игр. Выберите номер из списка:\n"
        game_options = {}
        for index, (game_id, game_title) in enumerate(games, start=1):
            response += f"{index}. {game_title}\n"
            game_options[str(index)] = game_id

        await state.update_data(game_options=game_options)
        await message.answer(response + "\nОтправьте номер нужной игры.")
        await state.set_state(SearchGame.waiting_for_game_selection)

    except Exception as e:
        await message.answer("❌ Произошла ошибка при поиске. Попробуйте позже.")

@router.message(SearchGame.waiting_for_game_selection)
async def select_game(message: Message, state: FSMContext):
    update_last_activity(message.from_user.id)
    user_data = await state.get_data()
    game_options = user_data.get("game_options", {})

    if message.text not in game_options:
        await message.answer("Некорректный ввод. Введите номер игры из списка или отмените поиск.")
        return

    game_id = game_options[message.text]
    await game_card.show_game(message, game_id)
    await state.clear()


def register_handlers(dp):
    dp.include_router(router)
    dp.include_router(game_card.router)
