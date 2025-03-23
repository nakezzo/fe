import logging
import json
import phonenumbers
from aiogram import Router
from aiogram import types, F
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import sqlite3
from datetime import datetime, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.formatting import Text
import os
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
import zipfile
import rarfile
import mimetypes
from telethon import errors
from phonenumbers import geocoder
from telethon import TelegramClient
import asyncio
from currency_converter import CurrencyConverter

API_TOKEN = '7950201257:AAFT2sOTpwCYCw9DEG-1EGX8eY0ASiqKziM'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
ADMIN_IDS = [5978945040]
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
c = CurrencyConverter()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    language TEXT,
    currency TEXT,
    registration_date TEXT,
    last_login TEXT,
    subscription_active INTEGER DEFAULT 0,
    subscription_expiry TEXT,
    quantity INTEGER DEFAULT 0, 
    sold_accounts INTEGER DEFAULT 0,
    notification_preference TEXT,
    cryptobot_id TEXT,
    lzt_link TEXT,
    agreed_to_terms INTEGER DEFAULT 0
)
''')
conn.commit()

cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()
column_names = [column[1] for column in columns]


class AdminStates(StatesGroup):
    WAITING_FOR_USER_ID_AND_AMOUNT = State()
    WAITING_FOR_USER_ID_FOR_SUBSCRIPTION = State()
    WAITING_FOR_COUNTRY_CODE_AND_PRICE = State()
    WAITING_FOR_USER_ID_AND_MESSAGE = State()
    WAITING_FOR_ANNOUNCEMENT = State()

class WalletStates(StatesGroup):
    waiting_for_cryptobot_id = State()
    waiting_for_lzt_link = State()
    waiting_for_profile_name = State()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def convert_currency(price_rub, currency):

    if currency == "usd":
        return round(c.convert(price_rub, 'RUB', 'USD'), 2)
    return price_rub

def get_notification_preference(user_id):

    try:
        cursor.execute('SELECT notification_preference FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении предпочтений уведомлений: {e}")
        return None

def get_user(user_id):
    try:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            return {
                "user_id": result[0],
                "balance": result[1],
                "language": result[2],
                "currency": result[3],
                "registration_date": result[4],
                "last_login": result[5],
                "subscription_active": result[6],
                "subscription_expiry": result[7],
                "quantity": result[8],
                "sold_accounts": result[9],
                "agreed_to_terms": result[10]
            }
        return None
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении пользователя: {e}")
        return None

@dp.message(Command('send_message'))
async def send_message_command(message: types.Message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите ID пользователя и сообщение через пробел (например, `123456789 Привет!`):")

async def console_input():
    while True:
        user_input = await asyncio.get_event_loop().run_in_executor(None, input, "Введите команду (или 'exit' для выхода): ")

        if user_input.lower() == 'exit':
            break

        await handle_console_command(user_input)

async def handle_console_command(command: str):
    try:
        if command.startswith("send"):
            parts = command.split(maxsplit=2)
            if len(parts) < 3:
                print("Некорректный формат команды. Используйте: send <user_id> <message>")
                return

            user_id = int(parts[1])
            message_text = parts[2]

            await bot.send_message(user_id, message_text)
            print(f"Сообщение отправлено пользователю {user_id}.")
        else:
            print("Неизвестная команда.")
    except Exception as e:
        print(f"Ошибка: {e}")


def get_prices(category):
    try:
        cursor.execute('SELECT * FROM pricing WHERE category = ?', (category,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении цен: {e}")
        return []

def add_user(user_id, language=None, currency=None):
    try:
        cursor.execute('''
        INSERT INTO users (user_id, language, currency, registration_date, last_login, agreed_to_terms)
        VALUES (?, ?, ?, ?, ?, 0)
        ''', (user_id, language, currency, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при добавлении пользователя: {e}")

def update_user(user_id, language=None, currency=None):
    try:
        if language:
            cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
        if currency:
            cursor.execute('UPDATE users SET currency = ? WHERE user_id = ?', (currency, user_id))
        cursor.execute('UPDATE users SET last_login = ? WHERE user_id = ?', (datetime.now().isoformat(), user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении пользователя: {e}")

def update_balance(user_id, amount):
    try:
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (amount, int(user_id)))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при изменении баланса: {e}")

def activate_subscription(user_id, duration_days=30):
    try:
        expiry_date = (datetime.now() + timedelta(days=duration_days)).isoformat()
        cursor.execute('''
        UPDATE users
        SET subscription_active = 1, subscription_expiry = ?
        WHERE user_id = ?
        ''', (expiry_date, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при активации подписки: {e}")

def deactivate_subscription(user_id):
    try:
        cursor.execute('''
        UPDATE users
        SET subscription_active = 0, subscription_expiry = NULL
        WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при деактивации подписки: {e}")

def get_subscription_info(user_id):
    try:
        cursor.execute('SELECT subscription_active, subscription_expiry FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            active, expiry = result
            if active == 1 and expiry:
                expiry_date = datetime.fromisoformat(expiry)
                return {
                    "active": expiry_date > datetime.now(),
                    "expiry_date": expiry_date
                }
        return {"active": False, "expiry_date": None}
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении информации о подписке: {e}")
        return {"active": False, "expiry_date": None}

def update_quantity(user_id, quantity):
    try:
        cursor.execute('UPDATE users SET quantity = ? WHERE user_id = ?', (quantity, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении количества аккаунтов: {e}")

def update_sold_accounts(user_id, amount):
    try:
        cursor.execute('UPDATE users SET sold_accounts = ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении суммы проданных аккаунтов: {e}")

def update_price(country_code: str, price_with_delay: int, price_without_delay: int):
    try:
        cursor.execute('''
        UPDATE pricing
        SET price_with_delay = ?, price_without_delay = ?
        WHERE country_code = ?
        ''', (price_with_delay, price_without_delay, country_code))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении цены: {e}")

def save_cryptobot_id(user_id: int, cryptobot_id: str):

    try:
        cursor.execute('UPDATE users SET cryptobot_id = ? WHERE user_id = ?', (cryptobot_id, user_id))
        conn.commit()
        logging.info(f"Telegram ID для Cryptobot сохранен для пользователя {user_id}.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при сохранении Telegram ID для Cryptobot: {e}")

def save_lzt_link(user_id: int, lzt_link: str):

    try:
        cursor.execute('UPDATE users SET lzt_link = ? WHERE user_id = ?', (lzt_link, user_id))
        conn.commit()
        logging.info(f"Ссылка на LZT профиль сохранена для пользователя {user_id}.")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при сохранении ссылки на LZT профиль: {e}")


language_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="English 🇬🇧"), KeyboardButton(text="Русский 🇷🇺")]
    ],
    resize_keyboard=True
)

currency_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="USD 🇺🇸"), KeyboardButton(text="Рубли 🇷🇺")]
    ],
    resize_keyboard=True
)

