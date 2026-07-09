import sqlite3
from datetime import datetime, timedelta

DB_PATH = "shop_database.db"


def normalize_weight(weight):
    """Приводит вес к единому виду: 1.0 -> 1, 0,9 -> 0.9, 1г -> 1."""
    if weight is None:
        return None
    weight_str = (
        str(weight)
        .strip()
        .lower()
        .replace(",", ".")
        .replace("grams", "")
        .replace("gram", "")
        .replace("гр", "")
        .replace("г", "")
        .replace("g", "")
        .strip()
    )
    if not weight_str:
        return None
    try:
        value = float(weight_str)
        if value <= 0:
            return None
        if value.is_integer():
            return str(int(value))
        return str(value).rstrip("0").rstrip(".")
    except ValueError:
        return None


def normalize_tx_hash(tx_hash):
    """Нормализует TX hash для защиты от повторной выдачи по одному платежу."""
    if tx_hash is None:
        return ""
    value = "".join(str(tx_hash).strip().lower().split())
    for prefix in ("txid:", "tx:", "hash:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    if value.startswith("0x"):
        value = value[2:]
    return value


# ==================== VERIFIED USERS ====================

def is_user_verified(user_id):
    """Проверяет, прошёл ли пользователь anti-bot верификацию."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM verified_users WHERE user_id = ? LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def save_verified_user(user_id, username=None):
    """Сохраняет пользователя как прошедшего проверку."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO verified_users (user_id, username)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            verified_at = CURRENT_TIMESTAMP
        """,
        (user_id, username or ""),
    )
    conn.commit()
    conn.close()
    return True


# ==================== USER LANGUAGE ====================

def get_user_language(user_id):
    """Возвращает выбранный язык пользователя или None."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM user_languages WHERE user_id = ? LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_user_language(user_id, language):
    """Сохраняет выбранный язык пользователя."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_languages (user_id, language)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
        """,
        (user_id, language),
    )
    conn.commit()
    conn.close()
    return True


def get_all_verified_users():
    """Возвращает список всех верифицированных пользователей (user_id, username)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM verified_users ORDER BY verified_at DESC")
    users = cursor.fetchall()
    conn.close()
    return users


# ==================== ADMIN LOGIN ATTEMPTS ====================

def record_admin_login_attempt(user_id, success):
    """Записывает попытку входа админа. Возвращает кол-во неудачных попыток подряд."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin_login_attempts (user_id, success) VALUES (?, ?)",
        (user_id, 1 if success else 0),
    )
    conn.commit()
    if success:
        # Сбрасываем счётчик при успехе
        cursor.execute("DELETE FROM admin_login_attempts WHERE user_id = ? AND success = 0", (user_id,))
        conn.commit()
        conn.close()
        return 0
    # Считаем неудачные попытки за последние 24 часа
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM admin_login_attempts WHERE user_id = ? AND success = 0 AND attempted_at > ?",
        (user_id, since),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def is_admin_banned(user_id):
    """Проверяет, забанен ли пользователь за 3+ неудачных попыток за 24 часа."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM admin_login_attempts WHERE user_id = ? AND success = 0 AND attempted_at > ?",
        (user_id, since),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count >= 3


def clear_admin_ban(user_id):
    """Снимает бан (удаляет неудачные попытки)."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admin_login_attempts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ==================== RATE LIMITING (anti-spam) ====================

_rate_limit_cache = {}  # {user_id: [timestamp, timestamp, ...]}


def check_rate_limit(user_id, max_requests=2, window_seconds=1):
    """
    Проверяет rate limit. Возвращает True если пользователь превысил лимит.
    max_requests запросов за window_seconds секунд = бан на 3 секунды.
    """
    import time
    now = time.time()
    user_id = int(user_id)

    if user_id not in _rate_limit_cache:
        _rate_limit_cache[user_id] = []

    timestamps = _rate_limit_cache[user_id]
    # Очищаем старые записи (старше 3 секунд)
    timestamps[:] = [t for t in timestamps if now - t < 3]

    # Проверяем: если уже есть превышение, игнорируем
    recent = [t for t in timestamps if now - t < window_seconds]
    if len(recent) >= max_requests:
        return True  # Заблокирован

    timestamps.append(now)
    return False


