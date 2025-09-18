import logging
import asyncio
import aiohttp
import sqlite3
import random
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime, timedelta

# Конфигурация
API_TOKEN = 'YOUR_BOT_TOKEN_HERE'
ADMIN_ID = 123456789  # ID администратора
PROVIDER_TOKEN = 'YOUR_CRYSTALPAY_TOKEN'  # Для платежей

# Инициализация бота
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

# Инициализация БД
conn = sqlite3.connect('virtual_numbers.db')
cursor = conn.cursor()

# Таблица пользователей
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE,
    username TEXT,
    full_name TEXT,
    balance REAL DEFAULT 0,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Таблица номеров
cursor.execute('''
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY,
    number TEXT UNIQUE,
    country TEXT,
    service TEXT,
    price REAL,
    status TEXT DEFAULT 'available',
    activation_time TIMESTAMP,
    user_id INTEGER,
    sms_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
''')

# Таблица транзакций
cursor.execute('''
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    amount REAL,
    type TEXT,
    status TEXT DEFAULT 'pending',
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
''')

# Таблица стран и сервисов
cursor.execute('''
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    country TEXT,
    country_code TEXT,
    service_name TEXT,
    service_code TEXT,
    price REAL,
    available INTEGER DEFAULT 1
)
''')

# Добавляем тестовые данные
cursor.execute("SELECT COUNT(*) FROM services")
if cursor.fetchone()[0] == 0:
    services_data = [
        ('Россия', 'RU', 'Telegram', 'tg', 50.0),
        ('Россия', 'RU', 'WhatsApp', 'wa', 45.0),
        ('Россия', 'RU', 'VKontakte', 'vk', 40.0),
        ('США', 'US', 'Telegram', 'tg', 70.0),
        ('США', 'US', 'WhatsApp', 'wa', 65.0),
        ('Украина', 'UA', 'Telegram', 'tg', 55.0),
        ('Украина', 'UA', 'Viber', 'vb', 48.0),
        ('Казахстан', 'KZ', 'WhatsApp', 'wa', 52.0),
        ('Германия', 'DE', 'Telegram', 'tg', 80.0),
        ('Великобритания', 'GB', 'WhatsApp', 'wa', 75.0)
    ]
    
    for country, code, service, s_code, price in services_data:
        cursor.execute(
            "INSERT INTO services (country, country_code, service_name, service_code, price) VALUES (?, ?, ?, ?, ?)",
            (country, code, service, s_code, price)
        )

conn.commit()

# Генерация виртуальных номеров
def generate_virtual_number(country_code):
    prefixes = {
        'RU': ['7916', '7903', '7920'],
        'US': ['1201', '1212', '1234'],
        'UA': ['38050', '38063', '38067'],
        'KZ': ['7700', '7701', '7702'],
        'DE': ['4915', '4916', '4917'],
        'GB': ['4477', '4478', '4479']
    }
    
    prefix = random.choice(prefixes.get(country_code, ['7916']))
    number = prefix + ''.join([str(random.randint(0, 9)) for _ in range(11 - len(prefix))])
    return number

# Состояния для FSM
class OrderStates(StatesGroup):
    choosing_country = State()
    choosing_service = State()
    confirming_purchase = State()
    waiting_for_sms = State()

class AdminStates(StatesGroup):
    adding_balance = State()
    adding_numbers = State()

# Главное меню
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📱 Купить номер"))
    keyboard.add(KeyboardButton("💰 Мой баланс"), KeyboardButton("📊 Мои номера"))
    keyboard.add(KeyboardButton("🆘 Поддержка"))
    return keyboard

# Меню стран
def countries_menu():
    cursor.execute("SELECT DISTINCT country, country_code FROM services WHERE available = 1")
    countries = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    for country, code in countries:
        keyboard.add(InlineKeyboardButton(f"🇺🇳 {country}", callback_data=f"country_{code}"))
    keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
    return keyboard

# Меню сервисов для страны
def services_menu(country_code):
    cursor.execute("SELECT service_name, service_code, price FROM services WHERE country_code = ? AND available = 1", (country_code,))
    services = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for service, code, price in services:
        keyboard.add(InlineKeyboardButton(f"{service} - {price} руб", callback_data=f"service_{code}"))
    keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_countries"))
    return keyboard

# Команда старта
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Регистрируем пользователя
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
        (user_id, username, full_name)
    )
    conn.commit()
    
    welcome_text = """🔢 <b>Добро пожаловать в VirtualNumbersBot!</b>

📱 <b>Наши услуги:</b>
• Виртуальные номера для регистрации
• Поддержка всех популярных сервисов
• Мгновенная активация
• Низкие цены

🎯 <b>Доступные сервисы:</b>
• Telegram, WhatsApp, Viber
• VKontakte, Instagram
• И многие другие!

Выберите действие:"""
    
    await message.answer(welcome_text, reply_markup=main_menu())

# Обработка кнопок главного меню
@dp.message_handler(lambda message: message.text == "📱 Купить номер")
async def buy_number(message: types.Message):
    await message.answer("🌍 <b>Выберите страну:</b>", reply_markup=countries_menu())