main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛒 Продать аккаунты"), KeyboardButton(text="💼 Профиль"), KeyboardButton(text="📈 Цены")],
        [KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="🔌 API"),
         KeyboardButton(text="🤝 Сотрудничество и Реферальные программы")],
        [KeyboardButton(text="📖 Условия работы"), KeyboardButton(text="💞 Отзывы")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Пользователи")],
        [KeyboardButton(text="💳 Изменить баланс")],
        [KeyboardButton(text="🔓 Активировать подписку")],
        [KeyboardButton(text="🔒 Деактивировать подписку")],
        [KeyboardButton(text="💵 Изменить цены")],
        [KeyboardButton(text="📨 Отправить сообщение")],
        [KeyboardButton(text="📢 Сделать объявление")],
        [KeyboardButton(text="🔙 В главное меню")]
    ],
    resize_keyboard=True
)
@dp.message(lambda message: message.text == "📨 Отправить сообщение")
async def send_message_admin(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите ID пользователя и сообщение через пробел (например, `123456789 Привет!`):")
    await state.set_state(AdminStates.WAITING_FOR_USER_ID_AND_MESSAGE)

@dp.message(AdminStates.WAITING_FOR_USER_ID_AND_MESSAGE)
async def process_send_message(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Некорректный ввод. Используйте формат: `ID_пользователя сообщение`.")
            return

        user_id = int(parts[0])
        message_text = parts[1]

        await bot.send_message(user_id, message_text)
        await message.answer(f"Сообщение отправлено пользователю {user_id}.")
    except ValueError:
        await message.answer("Некорректный ID пользователя. Введите число.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()
@dp.message(lambda message: message.text == "📢 Сделать объявление")
async def make_announcement(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите текст объявления:")
    await state.set_state(AdminStates.WAITING_FOR_ANNOUNCEMENT)

@dp.message(AdminStates.WAITING_FOR_ANNOUNCEMENT)
async def process_announcement(message: types.Message, state: FSMContext):
    try:
        announcement_text = message.text

        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()

        for user in users:
            user_id = user[0]
            try:
                await bot.send_message(user_id, announcement_text)
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        await message.answer("Объявление отправлено всем пользователям.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()
@dp.message(lambda message: message.text == "📊 Пользователи")
async def show_users_statistics(message: types.Message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    total_users = get_total_users()
    active_subscriptions = get_active_subscriptions()
    total_balance = get_total_balance()


    text = f"""
<b>📊 Статистика пользователей</b>
━━━━━━━━━━━━━━━━━━
<b>👤 Всего пользователей:</b> {total_users}
<b>👑 Активных подписок:</b> {active_subscriptions}
<b>💰 Общий баланс:</b> {total_balance} RUB
━━━━━━━━━━━━━━━━━━
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Список пользователей", callback_data="user_list")],
        [InlineKeyboardButton(text="👑 Активные подписки", callback_data="active_subscriptions_list")],
        [InlineKeyboardButton(text="💰 Топ по балансу", callback_data="top_balance")]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

def get_total_users():
    cursor.execute('SELECT COUNT(*) FROM users')
    return cursor.fetchone()[0]

def get_active_subscriptions():
    cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_active = 1')
    return cursor.fetchone()[0]

def get_total_balance():
    cursor.execute('SELECT SUM(balance) FROM users')
    return cursor.fetchone()[0] or 0

@dp.callback_query(lambda call: call.data == "user_list")
async def handle_user_list(call: types.CallbackQuery):
    await call.answer("Загрузка списка пользователей...")

    cursor.execute('SELECT user_id, balance, subscription_active FROM users')
    users = cursor.fetchall()

    text = "<b>👤 Список пользователей:</b>\n"
    for user in users:
        user_id, balance, subscription_active = user
        text += f"├─ ID: {user_id}, Баланс: {balance} RUB, Подписка: {'Активна' if subscription_active else 'Неактивна'}\n"

    await call.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(lambda call: call.data == "active_subscriptions_list")
async def handle_active_subscriptions(call: types.CallbackQuery):
    """Обработчик для кнопки 'Активные подписки'."""
    await call.answer("Загрузка списка активных подписок...")

    cursor.execute('SELECT user_id, balance FROM users WHERE subscription_active = 1')
    users = cursor.fetchall()

    text = "<b>👑 Пользователи с активными подписками:</b>\n"
    for user in users:
        user_id, balance = user
        text += f"├─ ID: {user_id}, Баланс: {balance} RUB\n"

    await call.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(lambda call: call.data == "top_balance")
async def handle_top_balance(call: types.CallbackQuery):
    """Обработчик для кнопки 'Топ по балансу'."""
    await call.answer("Загрузка топа по балансу...")

    cursor.execute('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10')
    users = cursor.fetchall()

    text = "<b>💰 Топ-10 пользователей по балансу:</b>\n"
    for i, user in enumerate(users, start=1):
        user_id, balance = user
        text += f"{i}. ID: {user_id}, Баланс: {balance} RUB\n"

    await call.message.edit_text(text, parse_mode="HTML")
def create_prices_keyboard(active_category=None):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    categories = [
        ("Стандарт с отлежкой", "standard_with_delay"),
        ("Стандарт без отлежки", "standard_without_delay"),
        ("Seller+ с отлежкой", "seller_plus_with_delay"),
        ("Seller+ без отлежки", "seller_plus_without_delay")
    ]

    for text, callback_data in categories:
        if callback_data == active_category:
            text = f"• {text} •"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    return keyboard

@dp.message(Command('start'))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    if user and user.get("language"):
        await message.answer("👋", reply_markup=main_menu_keyboard)
    else:
        await message.answer(
            get_text(user_id, "welcome"),
            reply_markup=create_language_keyboard()
        )
        if not user:
            add_user(user_id)

@dp.message(Command('admin'))
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Админ-панель", reply_markup=admin_keyboard)

@dp.message(lambda message: message.text == "💳 Изменить баланс")
async def change_balance(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите ID пользователя и сумму через пробел (например, `123456789 1000`):")
    await state.set_state(AdminStates.WAITING_FOR_USER_ID_AND_AMOUNT)

@dp.message(AdminStates.WAITING_FOR_USER_ID_AND_AMOUNT)
async def process_balance_input(message: types.Message, state: FSMContext):
    try:
        user_id, amount = map(int, message.text.split())
        update_balance(user_id, amount)
        await message.answer(f"Баланс пользователя {user_id} изменен на {amount}.")
    except ValueError:
        await message.answer("Некорректный ввод. Используйте формат: `ID_пользователя сумма`.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()

@dp.message(lambda message: message.text == "🔓 Активировать подписку")
async def activate_subscription_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите ID пользователя для активации подписки:")
    await state.set_state(AdminStates.WAITING_FOR_USER_ID_FOR_SUBSCRIPTION)

@dp.message(AdminStates.WAITING_FOR_USER_ID_FOR_SUBSCRIPTION)
async def process_activate_subscription(message: types.Message, state: FSMContext):
    try:
        target_user_id = int(message.text)
        activate_subscription(target_user_id)
        await message.answer(f"Подписка для пользователя {target_user_id} активирована.")
    except ValueError:
        await message.answer("Некорректный ввод. Введите ID пользователя.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()

@dp.message(lambda message: message.text == "🔒 Деактивировать подписку")
async def deactivate_subscription_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите ID пользователя для деактивации подписки:")
    await state.set_state(AdminStates.WAITING_FOR_USER_ID_FOR_SUBSCRIPTION)

@dp.message(AdminStates.WAITING_FOR_USER_ID_FOR_SUBSCRIPTION)
async def process_deactivate_subscription(message: types.Message, state: FSMContext):
    try:
        target_user_id = int(message.text)
        deactivate_subscription(target_user_id)
        await message.answer(f"Подписка для пользователя {target_user_id} деактивирована.")
    except ValueError:
        await message.answer("Некорректный ввод. Введите ID пользователя.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()

@dp.message(lambda message: message.text == "💵 Изменить цены")
async def change_prices(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Введите код страны и новые цены через пробел (например, `RU 70 45`):")
    await state.set_state(AdminStates.WAITING_FOR_COUNTRY_CODE_AND_PRICE)

@dp.message(AdminStates.WAITING_FOR_COUNTRY_CODE_AND_PRICE)
async def process_price_change(message: types.Message, state: FSMContext):
    try:
        country_code, price_with_delay, price_without_delay = message.text.split()
        price_with_delay = int(price_with_delay)
        price_without_delay = int(price_without_delay)
        update_price(country_code, price_with_delay, price_without_delay)
        await message.answer(f"Цены для страны {country_code} обновлены: {price_with_delay}₽ с отлежкой, {price_without_delay}₽ без отлежки.")
    except ValueError:
        await message.answer("Некорректный ввод. Используйте формат: `код_страны цена_с_отлежкой цена_без_отлежки`.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()

def update_balance(user_id, amount):
    try:
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении баланса: {e}")

def get_user_currency(user_id):

    try:
        cursor.execute('SELECT currency FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return "rub"
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении валюты пользователя: {e}")
        return "rub"

def update_sold_accounts(user_id, amount):
    try:
        cursor.execute('UPDATE users SET sold_accounts = sold_accounts + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении количества аккаунтов: {e}")
@dp.message(lambda message: message.text == "🔙 В главное меню")
async def back_to_main_menu(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer("Возврат в главное меню.", reply_markup=main_menu_keyboard)

def create_agreement_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Согласен", callback_data="agree_terms")]
    ])
    return keyboard

with open("texts.json", "r", encoding="utf-8") as f:
    texts = json.load(f)

def get_text(user_id, key, **kwargs):
    user = get_user(user_id)
    language = user.get("language", "en")  # По умолчанию английский
    text = texts.get(language, {}).get(key, f"Text not found for key: {key}")
    return text.format(**kwargs)
@dp.message(lambda message: message.text == "English 🇬🇧")
async def language_english(message: types.Message):
    user_id = message.from_user.id
    update_user(user_id, language="en")
    await message.answer(get_text(user_id, "language_changed", language="English"), reply_markup=main_menu_keyboard)

@dp.message(lambda message: message.text == "Русский 🇷🇺")
async def language_russian(message: types.Message):
    user_id = message.from_user.id
    update_user(user_id, language="ru")
    await message.answer(get_text(user_id, "language_changed", language="Русский"), reply_markup=main_menu_keyboard)


@dp.message(lambda message: message.text == "USD 🇺🇸")
async def currency_usd(message: types.Message):
    user_id = message.from_user.id
    update_user(user_id, currency="usd")
    await message.answer("You selected USD 🇺🇸.", reply_markup=main_menu_keyboard)
    await message.answer(
        "📖 Terms of Service: [read](https://teletype.in/@cjsdkncvkjdsnkvcds/4O_vM0eBTAK).\n\n"
        "Please confirm that you agree to the terms of service:",
        parse_mode="Markdown",
        reply_markup=create_agreement_keyboard()
    )

@dp.message(lambda message: message.text == "Рубли 🇷🇺")
async def currency_rub(message: types.Message):
    user_id = message.from_user.id
    update_user(user_id, currency="rub")
    await message.answer("Вы выбрали рубли 🇷🇺.", reply_markup=main_menu_keyboard)

def load_prices_from_json(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"❌ Ошибка при загрузке JSON: {e}")
        return None

def get_country_by_phone(phone):
    try:
        if not phone.startswith("+"):
            phone = f"+{phone}"

        parsed_number = phonenumbers.parse(phone, None)

        country = geocoder.description_for_number(parsed_number, "en")
        return country
    except Exception as e:
        print(f"❌ Ошибка при определении страны: {e}")
        return None

def calculate_time_since_last_connect(last_connect_date):
    try:
        last_connect = datetime.strptime(last_connect_date, "%Y-%m-%dT%H:%M:%S%z")
        now = datetime.now(last_connect.tzinfo)
        time_diff = now - last_connect
        return time_diff
    except Exception as e:
        print(f"❌ Ошибка при расчёте времени: {e}")
        return None
def get_account_category(is_premium, last_connect_date):

    if last_connect_date:
        last_connect = datetime.fromisoformat(last_connect_date)
        time_diff = datetime.now(last_connect.tzinfo) - last_connect

        if time_diff > timedelta(hours=24):
            if is_premium:
                return "seller_plus_with_delay"
            else:
                return "standard_with_delay"
        else:
            if is_premium:
                return "seller_plus_without_delay"
            else:
                return "standard_without_delay"
    else:
        if is_premium:
            return "seller_plus_without_delay"
        else:
            return "standard_without_delay"

def get_price_for_country(country, prices_data):
    for region in prices_data.get("regions", []):
        for country_data in region.get("countries", []):
            if country_data.get("name") == country:
                return country_data.get("price")

    for region in prices_data.get("regions", []):
        for country_data in region.get("countries", []):
            if country_data.get("code") == "XX":
                return country_data.get("price")

    return None
async def check_sessions(session_files, json_files, extracted_dir):
    total_price = 0
    valid_accounts = []

    for session_file, json_file in zip(session_files, json_files):
        session_name = os.path.splitext(session_file)[0]
        json_path = os.path.join(extracted_dir, json_file)
        session_path = os.path.join(extracted_dir, session_file)

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)

            api_id = json_data.get("app_id")
            api_hash = json_data.get("app_hash")
            phone = json_data.get("phone")
            last_connect_date = json_data.get("last_connect_date")
            is_premium = json_data.get("is_premium", False)

            if not api_id or not api_hash:
                print(f"❌ Неверные данные в JSON {json_file}, пропускаем")
                continue

            client = TelegramClient(session_name, api_id, api_hash)
            await client.connect()

            if await client.is_user_authorized():
                print(f"✅ Сессия {session_name} работает")
                valid_accounts.append(session_name)
            else:
                print(f"❌ Сессия {session_name} не авторизована, пропускаем")
                continue

            await client.disconnect()

        except Exception as e:
            print(f"❌ Ошибка сессии {session_name}: {e}")
            continue

        finally:
            if session_name not in valid_accounts:
                if os.path.exists(json_path):
                    os.remove(json_path)
                if os.path.exists(session_path):
                    os.remove(session_path)

        await asyncio.sleep(5)

    return total_price, valid_accounts

def create_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_accounts")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_accounts")]
    ])
    return keyboard
@dp.message(F.document)
async def handle_document(message: types.Message):
    document = message.document
    file_name = document.file_name
    file_extension = file_name.split('.')[-1].lower() if '.' in file_name else None

    if file_extension not in ["zip", "rar"]:
        await message.answer("❌ Неподдерживаемый формат файла.")
        return

    if document.file_size > 20 * 1024 * 1024:
        await message.answer("❌ Размер файла превышает 20 МБ.")
        return

    await message.answer(f"✅ Файл принят. Расширение: {file_extension}")

    file_id = document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path

    await bot.download_file(file_path, file_name)
    await message.answer(f"📥 Файл сохранён: {file_name}")

    await process_archive(file_name, message)

import shutil

async def process_archive(file_name, message):
    user_id = message.from_user.id
    user_dir = f"accounts_{user_id}"

    try:
        os.makedirs(user_dir, exist_ok=True)

        extracted_dir = os.path.join(user_dir, "extracted")
        os.makedirs(extracted_dir, exist_ok=True)

        if file_name.endswith(".zip"):
            with zipfile.ZipFile(file_name, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)
                extracted_files = os.listdir(extracted_dir)
                print(f"Извлеченные файлы: {extracted_files}")
                await message.answer("📦 ZIP-архив успешно распакован.")
        elif file_name.endswith(".rar"):
            with rarfile.RarFile(file_name, 'r') as rar_ref:
                rar_ref.extractall(extracted_dir)
                extracted_files = os.listdir(extracted_dir)
                print(f"Извлеченные файлы: {extracted_files}")
                await message.answer("📦 RAR-архив успешно распакован.")

        session_files = [f for f in os.listdir(extracted_dir) if f.endswith(".session")]
        json_files = [f for f in os.listdir(extracted_dir) if f.endswith(".json")]

        if not session_files or not json_files:
            await message.answer("❌ В архиве отсутствуют необходимые файлы (SESSION + JSON).")
            return

        await message.answer("✅ Архив успешно обработан. Начинаю проверку аккаунтов...")

        total_price, valid_accounts = await check_sessions(session_files, json_files, extracted_dir)

        if total_price > 0:
            text = f"💰 Общая стоимость аккаунтов: {total_price}₽\n\n"
            text += f"✅ Валидных аккаунтов: {len(valid_accounts)}"
            keyboard = create_confirmation_keyboard()
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer("❌ Нет валидных аккаунтов для продажи.")

    except rarfile.NeedFirstVolume:
        await message.answer("❌ Многотомные архивы не поддерживаются.")
    except rarfile.PasswordRequired:
        await message.answer("❌ Архив защищён паролем. Пожалуйста, загрузите архив без пароля.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке архива: {e}")
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)
        if os.path.exists(extracted_dir):
            shutil.rmtree(extracted_dir)
rarfile.UNRAR_TOOL = "C:/Program Files/WinRAR/unrar.exe"
@dp.callback_query(lambda call: call.data == "confirm_accounts")
async def handle_confirm_accounts(call: types.CallbackQuery):
    user_id = call.from_user.id

    try:
        update_balance(user_id, 1000)
        update_sold_accounts(user_id, 5)

        await call.answer("✅ Аккаунты подтверждены. Баланс и количество аккаунтов обновлены.")
        await call.message.edit_text("✅ Аккаунты подтверждены.")
    except Exception as e:
        await call.answer(f"❌ Ошибка: {e}")

@dp.callback_query(lambda call: call.data == "reject_accounts")
async def handle_reject_accounts(call: types.CallbackQuery):
    await call.answer("❌ Аккаунты отклонены.")
    await call.message.edit_text("❌ Аккаунты отклонены.")
@dp.message(lambda message: message.text == "🛒 Продать аккаунты")
async def sell_accounts(message: types.Message):
    user_id = message.from_user.id

    markup = InlineKeyboardMarkup(inline_keyboard=[])
    button = InlineKeyboardButton(
        text=get_text(user_id, "upload_large_archive"),
        url="https://bigsize.blitzkrieg.space/big_files/upload-big-file?seller_id=5270&ref_id=FRANCHISE_APP_1"
    )
    markup.inline_keyboard.append([button])

    await message.answer(
        f"""
<b>{get_text(user_id, "upload_accounts_title")}</b>

{get_text(user_id, "upload_archive_description")}

<b>{get_text(user_id, "max_size")}:</b> 20 MB

<b>{get_text(user_id, "formats")}:</b> TDATA, SESSION + JSON

📦 <a href="https://bigsize.blitzkrieg.space/big_files/upload-big-file?seller_id=5270&ref_id=FRANCHISE_APP_1">{get_text(user_id, "upload_large_archive")}</a>

📖 <a href="https://teletype.in/@blitzkriegdev/blitzkrieg-faq#vZhK">{get_text(user_id, "account_requirements")}</a>
""",
        parse_mode="HTML",
        reply_markup=markup
    )


@dp.message(lambda message: message.text == "💼 Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        await message.answer(get_text(user_id, "user_not_found"))
        return

    registration_date = user.get("registration_date")
    if registration_date:
        date_obj = datetime.fromisoformat(registration_date)
        days_since_registration = (datetime.now() - date_obj).days
        formatted_registration = get_text(user_id, "days_ago", days=days_since_registration)
    else:
        formatted_registration = get_text(user_id, "no_data")

    subscription_info = get_subscription_info(user_id)
    subscription_status = get_text(user_id, "subscription_active") if subscription_info["active"] else get_text(user_id, "subscription_inactive")

    currency = user.get("currency", "rub")
    currency_symbol = "USD" if currency == "usd" else "RUB"

    balance_converted = convert_currency(user['balance'], currency)
    earned_converted = convert_currency(user['sold_accounts'], currency)

    text = f"""
<b>{get_text(user_id, "profile_title")}</b>
━━━━━━━━━━━━━━━━━━
<b>{get_text(user_id, "user_id")}:</b> <code>{user_id}</code>

<b>{get_text(user_id, "accounts_sold")}:</b> {user['quantity']}
<b>{get_text(user_id, "earned")}:</b> {earned_converted} {currency_symbol}

<b>{get_text(user_id, "balance")}:</b> {balance_converted} {currency_symbol}

<b>{get_text(user_id, "seller_plus_status")}:</b> {subscription_status}

<b>{get_text(user_id, "registered")}:</b> {formatted_registration}
━━━━━━━━━━━━━━━━━━
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(user_id, "last_30_days"), callback_data="30_days"),
         InlineKeyboardButton(text=get_text(user_id, "all_time"), callback_data="all_time")],
        [InlineKeyboardButton(text=get_text(user_id, "withdraw_funds"), callback_data="withdraw")],
        [InlineKeyboardButton(text=get_text(user_id, "my_accounts"), callback_data="my_accounts"),
         InlineKeyboardButton(text=get_text(user_id, "seller_plus"), callback_data="seller")],
        [InlineKeyboardButton(text=get_text(user_id, "settings"), callback_data="settings")]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

def create_stats_keyboard(active_button=None):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 За 30 дней", callback_data="30_days"),
         InlineKeyboardButton(text="📈 За всё время", callback_data="all_time")],
        [InlineKeyboardButton(text="💸 Вывод средств", callback_data="withdraw")],
        [InlineKeyboardButton(text="📂 Мои аккаунты", callback_data="my_accounts"),
         InlineKeyboardButton(text="Seller+", callback_data="seller")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])

    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data == active_button:
                button.text = f"• {button.text} •"

    return keyboard


@dp.message(Command('activate_subscription'))
async def activate_subscription_command(message: types.Message):
    user_id = message.from_user.id
    activate_subscription(user_id, duration_days=30)
    await message.answer("Ваша подписка активирована на 30 дней.")

@dp.message(Command('check_subscription'))
async def check_subscription_command(message: types.Message):
    user_id = message.from_user.id
    subscription_info = get_subscription_info(user_id)
    if subscription_info["active"]:
        expiry_date = subscription_info["expiry_date"].strftime("%Y-%m-%d %H:%M:%S")
        await message.answer(f"Ваша подписка активна. Истекает: {expiry_date}")
    else:
        await message.answer("Ваша подписка неактивна.")

@dp.callback_query(lambda call: call.data == "30_days")
async def handle_30_days(call: types.CallbackQuery):
    await call.answer("Вы выбрали 30 дней.")
    keyboard = create_stats_keyboard(active_button="30_days")
    await call.message.edit_reply_markup(reply_markup=keyboard)

@dp.callback_query(lambda call: call.data == "all_time")
async def handle_all_time(call: types.CallbackQuery):
    await call.answer("Вы выбрали всё время.")
    keyboard = create_stats_keyboard(active_button="all_time")
    await call.message.edit_reply_markup(reply_markup=keyboard)

async def send_long_message(chat_id, text):
    while len(text) > 0:
        part = text[:4096]
        text = text[4096:]
        await bot.send_message(chat_id, part)


@dp.callback_query(lambda call: call.data == "seller")
async def handle_seller(call: types.CallbackQuery):
    user_id = call.from_user.id
    user = get_user(user_id)
    subscription_info = get_subscription_info(user_id)

    if subscription_info["active"]:
        await call.answer("У вас уже есть активная привилегия Seller+", show_alert=True)
    else:
        text = (
            "☹️ Недостаточно проданных аккаунтов\n\n"
            "Чтобы активировать привилегию Seller+ ([подробнее](https://teletype.in/@blitzkriegdev/blitzkrieg-faq#7xVJ)), "
            "необходимо продать еще 70 аккаунтов за этот день."
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="back_to_profile")]
        ])

        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.callback_query(lambda call: call.data == "withdraw")