def is_user_rate_limited(user_id):
    """Проверяет, находится ли пользователь в состоянии rate limit."""
    import time
    now = time.time()
    user_id = int(user_id)
    if user_id not in _rate_limit_cache:
        return False
    timestamps = _rate_limit_cache[user_id]
    recent_1s = [t for t in timestamps if now - t < 1]
    return len(recent_1s) >= 2


# ==================== TX HASH ====================

def get_tx_hash_usage(tx_hash):
    """Возвращает запись об уже сохранённом TX hash или None."""
    normalized_hash = normalize_tx_hash(tx_hash)
    if not normalized_hash:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT original_hash, normalized_hash, order_id, user_id, network, amount, status, created_at, updated_at
        FROM used_tx_hashes
        WHERE normalized_hash = ?
        """,
        (normalized_hash,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_tx_hash_usage(tx_hash, order_id, user_id, network, amount, status):
    """Сохраняет TX hash как использованный."""
    normalized_hash = normalize_tx_hash(tx_hash)
    if not normalized_hash:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO used_tx_hashes (normalized_hash, original_hash, order_id, user_id, network, amount, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_hash) DO UPDATE SET
            original_hash = excluded.original_hash,
            user_id = excluded.user_id,
            network = excluded.network,
            amount = excluded.amount,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        WHERE used_tx_hashes.order_id = excluded.order_id
        """,
        (normalized_hash, str(tx_hash).strip(), str(order_id), user_id, network, str(amount), status),
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# ==================== PRODUCTS / STOCK ====================

