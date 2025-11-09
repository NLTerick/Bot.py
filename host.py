#!/usr/bin/env python3
"""
🎰 JETTON STAR BOT - ПОЛНАЯ ВЕРСИЯ ДЛЯ СЕРВЕРА
Работает 24/7 только для ваших ID: 7950097531 и 313556463
"""

import os
import requests
import random
import time
import threading
import hashlib
import logging
from flask import Flask, request, jsonify

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ================== КОНФИГУРАЦИЯ ==================
BOT_TOKEN = "8213741966:AAFgv4O2eO2iL33IlDji4jfjQkSWZ8YmIF4"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ЭКСКЛЮЗИВНЫЕ ПОЛЬЗОВАТЕЛИ
AUTHORIZED_USERS = {
    "7950097531": "👑 ВЛАДЕЛЕЦ",
    "313556463": "👥 ДРУГ"
}

# Глобальное состояние бота
bot_state = {
    'games': {},
    'active_sessions': {}
}

class JettonGame:
    def __init__(self, user_id):
        self.user_id = user_id
        self.bomb_count = 3
        self.bomb_positions = []
        self.revealed_cells = []
        self.game_active = False
        self.waiting_for_bombs = False
        self.last_message_id = None
        self.moves = 0
        self.bombs_found = 0
        self.stars_found = 0
        
    def generate_bombs(self, count):
        """Генерация бомб на основе ID пользователя"""
        seed = int(hashlib.md5(f"jetton_{self.user_id}_{count}".encode()).hexdigest()[:8], 16)
        random.seed(seed)
        bombs = random.sample(range(1, 26), count)
        random.seed()
        return bombs
    
    def create_grid(self):
        """Создание игрового поля"""
        grid_text = "🎰 <b>JETTON STAR - ЭКСКЛЮЗИВ</b>\n\n"
        grid_text += "⬛️<b>│ 1️⃣ │ 2️⃣ │ 3️⃣ │ 4️⃣ │ 5️⃣ </b>\n"
        grid_text += "──┼───┼───┼───┼───┼───\n"
        
        for i in range(5):
            grid_text += f"<b>{i+1}️⃣ </b>│"
            for j in range(5):
                cell_number = i * 5 + j + 1
                
                if cell_number in self.revealed_cells:
                    if cell_number in self.bomb_positions:
                        grid_text += " 💣 │"
                    else:
                        grid_text += " ⭐ │"
                else:
                    grid_text += " ▪️ │"
            grid_text += "\n"
            if i < 4:
                grid_text += "──┼───┼───┼───┼───┼───\n"
        
        return grid_text

def send_telegram_message(chat_id, text, message_id=None, reply_markup=None):
    """Отправка сообщения в Telegram"""
    try:
        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        if message_id:
            url = f"{TELEGRAM_API}/editMessageText"
            payload['message_id'] = message_id
            
        if reply_markup:
            payload['reply_markup'] = reply_markup
            
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get('ok') and not message_id:
            return result['result']['message_id']
        return message_id
        
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        return None

def is_authorized(user_id):
    """Проверка авторизации"""
    return str(user_id) in AUTHORIZED_USERS

def get_user_role(user_id):
    """Получение роли пользователя"""
    return AUTHORIZED_USERS.get(str(user_id), "🚫 НЕАВТОРИЗОВАН")

def start_game_session(chat_id, user_id):
    """Начало новой игровой сессии"""
    if not is_authorized(user_id):
        send_telegram_message(chat_id, 
            "❌ <b>ДОСТУП ЗАПРЕЩЕН</b>\n\n"
            "Этот бот доступен только для эксклюзивных пользователей.\n\n"
            "🔐 <b>Авторизованные ID:</b>\n"
            "• 7950097531 - 👑 ВЛАДЕЛЕЦ\n"
            "• 313556463 - 👥 ДРУГ")
        return None
    
    game = JettonGame(user_id)
    bot_state['games'][chat_id] = game
    bot_state['active_sessions'][user_id] = chat_id
    
    user_role = get_user_role(user_id)
    
    # Клавиатура для выбора уровня
    keyboard = {
        'inline_keyboard': [[
            {'text': '🎯 ЛЕГКИЙ (3 бомбы)', 'callback_data': 'level_3'},
            {'text': '⚡ СРЕДНИЙ (10 бомб)', 'callback_data': 'level_10'}
        ], [
            {'text': '💀 ХАРДКОР (20 бомб)', 'callback_data': 'level_20'}
        ]]
    }
    
    message = f"""
🎰 <b>JETTON STAR - ЭКСКЛЮЗИВНЫЙ ДОСТУП</b>

{user_role}
🔐 <b>ID:</b> <code>{user_id}</code>

<b>Выберите уровень сложности:</b>

• 🎯 ЛЕГКИЙ - 3 бомбы (88% звезд)
• ⚡ СРЕДНИЙ - 10 бомб (60% звезд)  
• 💀 ХАРДКОР - 20 бомб (20% звезд)

<i>Нажмите кнопку ниже для выбора</i>
    """
    
    message_id = send_telegram_message(chat_id, message, reply_markup=keyboard)
    if message_id:
        game.last_message_id = message_id
        
    return game