async def handle_withdraw(call: types.CallbackQuery):

    await call.answer("Вывод средств.")
    withdraw_text = """<b>💸 Вывод средств</b>

Выберите действие:
"""
    withdraw_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История выводов", callback_data="withdraw_history")],
        [InlineKeyboardButton(text="💳 Вывести средства", callback_data="withdraw_funds")],
        [InlineKeyboardButton(text="🔄 Изменить кошельки", callback_data="change_wallets")],
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="back_to_profile")]
    ])
    await call.message.edit_text(withdraw_text, parse_mode="HTML", reply_markup=withdraw_keyboard)

@dp.callback_query(lambda call: call.data == "withdraw_funds")
async def handle_withdraw_funds(call: types.CallbackQuery):

    user_id = call.from_user.id
    wallets = get_wallets(user_id)

    if not wallets or (not wallets.get("cryptobot_id") and not wallets.get("lzt_link")):
        await call.answer("У вас нет привязанных кошельков.")
        await call.message.edit_text("У вас нет привязанных кошельков.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="OK", callback_data="back_to_profile")]
        ]))
    else:
        text = """<b>💸 Ваши привязанные кошельки:</b>

<b>Cryptobot ID:</b> {cryptobot_id}
<b>LZT Профиль:</b> {lzt_link}
""".format(
            cryptobot_id=wallets.get("cryptobot_id", "Не привязан"),
            lzt_link=wallets.get("lzt_link", "Не привязан")
        )
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ]))

