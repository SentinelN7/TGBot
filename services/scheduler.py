from datetime import datetime, timedelta
from aiogram.types import Message, Chat, User
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from services.database import connect_db, update_user_state
from handlers.menu import show_menu


async def check_inactive_users(bot: Bot, dp: Dispatcher):
    conn = connect_db()
    cursor = conn.cursor()

    # Проверяем пользователей, которые неактивны более 60 минут и не в главном меню
    inactive_threshold = datetime.now() - timedelta(minutes=60)
    cursor.execute("""
        SELECT telegram_id FROM users 
        WHERE last_activity < %s AND current_state != 'Main Menu'
    """, (inactive_threshold,))

    inactive_users = cursor.fetchall()
    conn.close()

    for user in inactive_users:
        user_id = user[0]

        # Получаем FSMContext для пользователя
        state = dp.fsm.get_context(bot, user_id, user_id)

        # Очищаем состояние пользователя
        await state.clear()

        # Обновляем состояние в БД
        update_user_state(user_id, "Main Menu")

        # Отправляем сообщение пользователю
        await bot.send_message(user_id, "Вы были неактивны более 60 минут. Возвращаем вас в главное меню.")

        # Создаём корректный "фейковый" Message
        fake_message = Message(
            message_id=0,
            date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="User"),
            text="🏠 Главное меню"
        )

        await show_menu(fake_message, bot)
