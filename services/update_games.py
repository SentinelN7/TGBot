import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.game_api import fetch_games
from services.game_db import GameDatabase

db = GameDatabase()
scheduler = AsyncIOScheduler()

async def update_game_database():
    """Добавляет в базу игры, вышедшие за последние 7 дней."""
    logging.info("🔄 Запуск обновления базы игр...")
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
                    continue  # Пропускаем игры без даты выхода или жанра

                release_date = datetime.strptime(release_date, "%Y-%m-%d").date()
                if release_date < week_ago or release_date > today:
                    continue  # Пропускаем игры, вышедшие раньше 7 дней назад или ещё не вышедшие

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

            page += 1  # Переход к следующей странице

    logging.info("✅ Обновление базы завершено!")


async def start_scheduled_updates():
    scheduler.add_job(update_game_database, 'interval', days=7)
    scheduler.start()