@dp.callback_query(lambda call: call.data == "back_to_profile")
async def handle_back_to_profile(call: types.CallbackQuery):
    user_id = call.from_user.id
    user = get_user(user_id)

    if not user:
        add_user(user_id)
        user = get_user(user_id)

    registration_date = user.get("registration_date", "Нет данных")
    if registration_date != "Нет данных":
        date_obj = datetime.fromisoformat(registration_date)
        days_since_registration = (datetime.now() - date_obj).days
        formatted_registration = f"{days_since_registration} дней назад"
    else:
        formatted_registration = "Нет данных"

    subscription_info = get_subscription_info(user_id)
    subscription_status = "Есть" if subscription_info["active"] else "Нет"

    currency = user.get("currency", "rub")
    currency_symbol = "USD" if currency == "usd" else "RUB"

    text = f"""
<b>👤 Профиль пользователя</b>
━━━━━━━━━━━━━━━━━━
<b>🆔 ID:</b> <code>{user_id}</code>

<b>🏆 Продано аккаунтов:</b> {user.get('quantity', 0)}
<b>💸 Заработано:</b> {user.get('sold_accounts', 0)} {currency_symbol}

<b>💰 Баланс:</b> {user.get('balance', 0)} {currency_symbol}

<b>👑 Seller+ привилегия:</b> {subscription_status}

<b>📅 Зарегистрирован:</b> {formatted_registration}
━━━━━━━━━━━━━━━━━━
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 За 30 дней", callback_data="30_days"),
         InlineKeyboardButton(text="📈 За всё время", callback_data="all_time")],
        [InlineKeyboardButton(text="💸 Вывод средств", callback_data="withdraw")],
        [InlineKeyboardButton(text="📂 Мои аккаунты", callback_data="my_accounts"),
         InlineKeyboardButton(text="Seller+", callback_data="seller")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(lambda call: call.data == "change_wallets")
async def handle_change_wallets(call: types.CallbackQuery):

    await call.answer("Изменение кошельков.")
    change_wallets_text = """<b>🔄 Изменение кошельков</b>

