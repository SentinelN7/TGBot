from aiogram import Router, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from services.database import connect_db, update_recommendations
from services.game_api import fetch_game_details
from handlers.menu import show_menu

router = Router()

class SearchGame(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_game_selection = State()
    waiting_for_rating = State()

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
    await state.clear()  # Полностью очищаем состояние
    await show_menu(message)  # Вызываем главное меню

async def start_new_search(message: Message, state: FSMContext):
    """Общий метод для начала поиска без лишних сообщений."""
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
    """Обрабатывает выбор игры из списка"""
    user_data = await state.get_data()
    game_options = user_data.get("game_options", {})

    if message.text not in game_options:
        await message.answer("Некорректный ввод. Введите номер игры из списка или отмените поиск.")
        return

    game_id = game_options[message.text]
    await show_game_info(message, game_id)
    await state.clear()

async def show_game_info(message: Message, game_id: int):
    """Отображает информацию об игре"""
    try:
        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                g.title, 
                TO_CHAR(g.release_date, 'DD.MM.YYYY') AS release_date, 
                COALESCE(string_agg(DISTINCT ge.name, ', '), 'Не указано') AS genre,
                COALESCE(string_agg(DISTINCT pl.name, ', '), 'Не указано') AS platforms,
                g.metascore, 
                g.cover_url
            FROM games g
            LEFT JOIN game_genres gg ON g.id = gg.game_id
            LEFT JOIN genres ge ON gg.genre_id = ge.id
            LEFT JOIN game_platforms gp ON g.id = gp.game_id
            LEFT JOIN platforms pl ON gp.platform_id = pl.id
            WHERE g.id = %s
            GROUP BY g.id;
        """, (game_id,))

        game = cursor.fetchone()
        conn.close()

        if not game:
            await message.answer("❌ Произошла ошибка. Игра не найдена в базе.")
            return

        title, release_date, genre, platforms, rating, cover_url = game

        # Загружаем доп. информацию (разработчик, издатель, slug, описание)
        details = await fetch_game_details(title)
        if not details:
            await message.answer("❌ Ошибка загрузки информации.")
            return

        developer = details.get("developer", "Не указано")
        publisher = details.get("publisher", "Не указано")
        slug = details.get("slug")

        text = (f"<b>{title}</b>\n"
                f"🛠 Разработчик: {developer}\n"
                f"🏢 Издатель: {publisher}\n"
                f"📅 Дата релиза: {release_date}\n"
                f"🎮 Жанр: {genre}\n"
                f"🖥 Платформы: {platforms}\n"
                f"⭐ Оценка: {rating if rating else 'Нет'}\n\n"
                "Для более детальной информации нажмите 'Подробнее'.")

        keyboard_buttons = []
        if slug:
            keyboard_buttons.append([types.InlineKeyboardButton(text="Подробнее", url=f"https://rawg.io/games/{slug}")])
        keyboard_buttons.append([types.InlineKeyboardButton(text="Добавить в избранное", callback_data=f"favorite_{game_id}")])
        keyboard_buttons.append([types.InlineKeyboardButton(text="Оценить", callback_data=f"rate_{game_id}")])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Отправляем сообщение с фото или без
        if cover_url:
            await message.answer_photo(photo=cover_url, caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка в show_game_info: {e}")  # Вывод в лог
        await message.answer("❌ Ошибка при загрузке информации об игре.")



@router.callback_query(lambda c: c.data.startswith("favorite_"))
async def add_to_favorites(callback: CallbackQuery):
    """Добавляет игру в избранное, если её там ещё нет."""
    game_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    conn = connect_db()
    cursor = conn.cursor()

    # Проверяем, есть ли игра в избранном
    cursor.execute("SELECT 1 FROM favorite_games WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s) AND game_id = %s", (user_id, game_id))
    already_favorited = cursor.fetchone()

    # Получаем название игры
    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
    game_record = cursor.fetchone()
    game_title = game_record[0]

    if already_favorited:
        await callback.message.answer(f"❌ Игра {game_title} уже в вашем избранном!")
        conn.close()
        return

    # Добавляем в избранное
    cursor.execute("INSERT INTO favorite_games (user_id, game_id) VALUES ((SELECT id FROM users WHERE telegram_id = %s), %s)", (user_id, game_id))
    conn.commit()
    conn.close()

    await callback.message.answer(f"✅ Игра {game_title} добавлена в избранное!")
    update_recommendations(user_id)


@router.callback_query(lambda c: c.data.startswith("rate_"))
async def rate_game(callback: CallbackQuery, state: FSMContext):
    game_id = int(callback.data.split("_")[1])
    await state.update_data(game_id=game_id)
    await callback.answer()
    await callback.message.answer("Введите оценку от 1 до 10:")
    await state.set_state(SearchGame.waiting_for_rating)


@router.message(SearchGame.waiting_for_rating)
async def process_rating(message: Message, state: FSMContext):
    try:
        rating = int(message.text)
        if rating < 1 or rating > 10:
            raise ValueError
    except ValueError:
        await message.answer("Некорректный ввод. Введите число от 1 до 10.")
        return

    user_data = await state.get_data()
    game_id = user_data.get("game_id")
    user_id = message.from_user.id

    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя из БД
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()

    if user_record:
        real_user_id = user_record[0]  # ID пользователя в БД

        # Получаем название игры
        cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
        game_record = cursor.fetchone()
        game_title = game_record[0]

        # Добавляем/обновляем оценку
        cursor.execute("""
            INSERT INTO rated_games (user_id, game_id, rating) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id, game_id) 
            DO UPDATE SET rating = EXCLUDED.rating;
        """, (real_user_id, game_id, rating))

        conn.commit()
        conn.close()

        await message.answer(f"Вы оценили игру {game_title} на {rating}/10.")
        update_recommendations(user_id)
    else:
        conn.close()
        await message.answer("Ошибка: не удалось найти ваш профиль.")

    await state.clear()


def register_handlers(dp):
    dp.include_router(router)
