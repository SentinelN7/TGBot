import aiohttp
import requests
import logging
from io import BytesIO
from PIL import Image
from aiogram import Router, types, Bot
from aiogram.types import Message, BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from services.database import connect_db, update_recommendations
from services.game_api import fetch_game_details

router = Router()

class ShowingGame(StatesGroup):
    waiting_for_rating = State()


async def process_game_image(cover_url: str):
    """ Обработка изображений (обложек игр) """
    if not cover_url:
        return None

    try:
        response = requests.get(cover_url, timeout=10)
        if response.status_code == 200:
            image_data = response.content
            file_size = len(image_data)

            if file_size > 5 * 1024 * 1024:  # Если изображение больше 5MB, уменьшаем его
                img = Image.open(BytesIO(image_data))
                img_format = img.format if img.format else "JPEG"  # Определяем формат

                # Сжимаем изображение (уменьшаем качество и размер)
                output_buffer = BytesIO()
                img.thumbnail((1280, 720))  # Ограничиваем максимальное разрешение
                img.save(output_buffer, format=img_format, quality=85)  # Сохраняем с сжатием
                image_data = output_buffer.getvalue()  # Получаем данные сжатого изображения

            # Отправляем сжатое изображение
            return BufferedInputFile(image_data, filename="cover.jpg")

        else:
            print(f"Ошибка загрузки изображения: {response.status_code}")
            return None

    except Exception as e:
        print(f"Ошибка при обработке изображения: {e}")
        return None


async def show_game_message(message: Message, game_id: int, from_recommendations=False):
    """ Отображает карточку игры пользователю (только для игр из поиска и списка рекомендаций) """
    user_id = message.from_user.id

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
            logging.warning(f"Игра (ID {game_id}) не найдена в базе")
            await message.answer("❌ Произошла ошибка. Игра не найдена в базе.")
            return

        title, release_date, genre, platforms, rating, cover_url = game
        logging.info(f"Пользователь {user_id} получил карточку игры: {title}")

        details = await fetch_game_details(title)
        if not details:
            logging.error(f"Ошибка загрузки деталей игры: {title}")
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

        if from_recommendations:
            keyboard_buttons.append([types.InlineKeyboardButton(text="Неинтересно", callback_data=f"not_interested_{game_id}")])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        image = await process_game_image(cover_url)
        if image:
            await message.answer_photo(photo=image, caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка в show_game_message у пользователя {user_id}: {e}")
        await message.answer("❌ Ошибка при загрузке информации об игре.")


async def show_game_bot(user_id: int, game_id: int, bot):
    """ Отображает карточку игры пользователю (только для игр из интервальных рекомендаций) """
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
        keyboard_buttons.append([types.InlineKeyboardButton(text="Неинтересно", callback_data=f"not_interested_{game_id}")])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        image = await process_game_image(cover_url)
        if image:
            await bot.send_photo(user_id, photo=image, caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка в show_game_bot у пользователя {user_id}: {e}")
        await bot.send_message(user_id, "❌ Ошибка при загрузке информации об игре.")


@router.callback_query(lambda c: c.data.startswith("favorite_"))
async def add_to_favorites(callback: CallbackQuery):
    """ Добавляет игру в избранное пользователя """
    game_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} добавляет в избранное игру (ID {game_id})")

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM favorite_games WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s) AND game_id = %s", (user_id, game_id))
    already_favorited = cursor.fetchone()

    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
    game_record = cursor.fetchone()
    game_title = game_record[0]

    if already_favorited:
        logging.info(f"Пользователь {user_id} пытался добавить в избранное уже ранее добавленную игру: {game_title}")
        await callback.message.answer(f"❌ Игра {game_title} уже в вашем избранном!")
        conn.close()
        return

    cursor.execute("INSERT INTO favorite_games (user_id, game_id) VALUES ((SELECT id FROM users WHERE telegram_id = %s), %s)", (user_id, game_id))
    conn.commit()
    conn.close()

    logging.info(f"Игра {game_title} добавлена в избранное пользователем {user_id}")
    await callback.message.answer(f"✅ Игра {game_title} добавлена в избранное!")
    update_recommendations(user_id)


@router.callback_query(lambda c: c.data.startswith("rate_"))
async def rate_game(callback: CallbackQuery, state: FSMContext):
    """ Запрашивает у пользователя оценку игры """
    user_id = callback.from_user.id
    game_id = int(callback.data.split("_")[1])

    logging.info(f"Пользователь {user_id} хочет оценить игру (ID {game_id})")

    await state.update_data(game_id=game_id)
    await callback.answer()
    await callback.message.answer("Введите оценку от 1 до 10:")
    await state.set_state(ShowingGame.waiting_for_rating)


@router.message(ShowingGame.waiting_for_rating)
async def process_rating(message: Message, state: FSMContext):
    user_id = message.from_user.id
    """ Сохраняет оценку игры """
    try:
        rating = int(message.text)
        if rating < 1 or rating > 10:
            raise ValueError
    except ValueError:
        logging.warning(f"Пользователь {user_id} ввёл некорректную оценку: {message.text}")
        await message.answer("Некорректный ввод. Введите число от 1 до 10.")
        return

    user_data = await state.get_data()
    game_id = user_data.get("game_id")
    
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()

    if user_record:
        real_user_id = user_record[0]

        cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
        game_record = cursor.fetchone()
        game_title = game_record[0]

        cursor.execute("""
            INSERT INTO rated_games (user_id, game_id, rating) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id, game_id) 
            DO UPDATE SET rating = EXCLUDED.rating;
        """, (real_user_id, game_id, rating))

        conn.commit()
        conn.close()

        await message.answer(f"Вы оценили игру {game_title} на {rating}/10.")
        logging.info(f"Пользователь {user_id} оценил игру {game_title} (ID {game_id}) на {rating}/10")
        update_recommendations(user_id)
    else:
        conn.close()

    await state.clear()

@router.callback_query(lambda c: c.data.startswith("not_interested_"))
async def mark_not_interested(callback: CallbackQuery):
    """ Добавляет игру в список неинтересных пользователю """
    game_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} добавляет в неинтересные игру (ID {game_id})")

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM not_interested_games WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s) AND game_id = %s",
        (user_id, game_id))
    already_not_interested = cursor.fetchone()

    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
    game_record = cursor.fetchone()
    game_title = game_record[0]

    if already_not_interested:
        logging.info(f"Пользователь {user_id} пытался добавить в неинтересные уже ранее добавленную игру: {game_title}")
        await callback.message.answer(f"❌ Игра {game_title} уже помечена как неинтересная!")
        conn.close()
        return

    cursor.execute(
        "INSERT INTO not_interested_games (user_id, game_id) VALUES ((SELECT id FROM users WHERE telegram_id = %s), %s)",
        (user_id, game_id))
    conn.commit()
    conn.close()

    logging.info(f"Игра {game_title} добавлена в неинтересные пользователем {user_id}")
    await callback.message.answer(f"✅ Игра {game_title} больше не будет вам рекомендоваться!")
    update_recommendations(user_id)