Выберите кошелек для изменения или добавления:
"""
    change_wallets_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="LZT", callback_data="change_lzt_wallet")],
        [InlineKeyboardButton(text="Cryptobot", callback_data="change_cryptobot_wallet")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_operation")]
    ])
    await call.message.edit_text(change_wallets_text, parse_mode="HTML", reply_markup=change_wallets_keyboard)


@dp.callback_query(lambda call: call.data == "change_cryptobot_wallet")
async def handle_change_cryptobot_wallet(call: types.CallbackQuery, state: FSMContext):

    await call.answer("Изменение кошелька Cryptobot.")
    change_cryptobot_text = """<b>Изменение привязанного Cryptobot профиля</b>

Введите Telegram ID аккаунта, который привязан к вашему кошельку Cryptobot.
Пример Telegram ID: <code>123456789</code>

Ваш Telegram ID можно узнать, написав боту @userinfobot или @myldbot.
"""
    change_cryptobot_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_operation")]
    ])
    await call.message.edit_text(change_cryptobot_text, parse_mode="HTML", reply_markup=change_cryptobot_keyboard)

    await state.set_state(WalletStates.waiting_for_cryptobot_id)


@dp.callback_query(lambda call: call.data == "change_lzt_wallet")
async def handle_change_lzt_wallet(call: types.CallbackQuery, state: FSMContext):

    await call.answer("Изменение кошелька LZT.")
    change_lzt_text = """<b>Изменение привязанного LZT профиля</b>

Введите постоянную ссылку на ваш профиль LZT.
Пример ссылки: <code>https://lolz.live/members/123456</code>

Получить ссылку такого вида можно на этой странице в разделе <b>Адрес профиля</b> — <b>Постоянная ссылка на ваш профиль</b>.
"""
    change_lzt_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_operation")]
    ])
    await call.message.edit_text(change_lzt_text, parse_mode="HTML", reply_markup=change_lzt_keyboard)

    await state.set_state(WalletStates.waiting_for_lzt_link)


@dp.callback_query(lambda call: call.data == "change_profile_name")
async def handle_change_profile_name(call: types.CallbackQuery, state: FSMContext):

    await call.answer("Изменение названия профиля.")
    change_profile_name_text = """<b>📝 Изменение названия профиля</b>