def process_level_selection(chat_id, game, level):
    """Обработка выбора уровня"""
    try:
        bomb_count = int(level)
        if bomb_count not in [3, 10, 20]:
            return False
            
        game.bomb_count = bomb_count
        game.bomb_positions = game.generate_bombs(bomb_count)
        game.waiting_for_bombs = False
        game.game_active = True
        
        user_role = get_user_role(game.user_id)
        logger.info(f"🎯 {user_role} {game.user_id} выбрал уровень {bomb_count} бомб")
        
        # Запускаем поиск в отдельном потоке
        threading.Thread(target=auto_search, args=(chat_id, game), daemon=True).start()
        return True
        
    except ValueError:
        return False

def auto_search(chat_id, game):
    """Автоматический поиск бомб"""
    user_role = get_user_role(game.user_id)
    
    # Начальное сообщение
    start_message = f"""
🔍 <b>ЗАПУСК ЭКСКЛЮЗИВНОГО ПОИСКА</b>

{user_role}
🎯 <b>Уровень:</b> {game.bomb_count} бомб
📊 <b>Статистика:</b> {game.bomb_count}💣 / {25-game.bomb_count}⭐

{game.create_grid()}

<b>🤖 Начинаем поиск...</b>
⏳ <i>Обновляется каждые 2 секунды</i>
    """
    
    game.last_message_id = send_telegram_message(chat_id, start_message, game.last_message_id)
    time.sleep(2)
    
    known_bombs = set(game.bomb_positions)
    
    while game.game_active and game.bombs_found < game.bomb_count and game.moves < 25:
        game.moves += 1
        
        # Выбор ячейки
        unopened = [i for i in range(1, 26) if i not in game.revealed_cells]
        if not unopened:
            break
            
        chosen_cell = choose_smart_cell(game, known_bombs)
        game.revealed_cells.append(chosen_cell)
        
        if chosen_cell in known_bombs:
            game.bombs_found += 1
            result_text = f"💣 <b>БОМБА НАЙДЕНА!</b> Ячейка {chosen_cell}"
            known_bombs.remove(chosen_cell)
        else:
            game.stars_found += 1
            result_text = f"⭐ <b>ЗВЕЗДА!</b> Ячейка {chosen_cell}"
        
        # Обновление сообщения
        progress_message = f"""
🔍 <b>ПОИСК - Ход #{game.moves}</b>

{user_role}
🔐 <b>ID:</b> <code>{game.user_id}</code>

{result_text}

{game.create_grid()}

📊 <b>Прогресс:</b>
💣 Бомб: {game.bombs_found}/{game.bomb_count}
⭐ Звезд: {game.stars_found}/{25-game.bomb_count}
▪️ Осталось: {25 - len(game.revealed_cells)}

🎯 <b>Эффективность:</b> {(game.bombs_found/game.moves)*100:.1f}%

⏳ <i>Следующее обновление через 2 секунды...</i>
        """
        
        game.last_message_id = send_telegram_message(chat_id, progress_message, game.last_message_id)
        time.sleep(2)
        
        if game.bombs_found == game.bomb_count:
            break
    
    # Финальный отчет
    send_final_report(chat_id, game)

def choose_smart_cell(game, known_bombs):
    """Умный выбор ячейки"""
    unopened = [i for i in range(1, 26) if i not in game.revealed_cells]
    
    # Приоритет безопасных ячеек
    if known_bombs:
        safe_cells = [cell for cell in unopened if cell not in known_bombs]
        if safe_cells:
            return random.choice(safe_cells)
    
    return random.choice(unopened)

