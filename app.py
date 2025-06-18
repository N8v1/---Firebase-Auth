# app.py

import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont # Убедимся, что ImageDraw и ImageFont импортированы здесь
import uuid

import firebase_admin
from firebase_admin import credentials, auth, firestore
from google.cloud.firestore_v1.base_query import FieldFilter # Для нового синтаксиса where

# --- Инициализация Firebase Admin SDK ---
try:
    # Указываем путь к файлу напрямую (замените, если нужно)
    cred = credentials.Certificate('D:\\Pythonproeckti\\Cora 2.5\\CoraChat copy\\corachat-86d89-firebase-adminsdk-fbsvc-c3b75443ee.json')
    if not firebase_admin._apps: # Проверяем, не инициализировано ли уже приложение
        firebase_admin.initialize_app(cred)
        print(f"{datetime.now()} [Firebase] SDK успешно инициализирован.")
    else:
        print(f"{datetime.now()} [Firebase] SDK уже был инициализирован.")
    db = firestore.client()
    print(f"{datetime.now()} [Firestore] Клиент успешно инициализирован.")
except Exception as e:
    print(f"{datetime.now()} [Firebase] КРИТИЧЕСКАЯ ОШИБКА инициализации SDK: {e}")
    db = None

# Определяем базовую директорию проекта
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Конфигурируем Flask
app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, 'static'),
    template_folder=os.path.join(BASE_DIR, 'templates')
)

app.config['SECRET_KEY'] = os.urandom(24)
app.config['USER_DATA_FOLDER'] = os.path.join(BASE_DIR, 'static', 'user_data')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
AVATAR_SIZE = (100, 100)
DEFAULT_AVATAR_BACKGROUND_COLOR = '#FFC0CB'
DEFAULT_AVATAR_TEXT_COLOR = '#000000'
DEFAULT_AVATAR_FILENAME = 'default_avatar.png' # Убедитесь, что этот файл есть в static/

socketio = SocketIO(app)

MESSAGES_DIR = os.path.join(BASE_DIR, 'messages')
KEY_FILE = os.path.join(BASE_DIR, 'key.key')

# --- Инициализация шифрования сообщений ---
def load_key():
    if not os.path.exists(KEY_FILE):
        print(f"{datetime.now()} [load_key] Файл ключа НЕ найден: {KEY_FILE}. Генерирую новый.")
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file: key_file.write(key)
        return key
    print(f"{datetime.now()} [load_key] Загрузка ключа из: {KEY_FILE}")
    with open(KEY_FILE, "rb") as key_file: return key_file.read()

encryption_key = load_key()
fernet = Fernet(encryption_key)

# Создание директорий
for dir_path in [MESSAGES_DIR, app.config['USER_DATA_FOLDER']]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"{datetime.now()} Создана директория: {dir_path}")

# --- Вспомогательные функции ---
def get_user_profile_from_firestore(uid):
    if not db:
        print(f"{datetime.now()} [get_user_profile_from_firestore] Firestore клиент не инициализирован для UID: {uid}.")
        return None
    try:
        print(f"{datetime.now()} [get_user_profile_from_firestore] Запрос профиля для UID: {uid}")
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()
        if user_doc.exists:
            print(f"{datetime.now()} [get_user_profile_from_firestore] Профиль для UID {uid} НАЙДЕН.")
            return user_doc.to_dict()
        else:
            print(f"{datetime.now()} [get_user_profile_from_firestore] Профиль для UID {uid} НЕ НАЙДЕН в Firestore.")
            return None
    except Exception as e:
        print(f"{datetime.now()} [get_user_profile_from_firestore] ИСКЛЮЧЕНИЕ при получении профиля для UID {uid}: {e}")
        return None

def generate_default_avatar_filename(uid, first_letter):
    return f"default_avatar_{uid}_{first_letter}.png"