Введите новое название для вашего профиля:
"""
    change_profile_name_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")]
    ])
    await call.message.edit_text(change_profile_name_text, parse_mode="HTML", reply_markup=change_profile_name_keyboard)

    await state.set_state(WalletStates.waiting_for_profile_name)
def get_wallets(user_id: int):

    try:
        cursor.execute('SELECT cryptobot_id, lzt_link FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            return {
                "cryptobot_id": result[0],
                "lzt_link": result[1]
            }
        return None
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении данных о кошельках: {e}")
        return None


@dp.message(Command('my_wallets'))
async def show_wallets(message: types.Message):
    user_id = message.from_user.id
    wallets = get_wallets(user_id)

    if wallets:
        text = f"""<b>Ваши кошельки:</b>

<b>Cryptobot ID:</b> {wallets.get("cryptobot_id", "Не привязан")}
<b>LZT Профиль:</b> {wallets.get("lzt_link", "Не привязан")}
"""
    else:
        text = "❌ Данные о кошельках не найдены."

    await message.answer(text, parse_mode="HTML")


@dp.message(StateFilter(WalletStates.waiting_for_cryptobot_id))
async def process_cryptobot_id(message: types.Message, state: FSMContext):

    cryptobot_id = message.text.strip()

    if not cryptobot_id.isdigit():
        await message.answer("❌ Некорректный Telegram ID. Введите число.")
        return

    user_id = message.from_user.id
    save_cryptobot_id(user_id, cryptobot_id)

    await message.answer(f"✅ Telegram ID <code>{cryptobot_id}</code> успешно привязан.")
    await state.clear()


@dp.message(StateFilter(WalletStates.waiting_for_lzt_link))
async def process_lzt_link(message: types.Message, state: FSMContext):

    lzt_link = message.text.strip()

    if not lzt_link.startswith("https://lolz.live/members/"):
        await message.answer("❌ Некорректная ссылка. Введите ссылку в формате: https://lolz.live/members/123456")
        return

    user_id = message.from_user.id
    save_lzt_link(user_id, lzt_link)

    await message.answer(f"✅ Ссылка <code>{lzt_link}</code> успешно привязана.")
    await state.clear()
@dp.callback_query(lambda call: call.data == "cancel_operation")
async def handle_cancel_operation(call: types.CallbackQuery, state: FSMContext):

    await call.answer("Операция отменена.")
    await call.message.edit_text("❌ Операция отменена.")
    await state.clear()


@dp.callback_query(lambda call: call.data == "my_accounts")
async def handle_my_accounts(call: types.CallbackQuery):
    await call.answer("Вы выбрали Мои аккаунты.")
    await call.message.edit_text("Вы выбрали Мои аккаунты.")



def create_language_keyboard(active_button=None):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    buttons = [
        ("Русский", "set_language_ru"),
        ("English", "set_language_en")
    ]

    for text, callback_data in buttons:
        if callback_data == active_button:
            text = f"• {text} •"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    return keyboard

@dp.callback_query(lambda call: call.data.startswith("set_language_"))
async def handle_set_language(call: types.CallbackQuery):
    user_id = call.from_user.id
    language = call.data.split("_")[-1]
    update_user(user_id, language=language)

    if language == "ru":
        await call.answer("Язык изменен на русский.")
    else:
        await call.answer("Language changed to English.")

    keyboard = create_language_keyboard(active_button=call.data)
    await call.message.edit_reply_markup(reply_markup=keyboard)

CATEGORIES = {
    "standard_with_delay": "стандарт с отлежкой 24 часа",
    "standard_without_delay": "стандарт без отлежки",
    "seller_plus_with_delay": "seller+ с отлежкой 24 часа",
    "seller_plus_without_delay": "seller+ без отлежки"
}

def load_prices_from_json(category, file_name):

    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            data = json.load(file)

        if not isinstance(data, dict) or "regions" not in data:
            print(f"Ошибка: Неверная структура JSON. Ожидается словарь с ключом 'regions'. Содержимое: {data}")
            return None

        category_name = CATEGORIES.get(category)
        if not category_name:
            print(f"Ошибка: Неизвестная категория '{category}'.")
            return None

        if data.get("category") != category_name:
            print(f"Ошибка: Категория '{category_name}' не найдена в данных.")
            return None

        return {
            "name": category_name,
            "regions": data.get("regions", [])
        }

    except json.JSONDecodeError as e:
        print(f"Ошибка при чтении JSON (ошибка декодирования): {e} в файле: {file_name}")
        return None
    except FileNotFoundError:
        print(f"Ошибка: Файл '{file_name}' не найден.")
        return None
    except Exception as e:
        print(f"Ошибка при загрузке цен: {e}")
        return None
def create_currency_keyboard(active_button=None):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    buttons = [
        ("Рубли 🇷🇺", "set_currency_rub"),
        ("USD 🇺🇸", "set_currency_usd")
    ]

    for text, callback_data in buttons:
        if callback_data == active_button:
            text = f"• {text} •"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    return keyboard

@dp.callback_query(lambda call: call.data.startswith("set_currency_"))
async def handle_set_currency(call: types.CallbackQuery):
    user_id = call.from_user.id
    currency = call.data.split("_")[-1]

    update_user(user_id, currency=currency)

    if currency == "rub":
        await call.answer("Валюта изменена на рубли.")
    else:
        await call.answer("Currency changed to USD.")

    keyboard = create_currency_keyboard(active_button=call.data)
    await call.message.edit_reply_markup(reply_markup=keyboard)

@dp.callback_query(lambda call: call.data == "change_language")
async def handle_change_language(call: types.CallbackQuery):
    await call.answer("Изменение языка.")
    change_language_text = """<b>Изменение языка</b>

Выберите язык интерфейса.  
"""
    change_language_keyboard = create_language_keyboard()
    await call.message.edit_text(change_language_text, parse_mode="HTML", reply_markup=change_language_keyboard)

@dp.callback_query(lambda call: call.data == "change_currency")
async def handle_change_currency(call: types.CallbackQuery):
    await call.answer("Изменение валюты.")
    change_currency_text = """<b>Изменение валюты</b>

Выберите валюту для отображения цен.  
"""
    change_currency_keyboard = create_currency_keyboard()
    await call.message.edit_text(change_currency_text, parse_mode="HTML", reply_markup=change_currency_keyboard)
def create_profile_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notifications")],
        [InlineKeyboardButton(text="🛒 Режим покупки", callback_data="purchase_mode")],
        [InlineKeyboardButton(text="🌐 Изменить язык", callback_data="change_language")],
        [InlineKeyboardButton(text="💱 Изменить валюту", callback_data="change_currency")],
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile_back")]
    ])
    return keyboard

@dp.callback_query(lambda call: call.data == "settings")
async def handle_settings(call: types.CallbackQuery):
    await call.answer("Настройки.")
    settings_text = """<b>⚙️ Настройки</b>

Выберите опцию для настройки:
"""
    settings_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Изменить язык", callback_data="change_language")],
        [InlineKeyboardButton(text="💱 Изменить валюту", callback_data="change_currency")],
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="back_to_profile")]
    ])
    await call.message.edit_text(settings_text, parse_mode="HTML", reply_markup=settings_keyboard)

@dp.callback_query(lambda call: call.data == "settings_back")
async def handle_settings_back(call: types.CallbackQuery):
    await handle_settings(call)

def create_notifications_keyboard(selected_option=None):
    buttons = [
        ("Все", "notifications_all"),
        ("Только важные", "notifications_important"),
        ("Назад в настройки", "settings_back")
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for text, callback_data in buttons:
        if selected_option and callback_data == selected_option:
            text = f"• {text} •"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    return keyboard
@dp.callback_query(lambda call: call.data == "notifications")
async def handle_notifications(call: types.CallbackQuery):
    await call.answer("Настройка уведомлений.")
    notifications_text = """<b>🔔 Уведомления</b>

