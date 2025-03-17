import psycopg2
import datetime
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

PLATFORM_MAPPING = {
    "PlayStation 5": "PS5",
    "PlayStation 4": "PS4",
    "PlayStation 3": "PS3",
    "Xbox Series X/S": "XBOX SERIES X/S",
    "Xbox One": "XBOX ONE",
    "Xbox 360": "XBOX 360",
    "PC": "PC",
    "Nintendo Switch": "Nintendo Switch"
}


def connect_db():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )


def save_survey(telegram_id, platform, genre, favorite_games):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (telegram_id, platform, genre, favorite_games)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE 
        SET platform = EXCLUDED.platform, 
            genre = EXCLUDED.genre, 
            favorite_games = EXCLUDED.favorite_games;
    """, (telegram_id, platform, genre, favorite_games))

    conn.commit()
    conn.close()

def update_user_settings(user_id, **kwargs):
    """Обновляет настройки рекомендаций пользователя в БД."""
    conn = connect_db()
    cursor = conn.cursor()

    # Проверяем, существует ли пользователь
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False  # Пользователь не найден

    real_user_id = user_record[0]

    # Формируем запрос с обновлением только тех параметров, которые переданы
    update_fields = []
    values = []

    allowed_params = {"rec_count": "recommendation_count", "notif_freq": "notification_frequency", "notif_count": "notification_count"}

    for key, value in kwargs.items():
        if key in allowed_params:
            update_fields.append(f"{allowed_params[key]} = %s")
            values.append(value)

    if update_fields:
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
        values.append(real_user_id)
        cursor.execute(query, tuple(values))
        conn.commit()

    conn.close()
    return True  # Успешно обновлено



def user_exists(telegram_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM users WHERE telegram_id = %s LIMIT 1;", (telegram_id,))
    exists = cursor.fetchone() is not None

    conn.close()
    return exists


def get_user_profile(telegram_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT platform, genre, favorite_games, recommendation_count, notification_frequency, notification_count
        FROM users
        WHERE telegram_id = %s;
    """, (telegram_id,))

    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        return {
            "platform": user_data[0],
            "genre": user_data[1],
            "favorite_games": user_data[2],
            "rec_count": user_data[3],
            "notif_freq": user_data[4],
            "notif_count": user_data[5]
        }
    return None

def get_rated_games(user_id):
    """Получает список всех оценённых игр пользователя."""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя в БД
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT g.id, g.title, r.rating  
        FROM rated_games r
        JOIN games g ON r.game_id = g.id
        WHERE r.user_id = %s
        ORDER BY r.rating DESC;
    """, (real_user_id,))

    games = cursor.fetchall()
    conn.close()

    return games  # Вернёт список кортежей (game_id, game_title, rating)


def update_game_rating(user_id, game_id, new_rating):
    """Обновляет оценку игры в базе данных."""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя в БД
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False  # Пользователь не найден

    real_user_id = user_record[0]

    # Обновляем оценку
    cursor.execute("""
        UPDATE rated_games
        SET rating = %s
        WHERE user_id = %s AND game_id = %s;
    """, (new_rating, real_user_id, game_id))

    conn.commit()
    conn.close()
    return True


def remove_game_rating(user_id, game_id):
    """Удаляет оценку игры из базы данных."""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя в БД
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False  # Пользователь не найден

    real_user_id = user_record[0]

    # Удаляем оценку игры
    cursor.execute("""
        DELETE FROM rated_games
        WHERE user_id = %s AND game_id = %s;
    """, (real_user_id, game_id))

    conn.commit()
    conn.close()
    return True

def get_favorite_games(user_id):
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT g.id, g.title 
        FROM favorite_games f
        JOIN games g ON f.game_id = g.id
        WHERE f.user_id = %s
    """, (real_user_id,))

    games = cursor.fetchall()  # [(game_id, title), (game_id, title), ...]
    conn.close()

    return games


def remove_favorite_game(user_id, game_id):
    """Удаляет игру из избранного по game_id"""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False  # Если пользователя нет, прерываем удаление

    real_user_id = user_record[0]

    # Удаляем игру
    cursor.execute("""
        DELETE FROM favorite_games
        WHERE user_id = %s AND game_id = %s
    """, (real_user_id, game_id))

    conn.commit()
    conn.close()
    return True  # Успешное удаление


def get_not_interested_games(user_id):
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя в БД
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        return []

    real_user_id = user_record[0]

    # Получаем ID и название игры
    cursor.execute("""
        SELECT g.id, g.title 
        FROM not_interested_games n
        JOIN games g ON n.game_id = g.id
        WHERE n.user_id = %s
    """, (real_user_id,))

    games = cursor.fetchall()
    conn.close()

    return games  # Теперь каждая запись: (id, title)


def remove_not_interested_game(user_id, game_id):
    """Удаляет оценку игры из базы данных."""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя в БД
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False  # Пользователь не найден

    real_user_id = user_record[0]

    # Удаляем оценку игры
    cursor.execute("""
        DELETE FROM not_interested_games
        WHERE user_id = %s AND game_id = %s;
    """, (real_user_id, game_id))

    conn.commit()
    conn.close()
    return True