@dp.message_handler(lambda message: message.text == "💰 Мой баланс")
async def show_balance(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()
    
    if balance:
        await message.answer(f"💳 <b>Ваш баланс:</b> {balance[0]} руб\n\n💎 Пополнить баланс: /balance")
    else:
        await message.answer("❌ Пользователь не найден")

@dp.message_handler(lambda message: message.text == "📊 Мои номера")
async def show_my_numbers(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('''
        SELECT n.number, n.country, n.service, n.activation_time, n.sms_code 
        FROM numbers n 
        WHERE n.user_id = ? AND n.status = 'active'
    ''', (user_id,))
    
    numbers = cursor.fetchall()
    
    if numbers:
        text = "📱 <b>Ваши активные номера:</b>\n\n"
        for number, country, service, activation_time, sms_code in numbers:
            text += f"• {number} ({country}) - {service}\n"
            text += f"  🕐 Активирован: {activation_time}\n"
            if sms_code:
                text += f"  📨 Код: {sms_code}\n"
            text += "\n"
        await message.answer(text)
    else:
        await message.answer("❌ У вас нет активных номеров")

@dp.message_handler(lambda message: message.text == "🆘 Поддержка")
async def support(message: types.Message):
    support_text = """🆘 <b>Техническая поддержка</b>

📞 По всем вопросам:
• Проблемы с активацией
• Вопросы по оплате
• Технические неполадки

👨‍💻 Свяжитесь с нами: @support_username

⏰ Время работы: 24/7"""
    await message.answer(support_text)

# Обработка выбора страны
@dp.callback_query_handler(lambda c: c.data.startswith('country_'))
async def country_selected(call: types.CallbackQuery):
    country_code = call.data.split('_')[1]
    cursor.execute("SELECT country FROM services WHERE country_code = ? LIMIT 1", (country_code,))
    country = cursor.fetchone()
    
    if country:
        await call.message.edit_text(f"🇺🇳 <b>Выбрана страна:</b> {country[0]}\n\n📲 <b>Выберите сервис:</b>", 
                                   reply_markup=services_menu(country_code))
    else:
        await call.answer("❌ Страна не найдена")

# Обработка выбора сервиса
@dp.callback_query_handler(lambda c: c.data.startswith('service_'))
async def service_selected(call: types.CallbackQuery, state: FSMContext):
    service_code = call.data.split('_')[1]
    user_id = call.from_user.id
    
    cursor.execute('''
        SELECT s.country, s.country_code, s.service_name, s.price 
        FROM services s 
        WHERE s.service_code = ? AND s.available = 1
    ''', (service_code,))
    
    service = cursor.fetchone()
    
    if service:
        country, country_code, service_name, price = service
        
        # Проверяем баланс
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = cursor.fetchone()
        
        if balance and balance[0] >= price:
            # Генерируем номер
            number = generate_virtual_number(country_code)
            
            # Сохраняем в состоянии
            await state.update_data(
                country=country,
                country_code=country_code,
                service=service_name,
                price=price,
                number=number
            )
            
            confirm_text = f"""✅ <b>Подтверждение покупки</b>

📱 Номер: +{number}
🌍 Страна: {country}
📲 Сервис: {service_name}
💵 Стоимость: {price} руб

Для подтверждения нажмите "Купить" """
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("🛒 Купить", callback_data="confirm_purchase"))
            keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_purchase"))
            
            await call.message.edit_text(confirm_text, reply_markup=keyboard)
            await OrderStates.confirming_purchase.set()
            
        else:
            await call.answer("❌ Недостаточно средств на балансе")
            await call.message.answer(f"💳 Ваш баланс: {balance[0] if balance else 0} руб\nНужно: {price} руб\n\nПополните баланс: /balance")
    else:
        await call.answer("❌ Сервис не доступен")

# Подтверждение покупки
@dp.callback_query_handler(lambda c: c.data == 'confirm_purchase', state=OrderStates.confirming_purchase)
async def confirm_purchase(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    
    # Списываем средства
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (data['price'], user_id))
    
    # Создаем запись о номере
    cursor.execute('''
        INSERT INTO numbers (number, country, service, price, status, activation_time, user_id)
        VALUES (?, ?, ?, ?, 'active', datetime('now'), ?)
    ''', (data['number'], data['country'], data['service'], data['price'], user_id))
    
    # Записываем транзакцию
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, status, details)
        VALUES (?, ?, 'purchase', 'completed', ?)
    ''', (user_id, data['price'], f"Покупка номера {data['number']} для {data['service']}"))
    
    conn.commit()
    
    # Генерируем тестовый SMS код
    sms_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    cursor.execute("UPDATE numbers SET sms_code = ? WHERE number = ?", (sms_code, data['number']))
    conn.commit()
    
    success_text = f"""🎉 <b>Покупка успешна!</b>

📱 Номер: +{data['number']}
🌍 Страна: {data['country']}
📲 Сервис: {data['service']}
💵 Списано: {data['price']} руб

📨 <b>Ожидайте SMS:</b>
Код придёт в течение 2-3 минут

🔄 <b>Обновить код:</b> /refresh_{data['number']}"""
    
    await call.message.edit_text(success_text)
    await state.finish()
    
    # Имитируем приход SMS через 1-2 минуты
    asyncio.create_task(send_sms_after_delay(data['number'], sms_code, user_id))

async def send_sms_after_delay(number, sms_code, user_id):
    await asyncio.sleep(random.randint(60, 120))
    try:
        await bot.send_message(
            user_id,
            f"📨 <b>Новое SMS на номер +{number}:</b>\n\n🔢 Код: <code>{sms_code}</code>\n\n✅ Используйте этот код для регистрации",
            parse_mode='HTML'
        )
    except Exception as e:
        logging.error(f"Failed to send SMS notification: {e}")

# Админ команды
@dp.message_handler(commands=['admin'], user_id=ADMIN_ID)
async def admin_panel(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    keyboard.add(InlineKeyboardButton("💵 Добавить баланс", callback_data="admin_add_balance"))
    keyboard.add(InlineKeyboardButton("📱 Добавить номера", callback_data="admin_add_numbers"))
    
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=keyboard)

# Запуск бота
async def on_startup(dp):
    logging.info("Virtual Numbers Bot started")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)