Выберите тип уведомлений, которые вы хотите получать:
"""
    notifications_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Все уведомления", callback_data="notifications_all")],
        [InlineKeyboardButton(text="Только важные", callback_data="notifications_important")],
        [InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="settings")]
    ])
    await call.message.edit_text(notifications_text, parse_mode="HTML", reply_markup=notifications_keyboard)

@dp.callback_query(lambda call: call.data == "purchase_mode")
async def handle_purchase_mode(call: types.CallbackQuery):

    await call.answer("Настройка режима покупки.")
    purchase_mode_text = """<b>🛒 Режим покупки</b>

Выберите режим покупки для аккаунтов без отлежки 24 часа:
"""
    purchase_mode_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Разрешено", callback_data="purchase_mode_allowed")],
        [InlineKeyboardButton(text="Запрещено", callback_data="purchase_mode_denied")],
        [InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="settings")]
    ])
    await call.message.edit_text(purchase_mode_text, parse_mode="HTML", reply_markup=purchase_mode_keyboard)


@dp.callback_query(lambda call: call.data == "change_language")
async def handle_change_language(call: types.CallbackQuery):

    await call.answer("Изменение языка.")
    change_language_text = """<b>🌐 Изменение языка</b>

Выберите язык интерфейса:
"""
    change_language_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский 🇷🇺", callback_data="set_language_ru")],
        [InlineKeyboardButton(text="English 🇬🇧", callback_data="set_language_en")]
    ])
    await call.message.edit_text(change_language_text, parse_mode="HTML", reply_markup=change_language_keyboard)

@dp.callback_query(lambda call: call.data == "change_currency")
async def handle_change_currency(call: types.CallbackQuery):

    await call.answer("Изменение валюты.")
    change_currency_text = """<b>💱 Изменение валюты</b>

Выберите валюту для отображения цен:
"""
    change_currency_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Рубли 🇷🇺", callback_data="set_currency_rub")],
        [InlineKeyboardButton(text="USD 🇺🇸", callback_data="set_currency_usd")]
    ])
    await call.message.edit_text(change_currency_text, parse_mode="HTML", reply_markup=change_currency_keyboard)

@dp.callback_query(lambda call: call.data.startswith("set_language_"))
async def handle_set_language(call: types.CallbackQuery):

    user_id = call.from_user.id
    language = call.data.split("_")[-1]

    update_user(user_id, language=language)

    if language == "ru":
        await call.answer("Язык изменен на русский.")
    else:
        await call.answer("Language changed to English.")

    await handle_settings(call)

@dp.callback_query(lambda call: call.data.startswith("set_currency_"))
async def handle_set_currency(call: types.CallbackQuery):

    user_id = call.from_user.id
    currency = call.data.split("_")[-1]

    update_user(user_id, currency=currency)

    if currency == "rub":
        await call.answer("Валюта изменена на рубли.")
    else:
        await call.answer("Currency changed to USD.")

    await handle_settings(call)
def set_notification_preference(user_id, preference):

    try:
        cursor.execute('UPDATE users SET notification_preference = ? WHERE user_id = ?', (preference, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении предпочтений уведомлений: {e}")
@dp.callback_query(lambda call: call.data == "notifications_important")
async def handle_notifications_important(call: types.CallbackQuery):
    user_id = call.from_user.id

    set_notification_preference(user_id, "important")

    await call.answer("Только важные уведомления включены.")

    await handle_notifications(call)

@dp.callback_query(lambda call: call.data == "notifications_all")
async def handle_notifications_all(call: types.CallbackQuery):
    user_id = call.from_user.id

    set_notification_preference(user_id, "all")

    await call.answer("Все уведомления включены.")

    await handle_notifications(call)

@dp.callback_query(lambda call: call.data == "notifications")
async def handle_notifications(call: types.CallbackQuery):
    user_id = call.from_user.id

    current_preference = get_notification_preference(user_id)

    notifications_text = """<b>Настройка уведомлений</b>

Выберите типы уведомлений, которые вы хотите получать.
"""
    notifications_keyboard = create_notifications_keyboard(selected_option=current_preference)
    await call.message.edit_text(notifications_text, parse_mode="HTML", reply_markup=notifications_keyboard)
def create_purchase_mode_keyboard(selected_option=None):
    buttons = [
        ("Разрешено", "purchase_mode_allowed"),
        ("Запрещено", "purchase_mode_denied"),
        ("Назад в настройки", "settings_back")
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for text, callback_data in buttons:
        if selected_option and callback_data == selected_option:
            text = f"• {text} •"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    return keyboard
@dp.callback_query(lambda call: call.data == "profile_back")
async def handle_profile_back(call: types.CallbackQuery):
    await call.answer("Возврат в профиль.")
    await profile(call.message)

@dp.callback_query(lambda call: call.data == "purchase_mode")
async def handle_purchase_mode(call: types.CallbackQuery):
    await call.answer("Настройка режима покупки.")
    purchase_mode_text = """<b>Настройка режима покупки</b>

