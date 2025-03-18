from datetime import datetime, timedelta
from aiogram.types import Message, Chat, User
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from services.database import *
from handlers.menu import show_menu
from services import game_card
from services.game_api import fetch_games
from services.game_db import GameDatabase

db = GameDatabase()

async def check_inactive_users(bot: Bot, dp: Dispatcher):
    conn = connect_db()
    cursor = conn.cursor()

    inactive_threshold = datetime.datetime.now() - timedelta(hours=1)
    cursor.execute("""
        SELECT telegram_id FROM users 
        WHERE last_activity < %s AND current_state != 'Main Menu'
    """, (inactive_threshold,))

    inactive_users = cursor.fetchall()
    conn.close()

    for user in inactive_users:
        user_id = user[0]

        state = dp.fsm.get_context(bot, user_id, user_id)

        await state.clear()

        update_user_state(user_id, "Main Menu")

        await bot.send_message(user_id, "Вы были неактивны более 60 минут. Возвращаем вас в главное меню.")

        fake_message = Message(
            message_id=0,
            date=datetime.datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="User"),
            text="🏠 Главное меню"
        )

        await show_menu(fake_message, bot)


async def send_scheduled_recommendations(bot):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT telegram_id, last_notification FROM users 
        WHERE notification_frequency != 'never' AND current_state = 'Main Menu'
    """)
    users = cursor.fetchall()

    current_time = datetime.now()

    for user_id, last_notification in users:
        user_settings = get_user_profile(user_id)
        notif_freq = user_settings.get("notif_freq", 4)
        notif_count = user_settings.get("notif_count", 5)

        if isinstance(last_notification, str):
            last_notification = datetime.strptime(last_notif, "%Y-%m-%d %H:%M:%S")
        elif last_notification is None:
            last_notification = datetime.min  # Если уведомлений не было, отправим первое сразу

        # Определяем, когда можно отправлять уведомления
        if notif_freq == "daily":
            delta = timedelta(days=1)
        elif notif_freq == "3days":
            delta = timedelta(days=3)
        elif notif_freq == "weekly":
            delta = timedelta(weeks=1)
        else:
            continue

        if (current_time - last_notification) < delta:
            continue  # Уведомление пока не должно отправляться

        recommended_games = get_recommendations(user_id, notif_count)
        if len(recommended_games) < notif_count:
            update_recommendations(user_id)
            recommended_games = get_recommendations(user_id, notif_count)

        game_ids = [game[0] for game in recommended_games]

        for game_id in game_ids:
            await game_card.show_game_bot(user_id, game_id, bot)

        add_to_viewed_games(user_id, game_ids)
        remove_from_recommendations(user_id, game_ids)

        cursor.execute("UPDATE users SET last_notification = %s WHERE telegram_id = %s", (current_time, user_id))
        conn.commit()

    conn.close()

async def update_game_database():
    today = datetime.today().date()
    week_ago = today - timedelta(days=7)

    async for platform_name, platform_id in db.get_all_platforms():
        page = 1
        while True:
            data = await fetch_games(platform_id, page)
            if not data or "results" not in data:
                break

            for game in data["results"]:
                release_date = game.get("released")
                genres = game.get("genres", [])

                if not release_date or not genres:
                    continue

                release_date = datetime.strptime(release_date, "%Y-%m-%d").date()
                if release_date < week_ago or release_date > today:
                    continue

                db.insert_game(
                    title=game["name"],
                    release_date=release_date,
                    metascore=game.get("metacritic"),
                    cover_url=game.get("background_image")
                )

                for genre in genres:
                    db.insert_genre(genre["name"])
                    db.link_game_genre(game["name"], genre["name"])

                db.insert_platform(platform_name)
                db.link_game_platform(game["name"], platform_name)

            page += 1


async def clear_viewed_games():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("TRUNCATE TABLE viewed_games")
    conn.commit()
    conn.close()

    print("✅ Таблица viewed_games очищена.")
