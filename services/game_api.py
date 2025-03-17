import aiohttp
import asyncio
import logging
from config import RAWG_API_KEY
from services.game_db import GameDatabase  # Подключаем нашу работу с БД

# Словарь платформ (RAWG API → наша БД)
PLATFORMS = {
    "PC": 4,
    "PS5": 187,
    "PS4": 18,
    "PS3": 16,
    "Nintendo Switch": 7,
    "XBOX 360": 14,
    "XBOX ONE": 1,
    "XBOX SERIES X/S": 186
}

BASE_URL = "https://api.rawg.io/api/games"

async def fetch_games(session, platform_id, page):
    """Получает список игр с API RAWG."""
    params = {
        "key": RAWG_API_KEY,
        "platforms": platform_id,
        "page": page,
        "page_size": 20  # Максимум 20 игр за раз
    }

    async with session.get(BASE_URL, params=params) as response:
        if response.status != 200:
            logging.error(f"Ошибка запроса: {response.status}")
            return None
        return await response.json()

async def get_all_games():
    """Загружает игры по всем платформам и сохраняет в БД."""
    db = GameDatabase()
    async with aiohttp.ClientSession() as session:
        for platform, platform_id in PLATFORMS.items():
            print(f"🔄 Загружаем игры для {platform}...")
            game_count = 0
            page = 1

            while game_count < 4500:
                data = await fetch_games(session, platform_id, page)
                if not data or "results" not in data:
                    break  # Если данные не пришли, прерываем

                for game in data["results"]:
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

                    # Привязываем игру к платформам
                    db.insert_platform(platform)
                    db.link_game_platform(game["name"], platform)

                    game_count += 1
                    if game_count >= 4500:
                        break  # Достигли лимита

                page += 1  # Переходим на следующую страницу

    print("✅ База данных обновлена!")

async def fetch_game_details(title: str):
    """Ищет игру по названию, получает её ID и загружает подробную информацию."""
    async with aiohttp.ClientSession() as session:
        # 1. Поиск игры по названию
        search_url = f"https://api.rawg.io/api/games?key={RAWG_API_KEY}&search={title}"
        async with session.get(search_url) as search_response:
            if search_response.status != 200:
                logging.error(f"Ошибка при поиске игры: {search_response.status}")
                return None
            search_data = await search_response.json()

            if not search_data.get("results"):
                logging.warning(f"Игра '{title}' не найдена.")
                return None

            # Берём первый результат
            game_id = search_data["results"][0]["id"]

        # 2. Запрашиваем данные по ID
        game_url = f"https://api.rawg.io/api/games/{game_id}?key={RAWG_API_KEY}"
        async with session.get(game_url) as response:
            if response.status != 200:
                logging.error(f"Ошибка при получении данных: {response.status}")
                return None
            data = await response.json()

    # Обрабатываем результат (тут нет "results", это уже один объект)
    return {
        "developer": data.get("developers", [{"name": "Не указано"}])[0]["name"],
        "publisher": data.get("publishers", [{"name": "Не указано"}])[0]["name"],
        "slug": data.get("slug"),
    }