Выберите режим покупки для аккаунтов без отлежки 24 часа.
"""
    purchase_mode_keyboard = create_purchase_mode_keyboard()
    await call.message.edit_text(purchase_mode_text, parse_mode="HTML", reply_markup=purchase_mode_keyboard)

@dp.callback_query(lambda call: call.data == "purchase_mode_allowed")
async def handle_purchase_mode_allowed(call: types.CallbackQuery):
    await call.answer("Покупка без отлежки разрешена.")
    await handle_purchase_mode(call)

@dp.callback_query(lambda call: call.data == "purchase_mode_denied")
async def handle_purchase_mode_denied(call: types.CallbackQuery):
    await call.answer("Покупка без отлежки запрещена.")
    await handle_purchase_mode(call)


@dp.callback_query(lambda call: call.data == "set_language_ru")
async def handle_set_language_ru(call: types.CallbackQuery):
    user_id = call.from_user.id

    update_user(user_id, language="ru")

    await call.answer("Язык изменен на русский.")
    await call.message.edit_text("Язык изменен на русский.")

@dp.callback_query(lambda call: call.data == "set_language_en")
async def handle_set_language_en(call: types.CallbackQuery):
    user_id = call.from_user.id

    update_user(user_id, language="en")

    await call.answer("Language changed to English.")
    await call.message.edit_text("Language changed to English.")

@dp.callback_query(lambda call: call.data == "set_currency_rub")
async def handle_set_currency_rub(call: types.CallbackQuery):
    user_id = call.from_user.id

    update_user(user_id, currency="rub")

    await call.answer("Валюта изменена на рубли.")
    await call.message.edit_text("Валюта изменена на рубли.")

@dp.callback_query(lambda call: call.data == "set_currency_usd")
async def handle_set_currency_usd(call: types.CallbackQuery):
    user_id = call.from_user.id
    update_user(user_id, currency="usd")

    await call.answer("Currency changed to USD.")
    await call.message.edit_text("Currency changed to USD.")





def create_price_keyboard(selected_category=None):

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="• 👑 Для Seller+ •" if selected_category and selected_category.startswith(
                    "seller_plus") else "👑 Для Seller+",
                callback_data="seller_plus"
            ),
            InlineKeyboardButton(
                text="• 💵 Стандартный •" if selected_category and selected_category.startswith(
                    "standard") else "💵 Стандартный",
                callback_data="standard"
            )
        ],
        [
            InlineKeyboardButton(
                text="• С отлежкой 24 часа •" if selected_category and "with_delay" in selected_category else "С отлежкой 24 часа",
                callback_data="with_delay"
            ),
            InlineKeyboardButton(
                text="• Без отлежки •" if selected_category and "without_delay" in selected_category else "Без отлежки",
                callback_data="without_delay"
            )
        ]
    ])
    return keyboard

@dp.callback_query(F.data.in_(["seller_plus", "standard", "with_delay", "without_delay"]))
async def handle_price_category(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_category = data.get("selected_category", "seller_plus_with_delay")

    if call.data == "seller_plus":
        if "with_delay" in selected_category:
            selected_category = "seller_plus_with_delay"
        else:
            selected_category = "seller_plus_without_delay"
    elif call.data == "standard":
        if "with_delay" in selected_category:
            selected_category = "standard_with_delay"
        else:
            selected_category = "standard_without_delay"
    elif call.data == "with_delay":
        if "seller_plus" in selected_category:
            selected_category = "seller_plus_with_delay"
        else:
            selected_category = "standard_with_delay"
    elif call.data == "without_delay":
        if "seller_plus" in selected_category:
            selected_category = "seller_plus_without_delay"
        else:
            selected_category = "standard_without_delay"

    await state.update_data(selected_category=selected_category)

    user_id = call.from_user.id
    currency = get_user_currency(user_id)
    currency_symbol = "USD" if currency == "usd" else "RUB"

    file_name = f"{selected_category}.json"
    prices_data = load_prices_from_json(selected_category, file_name)

    if prices_data:
        response = f"📌 Категория: {prices_data['name']}\n\n"
        for region in prices_data.get("regions", []):
            response += f"🌍 Регион: {region.get('name')}\n"
            for country in region.get("countries", []):
                price = country.get('price')
                price_converted = convert_currency(price, currency)
                response += f"├─ {country.get('flag')} {country.get('name')} {country.get('phone_code')} • {price_converted} {currency_symbol}\n"
        await call.message.answer(response, reply_markup=create_price_keyboard(selected_category))
    else:
        await call.message.answer("Цены для выбранной категории не найдены.")

    await call.answer()

@dp.message(lambda message: message.text == "📈 Цены")
async def show_prices(message: types.Message):
    user_id = message.from_user.id
    currency = get_user_currency(user_id)

    category = "seller_plus_with_delay"
    file_name = "seller_plus_with_delay.json"
    prices_data = load_prices_from_json(category, file_name)

    if prices_data:
        response = f"📌 Категория: {prices_data['name']}\n\n"
        for region in prices_data.get("regions", []):
            response += f"🌍 Регион: {region.get('name')}\n"
            for country in region.get("countries", []):
                price = country.get('price')
                price_converted = convert_currency(price, currency)
                currency_symbol = "USD" if currency == "usd" else "RUB"
                response += f"├─ {country.get('flag')} {country.get('name')} {country.get('phone_code')} • {price_converted} {currency_symbol}\n"
        await message.answer(response, reply_markup=create_price_keyboard(category))
    else:
        await message.answer("Цены для выбранной категории не найдены.")

@dp.callback_query(F.data.in_(["standard_with_delay", "standard_without_delay", "seller_plus_with_delay", "seller_plus_without_delay"]))
async def handle_price_category(call: types.CallbackQuery):
    category = call.data
    file_name = None

    if category == "standard_with_delay":
        file_name = "standard_with_delay.json"
    elif category == "standard_without_delay":
        file_name = "standard_without_delay.json"
    elif category == "seller_plus_with_delay":
        file_name = "seller_plus_with_delay.json"
    elif category == "seller_plus_without_delay":
        file_name = "seller_plus_without_delay.json"
    else:
        await call.message.answer("Некорректная категория.")
        await call.answer()
        return

    prices_data = load_prices_from_json(category, file_name)

    if prices_data:
        response = f"📌 Категория: {prices_data['name']}\n\n"
        for region in prices_data.get("regions", []):
            response += f"🌍 Регион: {region.get('name')}\n"
            for country in region.get("countries", []):
                response += f"├─ {country.get('flag')} {country.get('name')} {country.get('phone_code')} • {country.get('price')}₽\n"
        await call.message.answer(response, reply_markup=create_price_keyboard(category))
    else:
        await call.message.answer("Цены для выбранной категории не найдены.")

    await call.answer()



@dp.message(lambda message: message.text == "💬 Поддержка")
async def support(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        get_text(user_id, "official_support", link="https://t.me/bzskup_support"),
        parse_mode="Markdown"
    )

@dp.message(lambda message: message.text == "🔌 API")
async def api_info(message: types.Message):
    user_id = message.from_user.id
    await message.answer(get_text(user_id, "api_documentation"))

@dp.message(lambda message: message.text == "🤝 Сотрудничество и Реферальные программы")
async def partnership(message: types.Message):
    user_id = message.from_user.id
    await message.answer(get_text(user_id, "partnership_info"))


@dp.message(lambda message: message.text == "📖 Условия работы")
async def terms(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    if user and user["agreed_to_terms"] == 1:
        await message.answer(
            get_text(user_id, "terms_of_service", link="https://teletype.in/@cjsdkncvkjdsnkvcds/4O_vM0eBTAK"),
            parse_mode="Markdown"
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text(user_id, "agree"), callback_data="agree_terms")]
        ])
        await message.answer(
            f"{get_text(user_id, 'terms_of_service', link='https://teletype.in/@cjsdkncvkjdsnkvcds/4O_vM0eBTAK')}\n\n"
            f"{get_text(user_id, 'confirm_terms')}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

def update_agreement(user_id):
    try:
        cursor.execute('UPDATE users SET agreed_to_terms = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении согласия (user_id: {user_id}): {e}")


@dp.callback_query(lambda call: call.data == "agree_terms")
async def handle_agree_terms(call: types.CallbackQuery):
    user_id = call.from_user.id

    try:
        cursor.execute('UPDATE users SET agreed_to_terms = 1 WHERE user_id = ?', (user_id,))
        conn.commit()

        await call.answer("✅ Вы согласились с условиями работы.")
        await call.message.edit_text(
            "📖 Условия работы: [прочитать](https://teletype.in/@cjsdkncvkjdsnkvcds/4O_vM0eBTAK).",
            parse_mode="Markdown"
        )
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении согласия с условиями (user_id: {user_id}): {e}")
        await call.answer("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

@dp.callback_query(lambda message: message.text == "📖 Условия работы")
async def handle_agree_terms(call: types.CallbackQuery):
    user_id = call.from_user.id

    try:
        update_agreement(user_id)

        await call.answer("✅ Вы согласились с условиями работы.")
        await call.message.edit_text(
            "📖 Условия работы: [прочитать](https://teletype.in/@cjsdkncvkjdsnkvcds/4O_vM0eBTAK).",
            parse_mode="Markdown")
    except sqlite3.Error as e:
        logging.error(f"Ошибка при обновлении согласия с условиями (user_id: {user_id}): {e}")
        await call.answer("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

@dp.message(lambda message: message.text == "💞 Отзывы")
async def reviews(message: types.Message):
    await message.answer("💞 Оставьте отзыв: [форум](https://lolz.live/threads/7661091/).", parse_mode="Markdown")

async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        console_input()
    )

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