def send_final_report(chat_id, game):
    """Отправка финального отчета"""
    user_role = get_user_role(game.user_id)
    
    # Собираем информацию о бомбах
    bomb_locations = []
    for bomb in game.bomb_positions:
        row = (bomb - 1) // 5 + 1
        col = (bomb - 1) % 5 + 1
        bomb_locations.append(f"• Ряд {row}, Колонка {col}")
    
    final_message = f"""
🎰 <b>ЭКСКЛЮЗИВНАЯ ИГРА ЗАВЕРШЕНА</b>

{user_role}
🔐 <b>ID:</b> <code>{game.user_id}</code>

{game.create_grid()}

📊 <b>Итоговые результаты:</b>
• Ходов сделано: {game.moves}
• Бомб найдено: {game.bombs_found}/{game.bomb_count}
• Звезд найдено: {game.stars_found}/{25-game.bomb_count}

💣 <b>Расположение бомб:</b>
{chr(10).join(bomb_locations)}

🎯 <b>Общая эффективность:</b> {(game.bombs_found/game.bomb_count)*100:.1f}%

✨ <i>Игра завершена! Напишите /play для новой игры</i>
    """
    
    send_telegram_message(chat_id, final_message)
    game.game_active = False
    
    # Очистка сессии
    if chat_id in bot_state['games']:
        del bot_state['games'][chat_id]
    if game.user_id in bot_state['active_sessions']:
        del bot_state['active_sessions'][game.user_id]

# ================== WEBHOOK HANDLERS ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    """Основной webhook для Telegram"""
    try:
        update = request.get_json()
        
        if 'message' in update:
            process_message(update['message'])
        elif 'callback_query' in update:
            process_callback(update['callback_query'])
            
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return jsonify({'status': 'error'}), 500

def process_message(message):
    """Обработка текстовых сообщений"""
    chat_id = message['chat']['id']
    user_id = str(message['from']['id'])
    text = message.get('text', '').strip()
    
    if text == '/start':
        welcome_message = f"""
🎰 <b>JETTON STAR BOT</b>

🔐 <b>Ваш ID:</b> <code>{user_id}</code>
👑 <b>Статус:</b> {get_user_role(user_id)}

{'✨ <b>Добро пожаловать в эксклюзивный бот!</b>' if is_authorized(user_id) else '❌ <b>ДОСТУП ЗАПРЕЩЕН</b>'}

<b>Команды:</b>
/play - Начать новую игру
        """
        send_telegram_message(chat_id, welcome_message)
        
    elif text == '/play':
        start_game_session(chat_id, user_id)
        
    elif chat_id in bot_state['games']:
        game = bot_state['games'][chat_id]
        if game.waiting_for_bombs and text in ['3', '10', '20']:
            process_level_selection(chat_id, game, text)

def process_callback(callback_query):
    """Обработка callback от кнопок"""
    chat_id = callback_query['message']['chat']['id']
    user_id = str(callback_query['from']['id'])
    data = callback_query['data']
    
    if not is_authorized(user_id):
        send_telegram_message(chat_id, "❌ Доступ запрещен!")
        return
    
    if chat_id in bot_state['games']:
        game = bot_state['games'][chat_id]
        
        if data.startswith('level_'):
            level = data.split('_')[1]
            if process_level_selection(chat_id, game, level):
                # Удаляем клавиатуру
                requests.post(f"{TELEGRAM_API}/editMessageReplyMarkup", json={
                    'chat_id': chat_id,
                    'message_id': callback_query['message']['message_id'],
                    'reply_markup': {'inline_keyboard': []}
                })

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервера"""
    return jsonify({
        'status': 'online',
        'active_games': len(bot_state['games']),
        'authorized_users': list(AUTHORIZED_USERS.keys()),
        'timestamp': time.time()
    })

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Установка webhook (вызывается один раз)"""
    webhook_url = request.args.get('url')
    if webhook_url:
        response = requests.post(f"{TELEGRAM_API}/setWebhook", json={'url': webhook_url})
        return jsonify(response.json())
    return jsonify({'error': 'No URL provided'})

# ================== ЗАПУСК СЕРВЕРА ==================
if __name__ == '__main__':
    logger.info("🚀 Запуск Jetton Star Bot...")
    logger.info(f"🔐 Авторизованные пользователи: {list(AUTHORIZED_USERS.keys())}")
    
    # Для локального тестирования
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
