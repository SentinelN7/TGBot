import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from config import RAWG_API_KEY
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.game_api import fetch_games
from services.game_db import GameDatabase

db = GameDatabase()
scheduler = AsyncIOScheduler()

BASE_URL = "https://api.rawg.io/api/games"

async def fetch_games_by_date(session, start_date, end_date, page=1):
    """Получает список игр, вышедших в заданный период."""
    params = {
        "key": RAWG_API_KEY,
        "dates": f"{start_date},{end_date}",
        "ordering": "-released",
        "page": page,
        "page_size": 20
    }

    async with session.get(BASE_URL, params=params) as response:
        if response.status != 200:
            print(f"Ошибка запроса: {response.status}")
            return None
        return await response.json()

async def update_games():
    """Добавляет новые игры в базу данных (пропуская игры без платформ)."""
    db = GameDatabase()
    async with aiohttp.ClientSession() as session:
        print("🔄 Загружаем игры с 24 февраля 2025 по 12 марта 2025...")
        page = 1

        while True:
            data = await fetch_games_by_date(session, "2025-03-13", "2025-03-23", page)
            if not data or "results" not in data:
                break

            for game in data["results"]:
                platforms = game.get("platforms")

                if not platforms:
                    print(f"⚠ Пропущена игра '{game['name']}' (нет данных о платформах)")
                    continue  # Пропускаем игру без платформ

                db.insert_game(
                    title=game["name"],
                    release_date=game.get("released"),
                    metascore=game.get("metacritic"),
                    cover_url=game.get("background_image")
                )

                # Привязываем игру к жанрам
                for genre in game.get("genres", []):
                    db.insert_genre(genre["name"])
                    db.link_game_genre(game["name"], genre["name"])

                # Привязываем игру к платформам (теперь гарантировано есть)
                for platform in platforms:
                    db.insert_platform(platform["platform"]["name"])
                    db.link_game_platform(game["name"], platform["platform"]["name"])

            if "next" not in data or not data["next"]:
                break  # Если больше страниц нет, завершаем

            page += 1  # Переход на следующую страницу

        print("✅ Игры за 2025 год добавлены!")

if __name__ == "__main__":
    asyncio.run(update_games())