def add_product(category, product_name, weight, description, photo_id, added_by, district="Default"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    normalized_weight = normalize_weight(weight)
    cursor.execute(
        "INSERT INTO products (category, product_name, weight, description, photo_id, added_by, district) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (category, product_name, normalized_weight, description, photo_id, added_by, district)
    )
    conn.commit()
    conn.close()


def get_available_districts(product_name, weight=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    normalized_weight = normalize_weight(weight)
    if normalized_weight:
        cursor.execute(
            "SELECT DISTINCT district FROM products WHERE product_name = ? AND weight = ? AND is_sold = 0",
            (product_name, normalized_weight)
        )
    else:
        cursor.execute("SELECT DISTINCT district FROM products WHERE product_name = ? AND is_sold = 0", (product_name,))
    districts = [row[0] for row in cursor.fetchall()]
    conn.close()
    return districts


def get_all_available_districts():
    """Возвращает все районы, в которых есть хотя бы один товар в наличии."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT district FROM products WHERE is_sold = 0 ORDER BY district")
    districts = [row[0] for row in cursor.fetchall()]
    conn.close()
    return districts


def get_stock_by_district():
    """Возвращает словарь {район: [{product_name, weight, count}]}."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT district, product_name, weight, COUNT(*) as cnt
        FROM products WHERE is_sold = 0
        GROUP BY district, product_name, weight
        ORDER BY district, product_name
        """
    )
    result = {}
    for row in cursor.fetchall():
        district = row[0]
        if district not in result:
            result[district] = []
        result[district].append({
            "product_name": row[1],
            "weight": row[2],
            "count": row[3]
        })
    conn.close()
    return result


def get_available_product(product_name, district, weight=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    normalized_weight = normalize_weight(weight)
    if normalized_weight:
        cursor.execute(
            "SELECT id, photo_id, description FROM products WHERE product_name = ? AND district = ? AND weight = ? AND is_sold = 0 LIMIT 1",
            (product_name, district, normalized_weight)
        )
    else:
        cursor.execute(
            "SELECT id, photo_id, description FROM products WHERE product_name = ? AND district = ? AND is_sold = 0 LIMIT 1",
            (product_name, district)
        )
    product = cursor.fetchone()
    conn.close()
    return product


def mark_as_sold(product_id, order_id, user_id, product_name, amount, district, category="main"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if product_id:
        cursor.execute("UPDATE products SET is_sold = 1, order_id = ? WHERE id = ?", (order_id, product_id))
    cursor.execute(
        "INSERT INTO sales (order_id, user_id, product_name, amount, district, category) VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, user_id, product_name, amount, district, category)
    )
    conn.commit()
    conn.close()


def get_all_stock():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, product_name, weight, district, created_at FROM products WHERE is_sold = 0 ORDER BY product_name, weight, district, id")
    stock = cursor.fetchall()
    conn.close()
    return stock


def get_product_by_id(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, category, product_name, weight, description, district, photo_id, added_by, created_at FROM products WHERE id = ? AND is_sold = 0",
        (product_id,),
    )
    product = cursor.fetchone()
    conn.close()
    return product


def delete_product(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ? AND is_sold = 0", (product_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# ==================== SALES STATS ====================

def get_sales_stats(category=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if category:
        cursor.execute("SELECT SUM(amount), COUNT(*) FROM sales WHERE category = ?", (category,))
    else:
        cursor.execute("SELECT SUM(amount), COUNT(*) FROM sales")
    stats = cursor.fetchone()
    conn.close()
    return stats


def reset_all_stats():
    """Сбрасывает всю статистику продаж, зарплат и заказов."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sales")
    cursor.execute("DELETE FROM salary_records")
    cursor.execute("DELETE FROM delivery_assignments")
    conn.commit()
    conn.close()
    return True


# ==================== SALARY RECORDS ====================

def record_salary(order_id, user_id, role, amount, description=""):
    """Записывает начисление зарплаты."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO salary_records (order_id, user_id, role, amount, description) VALUES (?, ?, ?, ?, ?)",
        (order_id, user_id, role, amount, description)
    )
    conn.commit()
    conn.close()


def get_salary_stats(user_id=None, role=None):
    """Возвращает (total_amount, count) для зарплат."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = "SELECT SUM(amount), COUNT(*) FROM salary_records WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if role:
        query += " AND role = ?"
        params.append(role)
    cursor.execute(query, params)
    stats = cursor.fetchone()
    conn.close()
    return stats


# ==================== DELIVERY ASSIGNMENTS ====================

def create_delivery_assignment(order_id, client_id, delivery_address, total_amount):
    """Создаёт запись о доставке, ожидающей принятия."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO delivery_assignments (order_id, client_id, delivery_address, total_amount, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (order_id, client_id, delivery_address, total_amount)
    )
    conn.commit()
    conn.close()


def accept_delivery(order_id, courier_id):
    """Курьер принимает заказ."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE delivery_assignments SET courier_id = ?, status = 'accepted', accepted_at = CURRENT_TIMESTAMP
        WHERE order_id = ? AND status = 'pending'
        """,
        (courier_id, order_id)
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def complete_delivery(order_id, courier_id):
    """Курьер завершает доставку."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE delivery_assignments SET status = 'completed', completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ? AND courier_id = ? AND status = 'accepted'
        """,
        (order_id, courier_id)
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_delivery_assignment(order_id):
    """Возвращает запись о доставке."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM delivery_assignments WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_courier_deliveries(courier_id):
    """Возвращает все доставки курьера."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM delivery_assignments WHERE courier_id = ? ORDER BY created_at DESC",
        (courier_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== INIT DB ====================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Таблица товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            product_name TEXT,
            weight TEXT,
            description TEXT,
            district TEXT,
            photo_id TEXT,
            added_by INTEGER,
            is_sold INTEGER DEFAULT 0,
            order_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица продаж
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            user_id INTEGER,
            product_name TEXT,
            category TEXT,
            product_name_orig TEXT,
            amount REAL,
            district TEXT,
            sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица пользователей, прошедших anti-bot проверку
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица использованных TX hash
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_tx_hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalized_hash TEXT UNIQUE NOT NULL,
            original_hash TEXT NOT NULL,
            order_id TEXT,
            user_id INTEGER,
            network TEXT,
            amount TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица языков пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_languages (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'en'
        )
    ''')

    # Таблица попыток входа админа (для бана после 3 неудач)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            success INTEGER DEFAULT 0,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица зарплат
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS salary_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            user_id INTEGER,
            role TEXT,
            amount REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица доставок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS delivery_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            client_id INTEGER,
            courier_id INTEGER,
            delivery_address TEXT,
            total_amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accepted_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')

    # МИГРАЦИИ для существующих баз
    migrations = [
        "ALTER TABLE sales ADD COLUMN category TEXT",
        "ALTER TABLE products ADD COLUMN weight TEXT",
    ]
    for migration in migrations:
        try:
            cursor.execute(migration)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# Initialize database on import
init_db()