def get_recommendation_candidates(user_id):
    """Возвращает список ID игр, которые могут быть рекомендованы пользователю"""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя, его жанры и платформы
    cursor.execute("SELECT id, genre, platform FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]
    genre = user_record[1]
    platform = user_record[2]

    # Преобразуем жанры и платформы в список
    genre_list = genre.split(",") if isinstance(genre, str) else genre
    platform_list = platform.split(",") if isinstance(platform, str) else platform

    # Приводим платформы к нужному формату
    platform_list = [PLATFORM_MAPPING.get(p.strip(), p.strip()) for p in platform_list]

    # Поиск игр
    query = """
        SELECT g.id 
        FROM games g
        LEFT JOIN rated_games r ON g.id = r.game_id AND r.user_id = %s
        LEFT JOIN favorite_games f ON g.id = f.game_id AND f.user_id = %s
        LEFT JOIN not_interested_games n ON g.id = n.game_id AND n.user_id = %s
        LEFT JOIN recommendations rec ON g.id = rec.game_id AND rec.user_id = %s
        LEFT JOIN viewed_games v ON g.id = v.game_id AND v.user_id = %s
        LEFT JOIN game_genres gg ON g.id = gg.game_id
        LEFT JOIN genres gen ON gg.genre_id = gen.id
        LEFT JOIN game_platforms gp ON g.id = gp.game_id
        LEFT JOIN platforms p ON gp.platform_id = p.id
        WHERE r.game_id IS NULL  
        AND f.game_id IS NULL    
        AND n.game_id IS NULL    
        AND rec.game_id IS NULL
        AND v.game_id IS NULL  
    """
    params = [real_user_id, real_user_id, real_user_id, real_user_id, real_user_id]

    if genre_list:
        query += " AND gen.name = ANY(%s)"
        params.append(genre_list)

    if platform_list:
        query += " AND p.name = ANY(%s)"
        params.append(platform_list)

    query += " ORDER BY RANDOM() LIMIT 20;"

    print("Params:", params)

    cursor.execute(query, params)
    game_ids = [row[0] for row in cursor.fetchall()]
    print("Найденные игры:", game_ids)  # <-- Отладка

    if game_ids:
        add_recommendations(user_id, game_ids)

    conn.close()
    return game_ids

def add_recommendations(user_id, game_ids):
    """Добавляет список игр в рекомендации пользователя"""
    if not game_ids:
        return

    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]

    # Вставка данных
    query = """
        INSERT INTO recommendations (user_id, game_id)
        VALUES %s
        ON CONFLICT (user_id, game_id) DO NOTHING;
    """
    values = [(real_user_id, game_id) for game_id in game_ids]
    print(f"Добавляем в рекомендации: {game_ids}")  # <-- Отладка

    from psycopg2.extras import execute_values
    execute_values(cursor, query, values)

    conn.commit()
    conn.close()

def update_recommendations(user_id):
    """Обновляет список рекомендованных игр для пользователя."""
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]

    # Удаляем старые рекомендации
    cursor.execute("DELETE FROM recommendations WHERE user_id = %s", (real_user_id,))
    conn.commit()

    print(f"Удалены старые рекомендации для пользователя {user_id}")  # <-- Отладка

    # Получаем и добавляем новые рекомендации
    new_game_ids = get_recommendation_candidates(user_id)

    if new_game_ids:
        add_recommendations(user_id, new_game_ids)
        print(f"Добавлены новые рекомендации для пользователя {user_id}: {new_game_ids}")  # <-- Отладка
    else:
        print(f"Не удалось найти новые рекомендации для пользователя {user_id}")  # <-- Отладка

    conn.close()

def get_recommendations(user_id):
    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id, recommendation_count FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id, recommendation_count = user_record

    cursor.execute("""
                SELECT
                    g.id, 
                    g.title, 
                    TO_CHAR(g.release_date, 'DD.MM.YYYY') AS release_date, 
                    COALESCE(string_agg(DISTINCT ge.name, ', '), 'Не указано') AS genre,
                    COALESCE(string_agg(DISTINCT pl.name, ', '), 'Не указано') AS platforms,
                    g.metascore, 
                    g.cover_url
                FROM recommendations r
                JOIN games g ON r.game_id = g.id
                LEFT JOIN game_genres gg ON g.id = gg.game_id
                LEFT JOIN genres ge ON gg.genre_id = ge.id
                LEFT JOIN game_platforms gp ON g.id = gp.game_id
                LEFT JOIN platforms pl ON gp.platform_id = pl.id
                WHERE r.user_id = %s
                GROUP BY g.id
                LIMIT %s
            """, (real_user_id, recommendation_count))
    games = cursor.fetchall()

    conn.close()
    return games


def add_to_viewed_games(user_id, game_ids):
    """Добавляет игры в таблицу viewed_games с текущим временем."""
    if not game_ids:
        return

    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]
    now = datetime.datetime.now()

    query = """
        INSERT INTO viewed_games (user_id, game_id, viewed_at)
        VALUES %s
        ON CONFLICT (user_id, game_id) DO NOTHING;
    """

    from psycopg2.extras import execute_values
    values = [(real_user_id, game_id, now) for game_id in game_ids]
    execute_values(cursor, query, values)

    conn.commit()
    conn.close()

def remove_from_recommendations(user_id, game_ids):
    """Удаляет игры из таблицы recommendations после показа."""
    if not game_ids:
        return

    conn = connect_db()
    cursor = conn.cursor()

    # Получаем ID пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]

    query = """
        DELETE FROM recommendations
        WHERE user_id = %s AND game_id = ANY(%s);
    """
    cursor.execute(query, (real_user_id, game_ids))

    conn.commit()
    conn.close()

def update_last_activity(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_activity = NOW() WHERE telegram_id = %s", (user_id,))
    conn.commit()
    conn.close()


def update_user_state(user_id, state: str):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET current_state = %s WHERE telegram_id = %s", (state, user_id))
    conn.commit()
    conn.close()
