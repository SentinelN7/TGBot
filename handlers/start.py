from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.database import save_survey, get_user_profile, update_recommendations, user_exists
from handlers.menu import show_menu

router = Router()

# Словарь для хранения данных пользователей (пока в оперативной памяти)
user_data = {}

# Доступные платформы и жанры
PLATFORMS = ["PlayStation 5", "PlayStation 4", "PlayStation 3", "Xbox Series X/S", "Xbox One", "Xbox 360", "PC", "Nintendo Switch"]
GENRES = ["Action", "RPG", "Shooter", "Strategy", "Simulator", "Arcade", "Fighting", "Adventure", "Puzzle"]

# Определение состояний анкеты
class SurveyStates(StatesGroup):
    choosing_platform = State()
    choosing_genre = State()
    entering_favorite_games = State()

# Функция генерации главного меню анкеты
def generate_survey_keyboard(user_id):
    data = user_data.get(user_id, {"platform": "не выбрано", "genre": "не выбрано", "games": "не указаны"})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🕹 Платформа: {data['platform']}", callback_data="choose_platform")],
        [InlineKeyboardButton(text=f"🎮 Любимый жанр: {data['genre']}", callback_data="choose_genre")],
        [InlineKeyboardButton(text=f"🏆 Любимые игры: {data['games']}", callback_data="choose_games")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_survey")]
    ])
    return keyboard

@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext, edit: bool = False):
    user_id = message.from_user.id

    if not edit and user_exists(user_id):
        username = message.from_user.first_name
        await message.answer(f"Мы вас вспомнили. С возвращением, {username}!")
        await show_menu(message)
        return

    user_data.setdefault(user_id, {"platform": "не выбрано", "genre": "не выбрано", "games": "не указаны"})

    text = ("📋 Анкета\n\n"
            "Поля 'Платформа' и 'Жанр' должны быть обязательно заполнены!")
    reply_markup = generate_survey_keyboard(user_id)

    if edit:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.answer(text, reply_markup=reply_markup)

@router.callback_query(lambda c: c.data == "choose_platform")
async def choose_platform(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=platform, callback_data=f"set_platform:{platform}")] for platform in PLATFORMS
    ])
    await callback.message.edit_text("Выберите платформу:", reply_markup=keyboard)
    await state.set_state(SurveyStates.choosing_platform)

@router.callback_query(lambda c: c.data.startswith("set_platform:"))
async def set_platform(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[1]
    user_data[callback.from_user.id]["platform"] = platform
    await callback.message.edit_text("📋 Анкета", reply_markup=generate_survey_keyboard(callback.from_user.id))
    await state.clear()

@router.callback_query(lambda c: c.data == "choose_genre")
async def choose_genre(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=genre, callback_data=f"set_genre:{genre}")] for genre in GENRES
    ])
    await callback.message.edit_text("Выберите жанр:", reply_markup=keyboard)
    await state.set_state(SurveyStates.choosing_genre)

@router.callback_query(lambda c: c.data.startswith("set_genre:"))
async def set_genre(callback: CallbackQuery, state: FSMContext):
    genre = callback.data.split(":")[1]
    user_data[callback.from_user.id]["genre"] = genre
    await callback.message.edit_text("📋 Анкета", reply_markup=generate_survey_keyboard(callback.from_user.id))
    await state.clear()

@router.callback_query(lambda c: c.data == "choose_games")
async def choose_games(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите любимые игры через запятую:")
    await state.set_state(SurveyStates.entering_favorite_games)

@router.message(SurveyStates.entering_favorite_games)
async def set_games(message: Message, state: FSMContext):
    user_data[message.from_user.id]["games"] = message.text
    await message.answer("📋 Анкета", reply_markup=generate_survey_keyboard(message.from_user.id))
    await state.clear()

@router.callback_query(lambda c: c.data == "finish_survey")
async def finish_survey(callback: CallbackQuery):
    data = user_data.get(callback.from_user.id, {})
    if data.get("platform") == "не выбрано":
        await callback.answer("⚠️ Сначала выберите платформу!", show_alert=True)
        return
    if data.get("genre") == "не выбрано":
        await callback.answer("⚠️ Сначала выберите жанр!", show_alert=True)
        return

    save_survey(
        telegram_id=callback.from_user.id,
        platform=data.get("platform", ""),
        genre=data.get("genre", ""),
        favorite_games=data.get("games", "")
    )

    user_id = callback.from_user.id
    update_recommendations(user_id)


    text = (f"✅ Анкета заполнена!\n\n"
            f"🕹 Платформа: {data['platform']}\n"
            f"🎮 Любимый жанр: {data['genre']}\n"
            f"🏆 Любимые игры: {data['games']}")
    await callback.message.delete()
    await callback.message.answer(text)

    # Автоматически показываем меню после завершения анкеты
    await show_menu(callback.message)

def register_handlers(dp):
    dp.include_router(router)