def create_and_save_default_avatar_image(uid, first_letter):
    if not first_letter or not first_letter.strip():
        print(f"{datetime.now()} [create_and_save_default_avatar_image] Пустая первая буква для UID {uid}, аватар не создан.")
        return None
    try:
        user_folder_path = os.path.join(app.config['USER_DATA_FOLDER'], uid)
        if not os.path.exists(user_folder_path): os.makedirs(user_folder_path)

        filename = generate_default_avatar_filename(uid, first_letter)
        filepath = os.path.join(user_folder_path, filename)

        if os.path.exists(filepath): return filename

        img = Image.new('RGB', AVATAR_SIZE, color=DEFAULT_AVATAR_BACKGROUND_COLOR)
        try:
            font = ImageFont.truetype("arial.ttf", size=int(AVATAR_SIZE[1] * 0.7)) # Увеличил размер шрифта
        except IOError:
            font = ImageFont.load_default() 
            print(f"{datetime.now()} [create_and_save_default_avatar_image] Шрифт arial.ttf не найден, используется дефолтный.")


        draw = ImageDraw.Draw(img)
        try: # Новый API для textbbox
            bbox = draw.textbbox((0, 0), first_letter, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            draw_x = (AVATAR_SIZE[0] - text_width) / 2
            draw_y = (AVATAR_SIZE[1] - text_height) / 2 - bbox[1] # Учитываем смещение bbox[1]
        except AttributeError: # Старый API для textsize (если Pillow < 9.2.0)
             text_width, text_height = draw.textsize(first_letter, font=font)
             draw_x = (AVATAR_SIZE[0] - text_width) / 2
             draw_y = (AVATAR_SIZE[1] - text_height) / 2 * 0.8 # Примерная коррекция для старого API

        draw.text((draw_x, draw_y), first_letter, fill=DEFAULT_AVATAR_TEXT_COLOR, font=font)
        img.save(filepath, 'PNG')
        print(f"{datetime.now()} [create_default_avatar] Дефолтный аватар сохранен: {filepath}")
        return filename
    except Exception as e:
        print(f"{datetime.now()} [create_default_avatar] ИСКЛЮЧЕНИЕ создания дефолтного аватара для UID {uid}, буква '{first_letter}': {e}")
        return None

def get_user_avatar_url(uid, avatar_filename_from_db, display_name_for_default_avatar):
    if avatar_filename_from_db:
        path_for_url = os.path.join('user_data', uid, avatar_filename_from_db).replace("\\", "/")
        full_path = os.path.join(app.config['USER_DATA_FOLDER'], uid, avatar_filename_from_db)
        if os.path.exists(full_path):
            return url_for('static', filename=path_for_url)
        else:
            print(f"{datetime.now()} [get_user_avatar_url] Файл аватара '{avatar_filename_from_db}' НЕ найден: {full_path}")

    if display_name_for_default_avatar and display_name_for_default_avatar.strip():
        first_letter = display_name_for_default_avatar[0].upper()
        default_avatar_filename = create_and_save_default_avatar_image(uid, first_letter)
        if default_avatar_filename:
            return url_for('static', filename=os.path.join('user_data', uid, default_avatar_filename).replace("\\", "/"))
        else:
            print(f"{datetime.now()} [get_user_avatar_url] Не удалось создать/сохранить дефолтный аватар для UID {uid}")
    
    print(f"{datetime.now()} [get_user_avatar_url] Используется глобальный дефолтный аватар для UID {uid}.")
    return url_for('static', filename=DEFAULT_AVATAR_FILENAME)

def get_user_details(uid_or_at_username):
    start_time = datetime.now()
    if not db:
        print(f"{start_time} [get_user_details] Firestore клиент не инициализирован.")
        return None

    user_profile = None
    firebase_user_record = None
    user_uid = None
    print(f"{start_time} [get_user_details] Запрос деталей для: '{uid_or_at_username}'")

    if uid_or_at_username.startswith('@'):
        try:
            users_ref = db.collection('users').where(filter=FieldFilter('customUsername', '==', uid_or_at_username)).limit(1)
            docs = list(users_ref.stream())
            if docs:
                doc = docs[0]
                user_profile = doc.to_dict()
                user_uid = doc.id
                print(f"{datetime.now()} [get_user_details] Firestore: Найден профиль по customUsername '{uid_or_at_username}' для UID '{user_uid}'. Время: {(datetime.now() - start_time).total_seconds()}s")
            else:
                print(f"{datetime.now()} [get_user_details] Firestore: Пользователь с ником '{uid_or_at_username}' НЕ НАЙДЕН. Время: {(datetime.now() - start_time).total_seconds()}s")
                return None
        except Exception as e:
            print(f"{datetime.now()} [get_user_details] ИСКЛЮЧЕНИЕ Firestore (поиск по customUsername '{uid_or_at_username}'): {e}. Время: {(datetime.now() - start_time).total_seconds()}s")
            return None
    else:
        user_uid = uid_or_at_username
        user_profile = get_user_profile_from_firestore(user_uid) # Эта функция уже логирует
        if not user_profile:
             print(f"{datetime.now()} [get_user_details] Профиль Firestore для UID '{user_uid}' не найден. Будут использованы данные из Auth.")
             # Это нормально, если профиль еще не создан (например, сразу после регистрации Firebase)

    if not user_uid:
        print(f"{datetime.now()} [get_user_details] UID не определен для '{uid_or_at_username}'. Время: {(datetime.now() - start_time).total_seconds()}s")
        return None

    auth_start_time = datetime.now()
    try:
        firebase_user_record = auth.get_user(user_uid)
        print(f"{datetime.now()} [get_user_details] Firebase Auth: Пользователь для UID '{user_uid}' получен. Время: {(datetime.now() - auth_start_time).total_seconds()}s")
    except Exception as e:
        print(f"{datetime.now()} [get_user_details] ИСКЛЮЧЕНИЕ Firebase Auth (UID '{user_uid}'): {e}. Время: {(datetime.now() - auth_start_time).total_seconds()}s")
        if not user_profile: return None # Если нет ни данных Auth, ни профиля Firestore

    display_name = (user_profile.get('displayName') if user_profile 
                    else (firebase_user_record.display_name if firebase_user_record else None))
    if not display_name:
        display_name = (firebase_user_record.email.split('@')[0] if firebase_user_record and firebase_user_record.email else user_uid)

    at_username = user_profile.get('customUsername') if user_profile else None
    if not at_username:
        at_username = f"@{user_uid[:8]}" # Фоллбэк, если customUsername не найден в Firestore
        print(f"{datetime.now()} [get_user_details] customUsername не найден для UID '{user_uid}', используется временный: '{at_username}'")

    avatar_filename_from_db = user_profile.get('avatarFilename') if user_profile else None
    avatar_url = get_user_avatar_url(user_uid, avatar_filename_from_db, display_name)

    details = {
        'uid': user_uid, 'username': at_username, 'displayName': display_name,
        'email': (firebase_user_record.email if firebase_user_record 
                  else (user_profile.get('email') if user_profile else None)),
        'avatarUrl': avatar_url, 'avatarFilename': avatar_filename_from_db
    }
    print(f"{datetime.now()} [get_user_details] Финальные детали для '{uid_or_at_username}': {details}. Общее время: {(datetime.now() - start_time).total_seconds()}s")
    return details

def get_chat_filename(user1_at_username, user2_at_username):
    u1 = user1_at_username.lstrip('@'); u2 = user2_at_username.lstrip('@')
    return os.path.join(MESSAGES_DIR, "_".join(sorted([u1, u2])) + ".json")

def save_message(chat_file, sender_at_username, content, timestamp):
    messages = []
    if os.path.exists(chat_file):
        try:
            with open(chat_file, 'r', encoding='utf-8') as f: messages = json.load(f)
        except: messages = [] # Простая обработка ошибок чтения/декодирования
    encrypted_content = fernet.encrypt(content.encode()).decode()
    messages.append({"sender": sender_at_username, "content": encrypted_content, "timestamp": timestamp})
    try:
        with open(chat_file, 'w', encoding='utf-8') as f: json.dump(messages, f, indent=4, ensure_ascii=False)
    except Exception as e: print(f"{datetime.now()} [save_message] Ошибка записи в {chat_file}: {e}")

def load_messages(chat_file):
    if not os.path.exists(chat_file): return []
    try:
        with open(chat_file, 'r', encoding='utf-8') as f: encrypted_data = json.load(f)
        return [{"sender": m["sender"], "timestamp": m["timestamp"], 
                 "content": fernet.decrypt(m['content'].encode()).decode()}
                for m in encrypted_data]
    except Exception as e:
        print(f"{datetime.now()} [load_messages] Ошибка чтения/дешифрации {chat_file}: {e}")
        return []

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def process_and_save_avatar(file, user_uid):
    if file and allowed_file(file.filename):
        try:
            folder = os.path.join(app.config['USER_DATA_FOLDER'], user_uid); os.makedirs(folder, exist_ok=True)
            savename = f"avatar_{uuid.uuid4().hex}.png"; filepath = os.path.join(folder, savename)
            image = Image.open(file.stream)
            if image.mode not in ('RGB', 'RGBA'): image = image.convert('RGBA')
            elif image.mode == 'P': image = image.convert("RGBA")
            
            # Масштабирование и обрезка
            img_w, img_h = image.size; target_w, target_h = AVATAR_SIZE
            ratio_w, ratio_h = target_w / img_w, target_h / img_h
            scale = max(ratio_w, ratio_h)
            new_w, new_h = int(img_w * scale), int(img_h * scale)
            resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left, top = (new_w - target_w) / 2, (new_h - target_h) / 2
            cropped = resized.crop((left, top, left + target_w, top + target_h))
            
            cropped.save(filepath, 'PNG')
            print(f"{datetime.now()} [process_avatar] Аватар для UID {user_uid} сохранен: {filepath}")
            return savename
        except Exception as e:
            print(f"{datetime.now()} [process_avatar] ИСКЛЮЧЕНИЕ обработки аватара для UID {user_uid}: {e}")
    return None

# --- Маршруты Flask ---
@app.route('/')
def index():
    if 'firebase_token' in session and 'user_uid' in session: return redirect(url_for('chat'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        id_token = request.form.get('idToken')
        print(f"{datetime.now()} [login_page] POST. ID токен получен (первые 10 симв): {id_token[:10] if id_token else 'НЕТ'}")
        if not id_token: return render_template('login.html', error="ID токен не предоставлен.")
        try:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            print(f"{datetime.now()} [login_page] Токен верифицирован для UID: {uid}")
            session['firebase_token'] = id_token; session['user_uid'] = uid
            
            user_details = get_user_details(uid) # Получаем все детали (включая Firestore)
            if user_details:
                session['username'] = user_details['username']       # @customUsername
                session['displayName'] = user_details['displayName']
                session['avatarUrl'] = user_details['avatarUrl']
                print(f"{datetime.now()} [login_page] Детали пользователя для сессии Flask установлены: @{session['username']}, {session['displayName']}")
            else: # Крайний случай, если get_user_details вернул None (профиль не найден или ошибка)
                print(f"{datetime.now()} [login_page] ВНИМАНИЕ: get_user_details не вернул данные для UID {uid}. Попытка фоллбэка на данные Firebase Auth.")
                auth_user_rec = auth.get_user(uid) # Еще один запрос к Auth
                session['displayName'] = auth_user_rec.display_name or auth_user_rec.email.split('@')[0]
                session['username'] = f"@{uid[:8]}" # Временный ник, так как customUsername из Firestore не получен
                session['avatarUrl'] = get_user_avatar_url(uid, None, session['displayName'])
                print(f"{datetime.now()} [login_page] Фоллбэк сессия: @{session['username']}, {session['displayName']}")
            
            print(f"{datetime.now()} [login_page] Успешный вход для UID {uid}. Редирект на /chat.")
            return redirect(url_for('chat'))
        except firebase_admin.auth.InvalidIdTokenError:
            return render_template('login.html', error="Неверный ID токен Firebase.")
        except Exception as e:
            print(f"{datetime.now()} [login_page] ИСКЛЮЧЕНИЕ при входе: {e}")
            return render_template('login.html', error=f"Ошибка входа: {e}")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        id_token = request.form.get('idToken')
        custom_username = request.form.get('customUsername', '').strip()
        display_name = request.form.get('displayName', '').strip()
        avatar_file = request.files.get('avatar')
        print(f"{datetime.now()} [register_page] POST: customUsername='{custom_username}', displayName='{display_name}', avatar_exists={bool(avatar_file)}")

        if not all([id_token, custom_username, display_name]):
            return jsonify({"error": "Отсутствуют необходимые данные (токен, ник или имя)."}), 400
        if not custom_username.startswith('@') or len(custom_username) < 3: # @ + мин 2 символа
            return jsonify({"error": "Ник должен начинаться с @ и содержать мин. 2 символа после @."}), 400
        
        try:
            decoded_token = auth.verify_id_token(id_token); uid = decoded_token['uid']
        except Exception as e: return jsonify({"error": f"Ошибка верификации токена: {e}"}), 401
        if not db: return jsonify({"error": "Firestore не инициализирован."}), 500

        try: # Проверка уникальности customUsername
            docs = list(db.collection('users').where(filter=FieldFilter('customUsername', '==', custom_username)).limit(1).stream())
            if docs and docs[0].id != uid: return jsonify({"error": "Этот ник (@username) уже занят."}), 409
        except Exception as e: return jsonify({"error": "Ошибка проверки уникальности ника."}), 500

        avatar_filename = process_and_save_avatar(avatar_file, uid) if avatar_file and avatar_file.filename else None
        
        try: # Обновление displayName в Firebase Auth
            auth_user = auth.get_user(uid)
            if auth_user.display_name != display_name: auth.update_user(uid, display_name=display_name)
        except Exception as e: print(f"{datetime.now()} [register_page] Не удалось обновить displayName в Auth для UID {uid}: {e}")

        firestore_data = {'uid': uid, 'email': decoded_token.get('email'), 'displayName': display_name,
                          'customUsername': custom_username, 'registrationDate': firestore.SERVER_TIMESTAMP}
        if avatar_filename: firestore_data['avatarFilename'] = avatar_filename
        
        try:
            db.collection('users').document(uid).set(firestore_data, merge=True)
            print(f"{datetime.now()} [register_page] Профиль для UID {uid} сохранен в Firestore: {firestore_data}")
        except Exception as e: return jsonify({"error": f"Ошибка сохранения профиля в Firestore: {e}"}), 500

        # Установка сессии Flask
        session['firebase_token'] = id_token; session['user_uid'] = uid
        details = get_user_details(uid) # Получаем полные, только что сохраненные данные
        if details:
            session['username'] = details['username']; session['displayName'] = details['displayName']
            session['avatarUrl'] = details['avatarUrl']
            user_for_client = {'uid': uid, 'username': details['username'], 'displayName': details['displayName'], 'avatarUrl': details['avatarUrl']}
        else: # Если get_user_details не сработал (крайне маловероятно после успешной записи)
            print(f"{datetime.now()} [register_page] КРИТИЧЕСКАЯ ОШИБКА: get_user_details не вернул данные для UID {uid} сразу после регистрации!")
            session['username'] = custom_username; session['displayName'] = display_name
            session['avatarUrl'] = get_user_avatar_url(uid, avatar_filename, display_name) # Попытка сгенерировать URL
            user_for_client = {'uid': uid, 'username': custom_username, 'displayName': display_name, 'avatarUrl': session['avatarUrl']}

        print(f"{datetime.now()} [register_page] Успешная регистрация и вход для UID {uid} (@{session['username']}).")
        return jsonify({"message": "Регистрация завершена успешно!", "user": user_for_client}), 200

    return render_template('register.html')

@app.route('/chat')
def chat():
    if 'user_uid' not in session: return redirect(url_for('login_page'))
    uid = session['user_uid']
    print(f"{datetime.now()} [chat] Запрос страницы чата для UID: {uid}. Сессия: {session.items()}")
    
    user_s_details = get_user_details(uid)
    if not user_s_details: # Если профиль не найден или ошибка при его получении
        print(f"{datetime.now()} [chat] Не удалось получить user_s_details для UID {uid}. Очистка сессии и редирект.")
        session.clear(); return redirect(url_for('login_page'))
    
    # Обновляем данные в сессии, если они изменились
    session['username'] = user_s_details['username']
    session['displayName'] = user_s_details['displayName']
    session['avatarUrl'] = user_s_details['avatarUrl']
    
    print(f"{datetime.now()} [chat] Рендеринг chat.html для UID {uid} (@{session['username']}), displayName='{session['displayName']}', avatar='{session['avatarUrl']}'")
    return render_template('chat.html',
        current_user_username=session['username'], current_user_display_name=session['displayName'],
        current_user_avatar_url=session['avatarUrl'], current_user_uid=uid,
        DEFAULT_AVATAR_URL=url_for('static', filename=DEFAULT_AVATAR_FILENAME))

@app.route('/logout')
def logout():
    uid = session.pop('user_uid', 'N/A'); session.pop('firebase_token', None); session.clear()
    print(f"{datetime.now()} [logout] Пользователь UID {uid} вышел.")
    return redirect(url_for('login_page'))

@app.route('/search_users')
def search_users_route():
    if 'user_uid' not in session: return jsonify({"error": "Unauthorized"}), 401
    query = request.args.get('query', '').strip() # Не переводим в lower здесь, если Firestore case-sensitive
    current_uid = session['user_uid']
    if not query or not db: return jsonify([])
    
    results = []
    processed_uids = {current_uid} # Не ищем самого себя

    try:
        # Поиск по customUsername (должен быть >= query и <= query + очень большой символ Unicode)
        # Такой запрос требует индекса для customUsername
        normalized_query_username = query if query.startswith('@') else f"@{query}"
        username_ref = db.collection('users').where(filter=FieldFilter('customUsername', '>=', normalized_query_username)).where(filter=FieldFilter('customUsername', '<=', normalized_query_username + u'\uf8ff'))
        for doc in username_ref.stream():
            if doc.id not in processed_uids:
                details = get_user_details(doc.id) # Получаем полные данные
                if details: results.append(details); processed_uids.add(doc.id)
        
        # Поиск по displayName (аналогично)
        # Такой запрос требует индекса для displayName
        # Если Firestore не настроен на case-insensitive поиск, то 'Никита' и 'никита' - разные
        # Для лучшего поиска можно хранить displayName в нижнем регистре в отдельном поле.
        display_name_ref = db.collection('users').where(filter=FieldFilter('displayName', '>=', query)).where(filter=FieldFilter('displayName', '<=', query + u'\uf8ff'))
        for doc in display_name_ref.stream():
            if doc.id not in processed_uids: # Проверяем, не обработан ли уже этот UID
                # Дополнительная проверка на клиенте или здесь, если Firestore вернул слишком много
                user_data = doc.to_dict()
                if query.lower() in user_data.get('displayName','').lower(): # Фильтруем на совпадение по подстроке без учета регистра
                    details = get_user_details(doc.id)
                    if details: results.append(details); processed_uids.add(doc.id)

    except Exception as e:
        print(f"{datetime.now()} [search_users_route] ИСКЛЮЧЕНИЕ: {e}")
        return jsonify({"error": "Ошибка сервера при поиске."}), 500
    return jsonify(results)

@app.route('/get_chat_history/<partner_at_username>')
def get_chat_history(partner_at_username):
    if 'user_uid' not in session: return jsonify({"error": "Unauthorized"}), 401
    current_at_username = session['username']
    chat_file = get_chat_filename(current_at_username, partner_at_username)
    messages = load_messages(chat_file)
    for msg in messages: # Добавляем детали отправителя к каждому сообщению
        sender_details = get_user_details(msg['sender']) # msg['sender'] это @custom_username
        msg['senderDisplayName'] = sender_details['displayName'] if sender_details else msg['sender']
        msg['senderAvatarUrl'] = sender_details['avatarUrl'] if sender_details else url_for('static', filename=DEFAULT_AVATAR_FILENAME)
        msg['senderUid'] = sender_details['uid'] if sender_details else None
    partner_details = get_user_details(partner_at_username) # Детали партнера
    return jsonify({'messages': messages, 'partnerDetails': partner_details})

@app.route('/get_user_chats')
def get_user_chats_route():
    if 'user_uid' not in session: return jsonify({"error": "Unauthorized"}), 401
    current_at_username = session['username']
    partners = set()
    if not os.path.exists(MESSAGES_DIR): return jsonify([])
    
    no_at_current = current_at_username.lstrip('@')
    for fname in os.listdir(MESSAGES_DIR):
        if fname.endswith(".json"):
            parts = fname[:-5].split('_')
            if len(parts) == 2:
                u1, u2 = parts
                if u1 == no_at_current: partners.add(f"@{u2}")
                elif u2 == no_at_current: partners.add(f"@{u1}")
    
    chat_list = []
    for partner_uname in partners:
        details = get_user_details(partner_uname)
        if details:
            messages = load_messages(get_chat_filename(current_at_username, partner_uname))
            if messages:
                last_msg = messages[-1]
                content = last_msg.get('content', '')
                details['lastMessage'] = {'content': content[:30] + ('...' if len(content) > 30 else ''),
                                          'timestamp': last_msg.get('timestamp',''), 'sender': last_msg.get('sender','')}
            else: details['lastMessage'] = None
            chat_list.append(details)
    chat_list.sort(key=lambda x: x.get('lastMessage', {}).get('timestamp', '0'), reverse=True)
    return jsonify(chat_list)

# --- Обработчики SocketIO ---
@socketio.on('connect')
def handle_connect():
    if 'user_uid' not in session:
        print(f"{datetime.now()} [socket_connect] ОТКЛОНЕНО: нет user_uid в сессии. SID: {request.sid}")
        return False
    uid = session['user_uid']
    user_info = get_user_details(uid) # Обновляем данные сессии из Firestore/Auth
    if user_info:
        session['displayName'] = user_info['displayName']
        session['avatarUrl'] = user_info['avatarUrl']
        session['username'] = user_info['username'] # @customUsername
        join_room(uid) # Используем UID для комнаты
        print(f"{datetime.now()} [socket_connect] Пользователь UID '{uid}' (@{session['username']}) подключился к комнате UID. SID: {request.sid}")
        return True
    else: # Если get_user_details вернул None
        print(f"{datetime.now()} [socket_connect] ОТКЛОНЕНО: не удалось получить детали для UID {uid}. SID: {request.sid}")
        return False

@socketio.on('disconnect')
def handle_disconnect():
    if 'user_uid' in session:
        uid = session['user_uid']
        leave_room(uid) # Покидаем комнату по UID
        print(f"{datetime.now()} [socket_disconnect] Пользователь UID '{uid}' (@{session.get('username', 'N/A')}) отключился от комнаты UID. SID: {request.sid}")

@socketio.on('send_message')
def handle_send_message(data): # Ожидаем: {recipientUid, message, timestamp}
    if 'user_uid' not in session:
        emit('error', {'message': 'Вы не авторизованы.'}); return
    
    sender_uid = session['user_uid']
    sender_at_username = session['username'] # @customUsername отправителя

    recipient_uid = data.get('recipientUid')
    message_content = data.get('message')
    if not recipient_uid or not message_content:
        emit('error', {'message': 'Не указан получатель или текст сообщения.'}); return
    
    timestamp = data.get('timestamp', datetime.now().isoformat())

    recipient_info = get_user_details(recipient_uid)
    if not recipient_info or not recipient_info.get('username'):
        emit('error', {'message': 'Получатель не найден.'}); return
    recipient_at_username = recipient_info['username']

    chat_file = get_chat_filename(sender_at_username, recipient_at_username)
    save_message(chat_file, sender_at_username, message_content, timestamp)

    sender_info_for_payload = get_user_details(sender_uid) # Актуальные данные отправителя

    payload = {
        'sender': sender_info_for_payload['username'], 'senderUid': sender_uid,
        'senderDisplayName': sender_info_for_payload['displayName'], 'senderAvatarUrl': sender_info_for_payload['avatarUrl'],
        'recipient': recipient_at_username, 'recipientUid': recipient_uid,
        'content': message_content, 'timestamp': timestamp
    }
    socketio.emit('new_message', payload, room=recipient_uid) # В комнату получателя (по UID)
    socketio.emit('new_message', payload, room=sender_uid)    # И себе (в комнату по UID)
    print(f"{datetime.now()} [socket_send_message] UID {sender_uid} -> UID {recipient_uid} (@{recipient_at_username}): '{message_content[:20]}...'")

if __name__ == '__main__':
    print(f"Запуск Flask-SocketIO сервера. BASE_DIR: {BASE_DIR}")
    print(f"MESSAGES_DIR: {MESSAGES_DIR}; KEY_FILE: {KEY_FILE}")
    print(f"USER_DATA_FOLDER: {app.config['USER_DATA_FOLDER']}")
    print("Firebase SDK должен быть инициализирован.")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)