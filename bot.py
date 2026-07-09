import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Dict, List, Any

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from aiogram.exceptions import TelegramBadRequest

import database
import payments

# --- НАСТРОЙКИ / SETTINGS ---
BOT_TOKEN = "8819970524:AAERl6L3ZbfqOK32mKEGPPurvngKlCM0Fe0"
WEBAPP_URL = "https://http://localhost:8080"
CONFIG_FILE = "config.json"
ORDERS_FILE = "orders.jsonl"

ADMIN_PASSWORD = "04202019"
MAX_ADMINS = 3
MAX_COURIERS = 2
DELIVERY_FEE_USD = 10
DELIVERY_TIME_MINUTES = 100

# Капча: пользователь должен решить математический пример со стикерами
CAPTCHA_STICKERS = ["🍪", "🧁", "🍰", "🎂", "🍩"]

WALLETS = {
    "TRC20": "TMrhTfaS7tdwj9nGnW9ribofBFja78uZdy",
    "BEP20": "0xaE51B4EA48980eAe24F06015ed98E2F7E14f0d1E",
    "TON": "UQAxBM4SDbjU5k2SOzpU1b-06YSVHPyfOV1Tiafl7vFUT55_"
}

# --- МУЛЬТИЯЗЫЧНОСТЬ / I18N ---
LANGUAGES = {
    "ru": "Русский 🇷🇺",
    "en": "English 🇺🇸",
    "ko": "한국어 🇰🇷",
    "ja": "日本語 🇯🇵",
    "zh": "中文 🇨🇳",
}

I18N = {
    "welcome_verified": {
        "ru": "✅ Проверка пройдена! Выберите язык:",
        "en": "✅ Verification passed! Choose your language:",
        "ko": "✅ 인증 완료! 언어를 선택하세요:",
        "ja": "✅ 認証完了！言語を選択してください:",
        "zh": "✅ 验证通过！请选择语言:",
    },
    "language_set": {
        "ru": "🌐 Язык установлен: Русский\n\nДобро пожаловать в Ну... погоди...! 🐾",
        "en": "🌐 Language set: English\n\nWelcome to Ну... погоди...! 🐾",
        "ko": "🌐 언어 설정: 한국어\n\nНу... погоди...에 오신 것을 환영합니다! 🐾",
        "ja": "🌐 言語設定: 日本語\n\nНу... погоди...へようこそ！🐾",
        "zh": "🌐 语言已设置: 中文\n\n欢迎来到Ну... погоди...！🐾",
    },
    "captcha_prompt": {
        "ru": "🛡 Подтвердите, что вы человек.\n\nСколько {emoji} на картинке? Напишите число.",
        "en": "🛡 Confirm you are human.\n\nHow many {emoji} are in the image? Type the number.",
        "ko": "🛡 사람임을 확인하세요.\n\n이미지에 {emoji}가 몇 개 있나요? 숫자를 입력하세요.",
        "ja": "🛡 人間であることを確認してください。\n\n画像に{emoji}はいくつありますか？数字を入力してください。",
        "zh": "🛡 请确认您是人类。\n\n图片中有几个{emoji}？请输入数字。",
    },
    "captcha_wrong": {
        "ru": "❌ Неверно! Попробуйте ещё раз. Сколько {emoji}?",
        "en": "❌ Wrong! Try again. How many {emoji}?",
        "ko": "❌ 틀렸습니다! 다시 시도하세요. {emoji}가 몇 개?",
        "ja": "❌ 不正解！もう一度試してください。{emoji}はいくつ？",
        "zh": "❌ 错误！再试一次。有几个{emoji}？",
    },
    "open_shop": {
        "ru": "🛍 Открыть магазин",
        "en": "🛍 Open Shop",
        "ko": "🛍 상점 열기",
        "ja": "🛍 ショップを開く",
        "zh": "🛍 打开商店",
    },
    "help_btn": {
        "ru": "❓ Помощь",
        "en": "❓ Help",
        "ko": "❓ 도움말",
        "ja": "❓ ヘルプ",
        "zh": "❓ 帮助",
    },
    "help_header": {
        "ru": "🆘 **ПОДДЕРЖКА**\n\nНаши операторы:",
        "en": "🆘 **SUPPORT**\n\nOur operators:",
        "ko": "🆘 **지원**\n\n운영자:",
        "ja": "🆘 **サポート**\n\nオペレーター:",
        "zh": "🆘 **支持**\n\n我们的运营商:",
    },
    "no_operators": {
        "ru": "• Операторы пока не подключены.",
        "en": "• Operators are not connected yet.",
        "ko": "• 아직 운영자가 연결되지 않았습니다.",
        "ja": "• オペレーターはまだ接続されていません。",
        "zh": "• 运营商尚未连接。",
    },
    "delivery_address_ask": {
        "ru": "🚚 Вы выбрали доставку. Пожалуйста, отправьте адрес доставки:",
        "en": "🚚 You chose delivery. Please send the delivery address:",
        "ko": "🚚 배달을 선택하셨습니다. 배달 주소를 보내주세요:",
        "ja": "🚚 配達を選択しました。配達先住所を送信してください:",
        "zh": "🚚 您选择了配送。请发送配送地址:",
    },
    "delivery_address_saved": {
        "ru": "✅ Адрес сохранён: {address}",
        "en": "✅ Address saved: {address}",
        "ko": "✅ 주소 저장됨: {address}",
        "ja": "✅ 住所が保存されました: {address}",
        "zh": "✅ 地址已保存: {address}",
    },
    "admin_banned": {
        "ru": "🚫 Вы заблокированы на 24 часа после 3 неудачных попыток ввода пароля.",
        "en": "🚫 You are blocked for 24 hours after 3 failed password attempts.",
        "ko": "🚫 비밀번호 3회 실패로 24시간 차단되었습니다.",
        "ja": "🚫 パスワード3回失敗により24時間ブロックされています。",
        "zh": "🚫 密码错误3次后，您已被封禁24小时。",
    },
    "rate_limited": {
        "ru": "⏳ Слишком много запросов. Подождите несколько секунд.",
        "en": "⏳ Too many requests. Please wait a few seconds.",
        "ko": "⏳ 요청이 너무 많습니다. 몇 초 기다려주세요.",
        "ja": "⏳ リクエストが多すぎます。数秒お待ちください。",
        "zh": "⏳ 请求过多。请等待几秒钟。",
    },
    "courier_new_delivery": {
        "ru": "🚚 **НОВЫЙ ЗАКАЗ НА ДОСТАВКУ #{order_id}**\nАдрес: {address}\nСумма чека: {total} USDT\nВаш заработок: 10 USDT + 5% от чека\n\nНажмите кнопку чтобы принять заказ.",
        "en": "🚚 **NEW DELIVERY ORDER #{order_id}**\nAddress: {address}\nCheck total: {total} USDT\nYour earnings: 10 USDT + 5% of check\n\nPress the button to accept.",
        "ko": "🚚 **새 배달 주문 #{order_id}**\n주소: {address}\n총액: {total} USDT\n수입: 10 USDT + 수표의 5%\n\n수락하려면 버튼을 누르세요.",
        "ja": "🚚 **新しい配達注文 #{order_id}**\n住所: {address}\n合計: {total} USDT\n収入: 10 USDT + 伝票の5%\n\nボタンを押して受け入れてください。",
        "zh": "🚚 **新配送订单 #{order_id}**\n地址: {address}\n总额: {total} USDT\n收入: 10 USDT + 账单的5%\n\n按按钮接受。",
    },
    "courier_accepted": {
        "ru": "✅ Вы приняли заказ #{order_id}. После выполнения нажмите «Заказ выполнен».",
        "en": "✅ You accepted order #{order_id}. Press «Order completed» when done.",
        "ko": "✅ 주문 #{order_id}을 수락했습니다. 완료 후 «주문 완료»를 누르세요.",
        "ja": "✅ 注文 #{order_id}を受け入れました。完了したら「注文完了」を押してください。",
        "zh": "✅ 您已接受订单 #{order_id}。完成后按«订单完成»。",
    },
    "courier_completed": {
        "ru": "✅ Доставка #{order_id} завершена! Заработок начислен.",
        "en": "✅ Delivery #{order_id} completed! Earnings credited.",
        "ko": "✅ 배달 #{order_id} 완료! 수입이 적립되었습니다.",
        "ja": "✅ 配達 #{order_id}完了！収入が加算されました。",
        "zh": "✅ 配送 #{order_id} 完成！收入已计入。",
    },
    "stats_reset_ask": {
        "ru": "🔐 Для сброса статистики введите пароль администратора:",
        "en": "🔐 To reset statistics, enter the admin password:",
        "ko": "🔐 통계를 초기화하려면 관리자 비밀번호를 입력하세요:",
        "ja": "🔐 統計をリセットするには管理者パスワードを入力してください:",
        "zh": "🔐 要重置统计信息，请输入管理员密码:",
    },
    "stats_reset_done": {
        "ru": "✅ Вся статистика сброшена до нуля.",
        "en": "✅ All statistics have been reset to zero.",
        "ko": "✅ 모든 통계가 0으로 초기화되었습니다.",
        "ja": "✅ すべての統計がゼロにリセットされました。",
        "zh": "✅ 所有统计数据已重置为零。",
    },
}

RULES_TEXT = {
    "ru": """🌸 **ПРАВИЛА МАГАЗИНА НУ... ПОГОДИ...** 🌸

Добро пожаловать в **Ну... погоди...**! 🐾

━━━━━━━━━━━━━━━━━━━━
💳 **Оплата**
Мы принимаем оплату только в **USDT** в сетях:
**TRC20 / BEP20 / TON** 💎
Автоматическая проверка доступна для **BEP20** по TX hash.
━━━━━━━━━━━━━━━━━━━━
📍 **Доставка и получение**
✅ Заявка передается оператору сразу после оформления
✅ Выпечка готовится индивидуально 🧁
✅ Стоимость доставки: **10 USDT** 🚚
✅ Время доставки: до **100 минут** ⏱️
✅ Магазин работает 24/7 ♾️
✅ Зелёные галочки на сайте = наличие в районе 🟢
━━━━━━━━━━━━━━━━━━━━
🛟 **Поддержка**
Если есть вопросы — нажмите «Помощь» в меню.
━━━━━━━━━━━━━━━━━━━━
🔐 **Конфиденциальность**
Мы бережно относимся к вашим данным. 🤝

Спасибо, что выбираете **Ну... погоди...**! 💗""",

    "en": """🌸 **НУ... ПОГОДИ... SHOP RULES** 🌸

Welcome to **Ну... погоди...**! 🐾

━━━━━━━━━━━━━━━━━━━━
💳 **Payment**
We accept payments only in **USDT** using:
**TRC20 / BEP20 / TON** 💎
Automatic payment check is available for **BEP20** by TX hash.
━━━━━━━━━━━━━━━━━━━━
📍 **Delivery and Pickup**
✅ Order is sent to an operator immediately after checkout
✅ Bakery items are prepared individually 🧁
✅ Delivery cost: **10 USDT** 🚚
✅ Delivery time: up to **100 minutes** ⏱️
✅ Store is open 24/7 ♾️
✅ Green checkmarks on the site = available in that area 🟢
━━━━━━━━━━━━━━━━━━━━
🛟 **Support**
If you have questions — press «Help» in the menu.
━━━━━━━━━━━━━━━━━━━━
🔐 **Privacy**
We respect your privacy and keep your data confidential. 🤝

Thank you for choosing **Ну... погоди...**! 💗""",

    "ko": """🌸 **НУ... ПОГОДИ... 매장 규칙** 🌸

**Ну... погоди...**에 오신 것을 환영합니다! 🐾

━━━━━━━━━━━━━━━━━━━━
💳 **결제**
**USDT**로만 결제 가능:
**TRC20 / BEP20 / TON** 💎
**BEP20** TX hash로 자동 확인 가능.
━━━━━━━━━━━━━━━━━━━━
📍 **배달 및 픽업**
✅ 주문 후 즉시 운영자에게 전달
✅ 베이커리 제품은 개별 제작 🧁
✅ 배달비: **10 USDT** 🚚
✅ 배달 시간: 최대 **100분** ⏱️
✅ 24/7 운영 ♾️
✅ 사이트의 녹색 체크 = 해당 지역에서 이용 가능 🟢
━━━━━━━━━━━━━━━━━━━━
🛟 **지원**
질문이 있으면 메뉴에서 «도움말»을 누르세요.
━━━━━━━━━━━━━━━━━━━━
🔐 **개인정보**
귀하의 데이터를 안전하게 보호합니다. 🤝

**Ну... погоди...**를 선택해 주셔서 감사합니다! 💗""",

    "ja": """🌸 **НУ... ПОГОДИ...ショップルール** 🌸

**Ну... погоди...**へようこそ！🐾

━━━━━━━━━━━━━━━━━━━━
💳 **お支払い**
**USDT**のみ対応:
**TRC20 / BEP20 / TON** 💎
**BEP20** TX hashで自動確認可能。
━━━━━━━━━━━━━━━━━━━━
📍 **配達とピックアップ**
✅ 注文後すぐにオペレーターに転送
✅ ベーカリー商品は個別に準備 🧁
✅ 配達料: **10 USDT** 🚚
✅ 配達時間: 最大**100分** ⏱️
✅ 24時間営業 ♾️
✅ サイトの緑チェック = そのエリアで利用可能 🟢
━━━━━━━━━━━━━━━━━━━━
🛟 **サポート**
質問がある場合はメニューの「ヘルプ」を押してください。
━━━━━━━━━━━━━━━━━━━━
🔐 **プライバシー**
お客様のデータを安全に保護します。🤝

**Ну... погоди...**をお選びいただきありがとうございます！💗""",

    "zh": """🌸 **НУ... ПОГОДИ...商店规则** 🌸

欢迎来到**Ну... погоди...**！🐾

━━━━━━━━━━━━━━━━━━━━
💳 **支付**
仅接受**USDT**支付:
**TRC20 / BEP20 / TON** 💎
**BEP20** TX hash自动验证。
━━━━━━━━━━━━━━━━━━━━
📍 **配送和自取**
✅ 下单后立即转给运营商
✅ 烘焙产品单独制作 🧁
✅ 配送费: **10 USDT** 🚚
✅ 配送时间: 最多**100分钟** ⏱️
✅ 24/7营业 ♾️
✅ 网站上的绿色勾号 = 该区域有货 🟢
━━━━━━━━━━━━━━━━━━━━
🛟 **支持**
有问题请按菜单中的«帮助»。
━━━━━━━━━━━━━━━━━━━━
🔐 **隐私**
我们安全保护您的数据。🤝

感谢选择**Ну... погоди...**！💗""",
}

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("nu_pogodi_bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- FSM STATES ---
class AdminStates(StatesGroup):
    waiting_for_admin_password = State()
    waiting_for_photo = State()
    waiting_for_name = State()
    waiting_for_weight = State()
    waiting_for_district = State()
    waiting_for_quantity = State()
    waiting_for_delete_password = State()
    waiting_for_reset_password = State()
    waiting_for_broadcast_message = State()


class ClientStates(StatesGroup):
    waiting_for_captcha = State()
    choosing_districts = State()
    waiting_for_delivery_address = State()
    waiting_for_tx_hash = State()


# --- УТИЛИТЫ / UTILITIES ---
def get_user_lang(user_id) -> str:
    """Получает язык пользователя, по умолчанию 'en'."""
    lang = database.get_user_language(user_id)
    return lang if lang in LANGUAGES else "en"


def t(key: str, user_id, **kwargs) -> str:
    """Получает перевод по ключу и языку пользователя."""
    lang = get_user_lang(user_id)
    text = I18N.get(key, {}).get(lang, I18N.get(key, {}).get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text


def get_rules(user_id) -> str:
    """Получает правила на языке пользователя."""
    lang = get_user_lang(user_id)
    return RULES_TEXT.get(lang, RULES_TEXT["en"])


def _unique_int_list(values):
    result = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        config = {}
    operators = config.get("operators") or {}
    if not isinstance(operators, dict):
        operators = {}
    normalized = {
        "operators": {
            "bakery": _unique_int_list(operators.get("bakery", [])),
            "main": _unique_int_list(operators.get("main", [])),
            "courier": _unique_int_list(operators.get("courier", []))[:MAX_COURIERS],
        },
        "operator_usernames": config.get("operator_usernames") if isinstance(config.get("operator_usernames"), dict) else {},
        "admins": _unique_int_list(config.get("admins", []))[:MAX_ADMINS],
        "admin_usernames": config.get("admin_usernames") if isinstance(config.get("admin_usernames"), dict) else {},
    }
    return normalized


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return normalize_config(json.load(f))
    return normalize_config({})


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(normalize_config(config), f, ensure_ascii=False, indent=2)


def is_admin_user(user: types.User) -> bool:
    if not user:
        return False
    config = load_config()
    return int(user.id) in config.get("admins", [])[:MAX_ADMINS]


async def require_admin_message(message: types.Message, state: FSMContext = None) -> bool:
    if is_admin_user(message.from_user):
        return True
    if state:
        await state.clear()
    await message.answer(
        "🔒 Доступ только для администраторов. /admin\n"
        "🔒 Admins only. /admin"
    )
    return False


async def require_admin_callback(callback: types.CallbackQuery) -> bool:
    if is_admin_user(callback.from_user):
        return True
    await callback.answer("🔒 Admins only. /admin", show_alert=True)
    return False


def user_label(user) -> str:
    if hasattr(user, 'username') and user.username:
        return f"@{user.username}"
    uid = user.id if hasattr(user, 'id') else 'unknown'
    return f"ID {uid}"


def format_amount(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def district_label(district: str) -> str:
    if district == "Доставка":
        return "🚚 Delivery"
    if district == "Самовывоз":
        return "📦 Pickup"
    if district == "N/A":
        return "N/A"
    if not district:
        return "—"
    return district


def unit_label(unit: str) -> str:
    return "pc" if unit in ("pc", "шт") else "g"


def has_delivery(districts: List[str]) -> bool:
    return any(district == "Доставка" for district in districts or [])


def calculate_total(order: dict, districts: List[str]) -> float:
    order = order or {}
    items = order.get("items", []) or []
    total = 0.0
    used_item_prices = False
    for i, item in enumerate(items):
        district = districts[i] if i < len(districts) else item.get("district")
        if district == "N/A":
            continue
        if item.get("price") is None:
            continue
        try:
            total += float(item.get("price", 0)) * float(item.get("count", 1))
            used_item_prices = True
        except (TypeError, ValueError):
            continue
    if not used_item_prices:
        try:
            total = float(order.get("total", 0))
        except (TypeError, ValueError):
            total = 0.0
    payable_districts = [d for d in districts or [] if d != "N/A"]
    if has_delivery(payable_districts):
        total += DELIVERY_FEE_USD
    return total


def filter_payable_order(order: dict, districts: List[str]):
    order = dict(order or {})
    items = order.get("items", []) or []
    payable_items = []
    payable_districts = []
    skipped_items = []
    for i, item in enumerate(items):
        district = districts[i] if i < len(districts) else item.get("district")
        item_copy = dict(item or {})
        if district == "N/A":
            skipped_items.append(item_copy)
            continue
        item_copy["district"] = district
        payable_items.append(item_copy)
        payable_districts.append(district)
    order["items"] = payable_items
    order["total"] = format_amount(calculate_total(order, payable_districts))
    return order, payable_districts, skipped_items


def _safe_item_amount(item: dict) -> float:
    try:
        return float(item.get("price", 0)) * float(item.get("count", 1))
    except (TypeError, ValueError):
        return 0.0


# --- ГЕНЕРАЦИЯ КАПЧИ ---
def generate_captcha():
    """Генерирует капчу: строка из случайных эмодзи и вопрос 'сколько X?'"""
    emoji = random.choice(CAPTCHA_STICKERS)
    # Генерируем строку из 8-15 случайных эмодзи
    count = random.randint(2, 6)
    all_emojis = []
    for _ in range(count):
        all_emojis.append(emoji)
    # Добавляем другие эмодзи-обманки
    decoys = [e for e in CAPTCHA_STICKERS if e != emoji]
    decoy_count = random.randint(4, 9)
    for _ in range(decoy_count):
        all_emojis.append(random.choice(decoys))
    random.shuffle(all_emojis)
    captcha_text = " ".join(all_emojis)
    return captcha_text, emoji, count


# --- RATE LIMITER MIDDLEWARE ---
async def check_spam(message: types.Message) -> bool:
    """Возвращает True если пользователь спамит (2+ запроса в секунду)."""
    if not message.from_user:
        return False
    if is_admin_user(message.from_user):
        return False
    if database.check_rate_limit(message.from_user.id):
        return True
    return False


# --- ХРАНЕНИЕ ЗАЯВОК / ORDER STORAGE ---
def read_order_records() -> List[dict]:
    if not os.path.exists(ORDERS_FILE):
        return []
    records = []
    with open(ORDERS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def save_order_record(record: dict):
    records = [r for r in read_order_records() if str(r.get("order_id")) != str(record.get("order_id"))]
    records.append(record)
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        for item in records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def delete_order_record(order_id: str) -> bool:
    records = read_order_records()
    filtered = [r for r in records if str(r.get("order_id")) != str(order_id)]
    if len(filtered) == len(records):
        return False
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        for item in filtered:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return True


def update_order_payment_fields(order_id: str, status: str, network: str = None, tx_hash: str = None, payment_check: str = None) -> bool:
    records = read_order_records()
    found = False
    for record in records:
        if str(record.get("order_id")) == str(order_id):
            record["status"] = status
            if network:
                record["network"] = network
            if tx_hash:
                record["tx_hash"] = tx_hash
            if payment_check:
                record["payment_check"] = payment_check
            found = True
            break
    if not found:
        return False
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        for item in records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return True


def get_order_record(order_id: str) -> dict:
    for record in read_order_records():
        if str(record.get("order_id")) == str(order_id):
            return record
    return {}


def get_tx_hash_usage_from_orders(tx_hash: str) -> dict:
    normalized_hash = database.normalize_tx_hash(tx_hash)
    if not normalized_hash:
        return {}
    for record in read_order_records():
        if database.normalize_tx_hash(record.get("tx_hash")) == normalized_hash:
            return {
                "original_hash": record.get("tx_hash") or tx_hash,
                "normalized_hash": normalized_hash,
                "order_id": record.get("order_id"),
                "user_id": record.get("client_id"),
                "network": record.get("network"),
                "amount": record.get("total"),
                "status": record.get("status") or "saved",
                "created_at": record.get("created_at"),
            }
    return {}


def get_saved_tx_hash_usage(tx_hash: str) -> dict:
    return database.get_tx_hash_usage(tx_hash) or get_tx_hash_usage_from_orders(tx_hash)


def build_order_record(order_id, user, order, districts, total, status, network=None, tx_hash=None, payment_check=None):
    items_summary = []
    for i, item in enumerate(order.get("items", [])):
        category = item.get("category", "").lower()
        unit = item.get("unit") or ("pc" if category == "bakery" else "g")
        items_summary.append({
            "title": item.get("title", "Item"),
            "count": item.get("count"),
            "unit": unit,
            "district": districts[i] if i < len(districts) else item.get("district", "—"),
            "category": category or item.get("category"),
            "price": item.get("price"),
            "weight": item.get("weight"),
        })
    return {
        "order_id": order_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "client": user_label(user),
        "client_id": user.id if hasattr(user, 'id') else None,
        "total": total,
        "network": network,
        "tx_hash": tx_hash,
        "payment_check": payment_check,
        "comment": order.get("comment") or "—",
        "delivery_address": order.get("delivery_address") or "",
        "items": items_summary,
    }


# --- КЛАВИАТУРЫ / KEYBOARDS ---
def get_main_keyboard(user_id):
    lang = get_user_lang(user_id)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=I18N["open_shop"].get(lang, "🛍 Open Shop"), web_app=WebAppInfo(url=WEBAPP_URL))],
            [KeyboardButton(text=I18N["help_btn"].get(lang, "❓ Help"))],
        ],
        resize_keyboard=True,
    )


def get_language_keyboard():
    buttons = []
    for code, name in LANGUAGES.items():
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"lang_{code}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Склад / Stock", callback_data="view_stock"),
            InlineKeyboardButton(text="📈 Продажи / Sales", callback_data="view_sales"),
        ],
        [InlineKeyboardButton(text="🧾 Заявки / Orders", callback_data="view_orders")],
        [InlineKeyboardButton(text="💰 Зарплаты / Salaries", callback_data="view_salaries")],
        [InlineKeyboardButton(text="👨‍🍳 Стать оператором BAKERY", callback_data="reg_bakery")],
        [InlineKeyboardButton(text="📦 Стать оператором MAIN", callback_data="reg_main")],
        [InlineKeyboardButton(text="🚚 Стать доставщиком / Courier", callback_data="reg_courier")],
        [InlineKeyboardButton(text="🚫 Отключиться / Unregister", callback_data="unregister")],
        [InlineKeyboardButton(text="🔄 Сброс статистики / Reset stats", callback_data="reset_stats")],
    ])


def operator_status_text():
    config = load_config()
    bakery_count = len(config["operators"]["bakery"])
    main_count = len(config["operators"]["main"])
    courier_count = len(config["operators"]["courier"])
    admin_count = len(config.get("admins", []))
    return (
        f"🛠 **Панель управления / Control Panel**\n\n"
        f"👑 Админов / Admins: {admin_count}/{MAX_ADMINS}\n"
        f"👨‍🍳 Операторов Bakery: {bakery_count}\n"
        f"📦 Операторов Main: {main_count}\n"
        f"🚚 Доставщиков / Couriers: {courier_count}/{MAX_COURIERS}\n\n"
        f"Команды / Commands:\n"
        f"• /add — добавить товар на склад\n"
        f"• /stock — просмотр склада\n"
        f"• /orders — заявки\n"
        f"• /salaries — зарплаты\n"
        f"• /post — рассылка сообщения всем\n"
        f"• /add_courier <id> — добавить курьера"
    )


# --- ЛОГИКА ЗАРПЛАТ / SALARY LOGIC ---
def calculate_and_record_salaries(order_id: str, order: dict, districts: List[str], has_delivery_flag: bool, courier_id: int = None):
    """
    Рассчитывает и записывает зарплаты:
    - Bakery operator: 100% с выпечки + 15% с остальных позиций (без доставки)
    - Main operator: 85% без доставки, 80% с доставкой (5% идёт курьеру)
    - Courier: 10 USDT + 5% с чека (только если доставка)
    """
    config = load_config()
    items = order.get("items", []) or []

    bakery_total = 0.0
    main_total = 0.0

    for i, item in enumerate(items):
        category = (item.get("category") or "").lower()
        amount = _safe_item_amount(item)
        district = districts[i] if i < len(districts) else ""
        if district == "N/A":
            continue
        if category == "bakery":
            bakery_total += amount
        else:
            main_total += amount

    # Общая сумма чека без доставки
    check_total = bakery_total + main_total

    # Bakery operator: 100% с выпечки + 15% с main позиций
    bakery_ops = config["operators"].get("bakery", [])
    if bakery_ops and bakery_total > 0:
        bakery_salary = bakery_total + (main_total * 0.15)
        for op_id in bakery_ops:
            database.record_salary(order_id, op_id, "bakery", bakery_salary,
                                   f"100% bakery ({bakery_total}) + 15% main ({main_total * 0.15:.2f})")

    # Main operator: 85% если без доставки, 80% если с доставкой
    main_ops = config["operators"].get("main", [])
    if main_ops and main_total > 0:
        if has_delivery_flag:
            main_pct = 0.80
            desc = f"80% of main ({main_total})"
        else:
            main_pct = 0.85
            desc = f"85% of main ({main_total})"
        main_salary = main_total * main_pct
        for op_id in main_ops:
            database.record_salary(order_id, op_id, "main", main_salary, desc)

    # Courier: 10 USDT + 5% от чека
    if has_delivery_flag and courier_id:
        courier_salary = DELIVERY_FEE_USD + (check_total * 0.05)
        database.record_salary(order_id, courier_id, "courier", courier_salary,
                               f"10 USDT delivery + 5% of check ({check_total * 0.05:.2f})")


# --- УВЕДОМЛЕНИЯ / NOTIFICATIONS ---
async def notify_operators_new_order(user, order_id, order, districts, total, delivery_address=""):
    """Уведомляет операторов и админов о новой заявке."""
    config = load_config()
    operators = config.get("operators", {})
    items = order.get("items", [])
    comment = order.get("comment") or "—"
    client = user_label(user)
    is_delivery = has_delivery(districts)

    # Определяем кому слать: если есть bakery позиции — bakery оператору тоже
    has_bakery = any((item.get("category") or "").lower() == "bakery" for item in items)
    has_main = any((item.get("category") or "").lower() != "bakery" for item in items)

    # Если есть main позиции — уведомляем всех (main + bakery + admins)
    # Если только bakery — только bakery + admins
    if has_main:
        all_notify = set(operators.get("main", []) + operators.get("bakery", []) + config.get("admins", []))
    else:
        all_notify = set(operators.get("bakery", []) + config.get("admins", []))

    if not all_notify:
        return

    text = (
        f"🆕 **НОВАЯ ЗАЯВКА #{order_id}**\n"
        f"Клиент: {client}\n"
        f"Сумма: {total} USDT\n"
        f"Комментарий: {comment}\n"
    )
    if delivery_address:
        text += f"📍 Адрес доставки: {delivery_address}\n"
    text += "\n**Товары:**\n"

    for i, item in enumerate(items):
        category = item.get("category", "").lower()
        unit = item.get("unit") or ("pc" if category == "bakery" else "g")
        district = districts[i] if i < len(districts) else "—"
        text += f"• {item.get('title', 'Item')} x {item.get('count')}{unit_label(unit)} | {district_label(district)}\n"

    if is_delivery:
        text += f"\n🚚 Доставка: {DELIVERY_FEE_USD} USDT"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выдать товар / Issue goods", callback_data=f"issue_order_{order_id}")]
    ])

    for op_id in all_notify:
        try:
            await bot.send_message(op_id, text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify {op_id}: {e}")


async def notify_couriers_new_delivery(order_id, delivery_address, total):
    """Уведомляет доставщиков о новом заказе с доставкой."""
    config = load_config()
    couriers = config["operators"].get("courier", [])
    if not couriers:
        return

    text = (
        f"🚚 **НОВЫЙ ЗАКАЗ НА ДОСТАВКУ #{order_id}**\n"
        f"📍 Адрес: {delivery_address}\n"
        f"💰 Сумма чека: {total} USDT\n"
        f"💵 Ваш заработок: 10 USDT + 5% от чека\n\n"
        f"Нажмите кнопку чтобы принять заказ."
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принимаю заказ / Accept", callback_data=f"courier_accept_{order_id}")]
    ])

    for c_id in couriers:
        try:
            await bot.send_message(c_id, text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify courier {c_id}: {e}")


async def notify_operators_tx_hash(user, order_id, amount, network, tx_hash, check_result):
    config = load_config()
    operators = config.get("operators", {})
    all_notify = set(operators.get("main", []) + operators.get("bakery", []) + config.get("admins", []))
    if not all_notify:
        return
    paid = bool(check_result.get("paid"))
    status = "✅ оплата подтверждена" if paid else "⏳ нужна ручная проверка"
    reason = check_result.get("reason") or "—"
    text = (
        f"🔎 **TX HASH #{order_id}**\n"
        f"Статус: {status}\n"
        f"Клиент: {user_label(user)}\n"
        f"Сумма: {amount} USDT\n"
        f"Сеть: {network}\n"
        f"TX: `{tx_hash}`\n"
        f"Проверка: `{reason}`"
    )
    for op_id in all_notify:
        try:
            await bot.send_message(op_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify {op_id}: {e}")


async def notify_operators_duplicate_tx_hash(user, order_id, amount, network, tx_hash, existing_usage):
    config = load_config()
    operators = config.get("operators", {})
    all_notify = set(operators.get("main", []) + operators.get("bakery", []) + config.get("admins", []))
    if not all_notify:
        return
    text = (
        f"⛔ **ПОВТОРНЫЙ TX HASH**\n"
        f"Заявка: #{order_id}\n"
        f"Клиент: {user_label(user)}\n"
        f"TX: `{tx_hash}`\n"
        f"Уже использован для: #{existing_usage.get('order_id', '?')}"
    )
    for op_id in all_notify:
        try:
            await bot.send_message(op_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify {op_id}: {e}")


async def send_paid_order_to_operators(user, order_id, order, districts, amount, network, payment_check=None, tx_hash=None, delivery_address=""):
    """После оплаты отправляет копию заказа нужным операторам."""
    config = load_config()
    operators = config.get("operators", {})
    items = order.get("items", []) or []
    comment = order.get("comment") or "—"

    has_bakery = any((item.get("category") or "").lower() == "bakery" for item in items)
    has_main = any((item.get("category") or "").lower() != "bakery" for item in items)

    # Если есть main — всем, если только bakery — только bakery + admins
    if has_main:
        all_notify = set(operators.get("main", []) + operators.get("bakery", []) + config.get("admins", []))
    else:
        all_notify = set(operators.get("bakery", []) + config.get("admins", []))

    order_summary = (
        f"💰 **ОПЛАЧЕННЫЙ ЗАКАЗ #{order_id}**\n"
        f"Клиент: {user_label(user)}\n"
        f"Сумма: {amount} USDT | Сеть: {network}\n"
    )
    if tx_hash:
        order_summary += f"TX: `{tx_hash}`\n"
    if delivery_address:
        order_summary += f"📍 Адрес доставки: {delivery_address}\n"
    order_summary += f"Комментарий: {comment}\n\n**Товары:**\n"

    is_delivery = has_delivery(districts)
    for i, item in enumerate(items):
        category = (item.get("category") or "").lower()
        unit = item.get("unit") or ("pc" if category == "bakery" else "g")
        district = districts[i] if i < len(districts) else "—"
        order_summary += f"• {item.get('title', 'Item')} x {item.get('count')}{unit_label(unit)} | {district_label(district)}\n"

    if is_delivery:
        order_summary += f"\n🚚 Доставка: {DELIVERY_FEE_USD} USDT"

    for op_id in all_notify:
        try:
            await bot.send_message(op_id, order_summary, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to notify op {op_id}: {e}")


async def send_paid_order_items_and_notify(user, order_id, order, districts, amount, network, payment_check=None, tx_hash=None, delivery_address=""):
    """Выдаёт клиенту товары и уведомляет операторов.
    Если доставка — НЕ ищем товар на карте, просто отправляем чек операторам."""
    items = (order or {}).get("items", []) or []
    client_id = user.id if hasattr(user, 'id') else None
    is_delivery_order = has_delivery(districts) or bool(delivery_address)

    for i, item in enumerate(items):
        category = (item.get("category") or "").lower()
        title = item.get("title") or "Item"
        count = item.get("count") if item.get("count") is not None else item.get("weight", "")
        district = districts[i] if i < len(districts) else "—"
        item_amount = _safe_item_amount(item)

        # === ЕСЛИ ДОСТАВКА — не ищем на карте, просто записываем продажу ===
        if is_delivery_order:
            if category == "bakery":
                msg = (
                    f"🥨 **{title}** (🚚 Delivery)\n"
                    f"Will be ready after operator processing.\n"
                    f"🕒 Bakery hours: 9:00 - 21:00"
                )
                await bot.send_message(client_id, msg, parse_mode="Markdown")
            else:
                await bot.send_message(
                    client_id,
                    f"📦 **{title}** — operator will prepare your order for delivery.\n"
                    f"📍 Address: {delivery_address}"
                )
            database.mark_as_sold(None, order_id, client_id, title, item_amount, district, category=category)
            continue

        # === БЕЗ ДОСТАВКИ — ищем на карте как обычно ===
        if category != "bakery":
            weight = database.normalize_weight(item.get("weight", item.get("count")))
            prod = database.get_available_product(title, district, weight)
            if prod:
                weight_label = f" {weight}g" if weight else ""
                await bot.send_photo(
                    client_id,
                    prod[1],
                    caption=f"🎁 {title}{weight_label} ({district_label(district)})\n\n{prod[2]}",
                )
                database.mark_as_sold(prod[0], order_id, client_id, title, item_amount, district, category=category)
            else:
                await bot.send_message(
                    client_id,
                    f"⚠️ {title} in {district_label(district)} is out of stock. Operator will contact you."
                )
                database.mark_as_sold(None, order_id, client_id, title, item_amount, district, category=category)
        else:
            msg = (
                f"🥨 **{title}** ({district_label(district)})\n"
                f"Will be ready after operator processing.\n"
                f"🕒 Bakery hours: 9:00 - 21:00"
            )
            await bot.send_message(client_id, msg, parse_mode="Markdown")
            database.mark_as_sold(None, order_id, client_id, title, item_amount, district, category=category)

    # Уведомляем операторов
    await send_paid_order_to_operators(user, order_id, order, districts, amount, network, payment_check, tx_hash, delivery_address)

    # Если есть доставка — уведомляем курьеров
    if is_delivery_order and delivery_address:
        check_total = sum(_safe_item_amount(item) for i, item in enumerate(items) if (districts[i] if i < len(districts) else "") != "N/A")
        database.create_delivery_assignment(order_id, client_id, delivery_address, check_total)
        await notify_couriers_new_delivery(order_id, delivery_address, format_amount(check_total))

    # Рассчитываем зарплаты
    calculate_and_record_salaries(order_id, order, districts, is_delivery_order)


# --- ОБРАБОТЧИКИ / HANDLERS ---

# === КАПЧА И ВЕРИФИКАЦИЯ ===
def is_verified_or_admin(user: types.User) -> bool:
    if is_admin_user(user):
        return True
    if not user:
        return False
    return database.is_user_verified(user.id)


async def send_captcha(message: types.Message, state: FSMContext):
    """Отправляет капчу пользователю."""
    captcha_text, emoji, count = generate_captcha()
    await state.update_data(captcha_emoji=emoji, captcha_answer=count)
    await state.set_state(ClientStates.waiting_for_captcha)

    prompt = (
        f"🛡 **Проверка / Verification**\n\n"
        f"{captcha_text}\n\n"
        f"Сколько {emoji} вы видите? Напишите число.\n"
        f"How many {emoji} do you see? Type the number."
    )
    await message.answer(prompt, parse_mode="Markdown")


@dp.message(ClientStates.waiting_for_captcha)
async def handle_captcha_answer(message: types.Message, state: FSMContext):
    if await check_spam(message):
        return
    data = await state.get_data()
    correct = data.get("captcha_answer")
    emoji = data.get("captcha_emoji", "?")

    try:
        answer = int(message.text.strip())
    except (ValueError, TypeError, AttributeError):
        await message.answer(f"❌ Введите число. Сколько {emoji}?\n❌ Enter a number. How many {emoji}?")
        return

    if answer == correct:
        database.save_verified_user(message.from_user.id, message.from_user.username)
        await state.clear()
        # Показываем выбор языка
        await message.answer(
            "✅ Проверка пройдена! Выберите язык:\n"
            "✅ Verification passed! Choose language:",
            reply_markup=get_language_keyboard()
        )
    else:
        # Генерируем новую капчу
        captcha_text, new_emoji, new_count = generate_captcha()
        await state.update_data(captcha_emoji=new_emoji, captcha_answer=new_count)
        await message.answer(
            f"❌ Неверно!\n\n{captcha_text}\n\nСколько {new_emoji}? / How many {new_emoji}?",
            parse_mode="Markdown"
        )


@dp.callback_query(F.data.startswith("lang_"))
async def set_language_callback(callback: types.CallbackQuery, state: FSMContext):
    lang_code = callback.data.replace("lang_", "")
    if lang_code not in LANGUAGES:
        lang_code = "en"
    database.set_user_language(callback.from_user.id, lang_code)
    await state.clear()
    await callback.answer(f"Language: {LANGUAGES[lang_code]}", show_alert=False)
    try:
        await callback.message.edit_text(I18N["language_set"].get(lang_code, I18N["language_set"]["en"]))
    except TelegramBadRequest:
        pass
    # Показываем правила и главную клавиатуру
    rules = RULES_TEXT.get(lang_code, RULES_TEXT["en"])
    await callback.message.answer(rules, reply_markup=get_main_keyboard(callback.from_user.id), parse_mode="Markdown")


# === СТАРТ ===
@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    if await check_spam(m):
        return
    if not is_verified_or_admin(m.from_user):
        await send_captcha(m, state)
        return
    # Если нет языка — показать выбор
    if not database.get_user_language(m.from_user.id):
        await m.answer(
            "🌐 Выберите язык / Choose language:",
            reply_markup=get_language_keyboard()
        )
        return
    await m.answer(get_rules(m.from_user.id), reply_markup=get_main_keyboard(m.from_user.id), parse_mode="Markdown")


# === ПОМОЩЬ / HELP ===
@dp.message(Command("help"))
@dp.message(F.text.in_(["Помощь", "Help", "Помощь / Help", "❓ Помощь", "❓ Help", "❓ 도움말", "❓ ヘルプ", "❓ 帮助"]))
async def help_handler(message: types.Message):
    if await check_spam(message):
        return
    if not is_verified_or_admin(message.from_user):
        return

    config = load_config()
    usernames = config.get("operator_usernames", {})
    operators = config.get("operators", {})
    lang = get_user_lang(message.from_user.id)

    help_text = get_rules(message.from_user.id) + "\n\n"
    help_text += I18N["help_header"].get(lang, I18N["help_header"]["en"]) + "\n"

    # Показываем только операторов bakery и main, НЕ доставщиков
    shown = False
    bakery_ids = operators.get("bakery", [])
    main_ids = operators.get("main", [])
    visible_ids = set(bakery_ids + main_ids)

    for uid_str, username in usernames.items():
        if int(uid_str) in visible_ids:
            help_text += f"• @{username}\n"
            shown = True

    if not shown:
        help_text += I18N["no_operators"].get(lang, I18N["no_operators"]["en"])

    await message.answer(help_text, parse_mode="Markdown")


# === АДМИН-ВХОД ===
@dp.message(Command("admin"))
async def admin_cmd(m: types.Message, state: FSMContext):
    if await check_spam(m):
        return
    config = load_config()

    if is_admin_user(m.from_user):
        await m.answer(operator_status_text(), reply_markup=admin_keyboard(), parse_mode="Markdown")
        return

    # Проверяем бан
    if database.is_admin_banned(m.from_user.id):
        lang = get_user_lang(m.from_user.id)
        await m.answer(I18N["admin_banned"].get(lang, I18N["admin_banned"]["en"]))
        return

    if len(config.get("admins", [])) >= MAX_ADMINS:
        await m.answer(f"🚫 Admin limit reached: {MAX_ADMINS}/{MAX_ADMINS}.")
        return

    await state.set_state(AdminStates.waiting_for_admin_password)
    await m.answer(
        "🔐 Введите пароль администратора.\n"
        "🔐 Enter the admin password."
    )


@dp.message(AdminStates.waiting_for_admin_password)
async def admin_password_handler(message: types.Message, state: FSMContext):
    password = (message.text or "").strip()
    config = load_config()

    if is_admin_user(message.from_user):
        await state.clear()
        await message.answer(operator_status_text(), reply_markup=admin_keyboard(), parse_mode="Markdown")
        return

    if len(config.get("admins", [])) >= MAX_ADMINS:
        await state.clear()
        await message.answer(f"🚫 Admin limit: {MAX_ADMINS}/{MAX_ADMINS}.")
        return

    if password != ADMIN_PASSWORD:
        fail_count = database.record_admin_login_attempt(message.from_user.id, False)
        await state.clear()
        if fail_count >= 3:
            lang = get_user_lang(message.from_user.id)
            await message.answer(I18N["admin_banned"].get(lang, I18N["admin_banned"]["en"]))
        else:
            await message.answer(
                f"❌ Неверный пароль. Попытка {fail_count}/3. /admin\n"
                f"❌ Wrong password. Attempt {fail_count}/3. /admin"
            )
        return

    # Успешный вход
    database.record_admin_login_attempt(message.from_user.id, True)
    config["admins"].append(int(message.from_user.id))
    config["admin_usernames"][str(message.from_user.id)] = message.from_user.username or f"user_{message.from_user.id}"
    save_config(config)
    await state.clear()
    await message.answer(
        f"✅ You are now an admin. ({len(load_config().get('admins', []))}/{MAX_ADMINS})",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )


# === АДМИН: ДОБАВЛЕНИЕ ТОВАРА ===
@dp.message(Command("add"))
async def admin_add_start(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    await message.answer("📸 Отправьте фото товара с описанием.\n📸 Send item photo with description.")
    await state.set_state(AdminStates.waiting_for_photo)


@dp.message(AdminStates.waiting_for_photo, F.photo)
async def admin_add_photo(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    await state.update_data(photo_id=message.photo[-1].file_id, description=message.caption or "No description")
    await message.answer("🏷 Название товара / Item name:")
    await state.set_state(AdminStates.waiting_for_name)


@dp.message(AdminStates.waiting_for_name)
async def admin_add_name(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    await state.update_data(name=message.text)
    await message.answer("⚖️ Вес (число) / Weight (number):")
    await state.set_state(AdminStates.waiting_for_weight)


@dp.message(AdminStates.waiting_for_weight)
async def admin_add_weight(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    weight = database.normalize_weight(message.text)
    if not weight:
        return await message.answer("⚠️ Enter a valid number (e.g. 1, 3, 0.9)")
    await state.update_data(weight=weight)
    await message.answer("📍 Район / District:")
    await state.set_state(AdminStates.waiting_for_district)


@dp.message(AdminStates.waiting_for_district)
async def admin_add_district(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    await state.update_data(district=message.text)
    await message.answer("🔢 Количество / Quantity:")
    await state.set_state(AdminStates.waiting_for_quantity)


@dp.message(AdminStates.waiting_for_quantity)
async def admin_add_quantity(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    if not message.text.isdigit():
        return await message.answer("⚠️ Enter a number.")
    qty = int(message.text)
    if qty <= 0:
        return await message.answer("⚠️ Must be > 0.")
    data = await state.get_data()
    for _ in range(qty):
        database.add_product("main", data['name'], data['weight'], data['description'], data['photo_id'], message.from_user.id, data['district'])
    await message.answer(f"✅ Added {qty}x {data['name']} ({data['weight']}g) in {data['district']}")
    await state.clear()


# === АДМИН: СКЛАД ===
@dp.message(Command("stock"))
async def cmd_stock(message: types.Message):
    if not await require_admin_message(message):
        return
    await send_stock(message)


async def send_stock(target):
    stock = database.get_all_stock()
    if not stock:
        if isinstance(target, types.CallbackQuery):
            return await target.answer("Stock is empty.", show_alert=True)
        return await target.answer("📦 Stock is empty.")
    text = "📦 **СКЛАД / STOCK:**\n\n"
    buttons = []
    for item in stock:
        weight_text = f"{item[2]}g" if item[2] else "—"
        text += f"ID:{item[0]} | {item[1]} | {weight_text} | {item[3]}\n"
        buttons.append([InlineKeyboardButton(text=f"👁 {item[0]}: {item[1]}", callback_data=f"viewprod_{item[0]}")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons[:20])
    if isinstance(target, types.CallbackQuery):
        return await target.message.answer(text, reply_markup=markup, parse_mode="Markdown")
    return await target.answer(text, reply_markup=markup, parse_mode="Markdown")


@dp.callback_query(F.data == "view_stock")
async def view_stock_callback(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    await send_stock(callback)


# === АДМИН: ПРОДАЖИ ===
@dp.callback_query(F.data == "view_sales")
async def view_sales_callback(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    stats_all = database.get_sales_stats()
    stats_main = database.get_sales_stats("main")
    stats_bakery = database.get_sales_stats("bakery")
    text = (
        f"📈 **СТАТИСТИКА ПРОДАЖ / SALES:**\n\n"
        f"🌍 TOTAL: {stats_all[0] or 0} USDT | {stats_all[1] or 0} items\n"
        f"📦 MAIN: {stats_main[0] or 0} USDT | {stats_main[1] or 0} items\n"
        f"👨‍🍳 BAKERY: {stats_bakery[0] or 0} USDT | {stats_bakery[1] or 0} items"
    )
    await callback.message.answer(text, parse_mode="Markdown")


# === АДМИН: ЗАРПЛАТЫ ===
@dp.message(Command("salaries"))
async def cmd_salaries(message: types.Message):
    if not await require_admin_message(message):
        return
    await send_salaries(message)


@dp.callback_query(F.data == "view_salaries")
async def view_salaries_callback(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    await send_salaries(callback)


async def send_salaries(target):
    config = load_config()
    text = "💰 **ЗАРПЛАТЫ / SALARIES:**\n\n"

    for role in ["bakery", "main", "courier"]:
        ops = config["operators"].get(role, [])
        for op_id in ops:
            stats = database.get_salary_stats(user_id=op_id, role=role)
            total_earned = stats[0] or 0
            order_count = stats[1] or 0
            username = config.get("operator_usernames", {}).get(str(op_id), f"ID {op_id}")
            text += f"{'👨‍🍳' if role == 'bakery' else '📦' if role == 'main' else '🚚'} @{username} ({role}): {format_amount(total_earned)} USDT ({order_count} orders)\n"

    if isinstance(target, types.CallbackQuery):
        await target.message.answer(text, parse_mode="Markdown")
    else:
        await target.answer(text, parse_mode="Markdown")


# === АДМИН: ЗАЯВКИ ===
@dp.message(Command("orders"))
async def cmd_orders(message: types.Message):
    if not await require_admin_message(message):
        return
    await send_orders(message)


async def send_orders(target):
    records = read_order_records()
    if not records:
        if isinstance(target, types.CallbackQuery):
            return await target.answer("No orders yet.", show_alert=True)
        return await target.answer("🧾 No orders yet.")
    latest = records[-10:][::-1]
    text = "🧾 **ЗАЯВКИ / ORDERS:**\n\n"
    buttons = []
    for record in latest:
        status = record.get("status", "created")
        text += (
            f"#{record.get('order_id')} | {status}\n"
            f"Client: {record.get('client')} | {record.get('total')} USDT\n"
        )
        if record.get("delivery_address"):
            text += f"📍 {record.get('delivery_address')}\n"
        text += "\n"
        buttons.append([
            InlineKeyboardButton(text=f"✅ Issue {record.get('order_id')}", callback_data=f"issue_order_{record.get('order_id')}"),
            InlineKeyboardButton(text=f"🗑 Del", callback_data=f"delorder_{record.get('order_id')}"),
        ])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons[:10])
    if isinstance(target, types.CallbackQuery):
        return await target.message.answer(text, reply_markup=markup, parse_mode="Markdown")
    return await target.answer(text, reply_markup=markup, parse_mode="Markdown")


@dp.callback_query(F.data == "view_orders")
async def view_orders_callback(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    await send_orders(callback)


@dp.callback_query(F.data.startswith("delorder_"))
async def del_order(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    order_id = callback.data.replace("delorder_", "", 1)
    if delete_order_record(order_id):
        await callback.answer("Deleted.", show_alert=True)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    else:
        await callback.answer("Not found.", show_alert=True)


# === АДМИН: ПРОСМОТР И УДАЛЕНИЕ ТОВАРА ===
@dp.callback_query(F.data.startswith("viewprod_"))
async def view_product(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    p_id = callback.data.replace("viewprod_", "", 1)
    product = database.get_product_by_id(p_id)
    if not product:
        return await callback.answer("Not found.", show_alert=True)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Delete (password)", callback_data=f"del_{p_id}")]
    ])
    caption = (
        f"📦 ID: {product[0]}\n"
        f"Category: {product[1]}\n"
        f"Name: {product[2]}\n"
        f"Weight: {product[3] or '—'}g\n"
        f"District: {product[5]}\n"
        f"Desc: {product[4]}"
    )
    try:
        await callback.message.answer_photo(product[6], caption=caption, reply_markup=markup)
    except Exception:
        await callback.message.answer(caption, reply_markup=markup)
    await callback.answer()


@dp.callback_query(F.data.startswith("del_"))
async def request_delete_product_password(callback: types.CallbackQuery, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    p_id = callback.data.split("_", 1)[1]
    product = database.get_product_by_id(p_id)
    if not product:
        return await callback.answer("Not found.", show_alert=True)
    await state.update_data(delete_product_id=p_id)
    await state.set_state(AdminStates.waiting_for_delete_password)
    await callback.answer()
    await callback.message.answer(f"🔐 Enter admin password to delete ID {p_id}:")


@dp.message(AdminStates.waiting_for_delete_password)
async def delete_product_password_handler(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    password = (message.text or "").strip()
    data = await state.get_data()
    p_id = data.get("delete_product_id")
    if password != ADMIN_PASSWORD:
        await state.clear()
        return await message.answer("❌ Wrong password. Cancelled.")
    if database.delete_product(p_id):
        await message.answer(f"✅ Item ID {p_id} deleted.")
    else:
        await message.answer(f"⚠️ Item ID {p_id} not found.")
    await state.clear()


# === АДМИН: ВЫДАЧА ТОВАРА ===
@dp.callback_query(F.data.startswith("issue_order_"))
async def issue_order_from_admin(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    order_id = callback.data.replace("issue_order_", "", 1)
    record = get_order_record(order_id)
    if not record:
        return await callback.answer("Order not found.", show_alert=True)
    if record.get("status") in ("paid", "admin_issued"):
        return await callback.answer("Already issued.", show_alert=True)
    client_id = record.get("client_id")
    if not client_id:
        return await callback.answer("Client ID not found.", show_alert=True)

    order = {
        "items": record.get("items", []),
        "comment": record.get("comment") or "—",
        "total": record.get("total"),
        "delivery_address": record.get("delivery_address", ""),
    }
    districts = [item.get("district", "N/A") for item in order["items"]]
    client_user = SimpleNamespace(id=int(client_id), username=None)

    await send_paid_order_items_and_notify(
        client_user, order_id, order, districts,
        str(record.get("total") or "0"),
        record.get("network") or "admin",
        payment_check="admin_manual_issue",
        tx_hash=record.get("tx_hash"),
        delivery_address=record.get("delivery_address", ""),
    )

    updated_record = dict(record)
    updated_record["status"] = "admin_issued"
    save_order_record(updated_record)
    await callback.answer("Goods issued.", show_alert=True)


# === АДМИН: СБРОС СТАТИСТИКИ ===
@dp.callback_query(F.data == "reset_stats")
async def reset_stats_callback(callback: types.CallbackQuery, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.set_state(AdminStates.waiting_for_reset_password)
    await callback.answer()
    await callback.message.answer("🔐 Enter admin password to reset ALL statistics:")


@dp.message(AdminStates.waiting_for_reset_password)
async def reset_stats_password_handler(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    password = (message.text or "").strip()
    if password != ADMIN_PASSWORD:
        await state.clear()
        return await message.answer("❌ Wrong password. Reset cancelled.")
    database.reset_all_stats()
    # Также очищаем orders.jsonl
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        f.write("")
    await state.clear()
    lang = get_user_lang(message.from_user.id)
    await message.answer(I18N["stats_reset_done"].get(lang, I18N["stats_reset_done"]["en"]))


# === АДМИН: РАССЫЛКА /post ===
async def broadcast_message(text: str, from_user: types.User):
    """Отправляет сообщение всем верифицированным пользователям."""
    users = database.get_all_verified_users()
    sent = 0
    failed = 0
    for uid, username in users:
        try:
            await bot.send_message(
                uid,
                f"📢 Сообщение от администрации:\n\n{text}",
                parse_mode=None
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to broadcast to {uid}: {e}")
            failed += 1
    return sent, failed


@dp.message(Command("post"))
async def post_cmd(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    await state.set_state(AdminStates.waiting_for_broadcast_message)
    await message.answer(
        "📢 Введите текст сообщения для рассылки ВСЕМ пользователям магазина.\n"
        "📢 Enter the broadcast message for ALL shop users.\n\n"
        "Чтобы отменить — отправьте /cancel"
    )


@dp.message(AdminStates.waiting_for_broadcast_message)
async def broadcast_handler(message: types.Message, state: FSMContext):
    if not await require_admin_message(message, state):
        return
    text = (message.text or "").strip()
    if text.lower() in ("/cancel", "cancel", "отмена"):
        await state.clear()
        return await message.answer("❌ Рассылка отменена. / Broadcast cancelled.")
    if len(text) < 5:
        return await message.answer("⚠️ Сообщение слишком короткое (минимум 5 символов).")
    await message.answer("⏳ Отправляю сообщение всем верифицированным пользователям...")
    sent, failed = await broadcast_message(text, message.from_user)
    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена!\n"
        f"📨 Отправлено успешно: {sent}\n"
        f"❌ Не удалось доставить: {failed}"
    )


@dp.message(Command("add_courier"))
async def add_courier_cmd(message: types.Message):
    if not await require_admin_message(message):
        return
    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "🚚 Использование: /add_courier <user_id или @username>\n"
            "Примеры:\n"
            "• /add_courier 123456789\n"
            "• /add_courier @username\n\n"
            "Лимит курьеров: 2"
        )
        return

    identifier = args[1].strip()
    courier_id = None
    resolved_username = None

    # Если начинается с @ — это username
    if identifier.startswith("@"):
        username = identifier[1:]  # убираем @
        try:
            chat = await bot.get_chat(f"@{username}")
            courier_id = chat.id
            resolved_username = chat.username or username
        except Exception as e:
            return await message.answer(
                f"❌ Не удалось найти пользователя @{username}.\n"
                f"Убедись, что он хотя бы раз запускал бота (/start).\n"
                f"Ошибка: {str(e)[:100]}"
            )
    else:
        # Пробуем как числовой ID
        try:
            courier_id = int(identifier)
        except ValueError:
            return await message.answer("❌ Неверный формат. Используй числовой ID или @username.")

    if courier_id is None:
        return await message.answer("❌ Не удалось определить ID пользователя.")

    config = load_config()
    if courier_id in config["operators"].get("courier", []):
        return await message.answer("✅ Этот пользователь уже курьер.")

    if len(config["operators"].get("courier", [])) >= MAX_COURIERS:
        return await message.answer(f"🚫 Достигнут лимит курьеров: {MAX_COURIERS}/{MAX_COURIERS}")

    config["operators"]["courier"].append(courier_id)

    # Сохраняем username
    if resolved_username:
        config["operator_usernames"][str(courier_id)] = resolved_username
    else:
        try:
            chat = await bot.get_chat(courier_id)
            config["operator_usernames"][str(courier_id)] = chat.username or f"user_{courier_id}"
        except Exception:
            config["operator_usernames"][str(courier_id)] = f"user_{courier_id}"

    save_config(config)
    await message.answer(
        f"✅ Курьер добавлен!\n"
        f"ID: {courier_id}\n"
        f"Username: @{config['operator_usernames'].get(str(courier_id), 'неизвестен')}\n"
        f"Всего курьеров: {len(config['operators']['courier'])}/{MAX_COURIERS}"
    )


# === ОПЕРАТОРЫ: РЕГИСТРАЦИЯ ===
@dp.callback_query(F.data.startswith("reg_"))
async def register_operator(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    role = callback.data.replace("reg_", "")
    user_id = callback.from_user.id
    config = load_config()

    if role == "courier":
        if len(config["operators"]["courier"]) >= MAX_COURIERS:
            return await callback.answer(f"Courier limit: {MAX_COURIERS}/{MAX_COURIERS}", show_alert=True)
        if user_id in config["operators"]["courier"]:
            return await callback.answer("Already registered as courier.", show_alert=True)
        config["operators"]["courier"].append(user_id)
    elif role in ("bakery", "main"):
        if user_id in config["operators"][role]:
            return await callback.answer("Already registered.", show_alert=True)
        config["operators"][role].append(user_id)
    else:
        return await callback.answer("Unknown role.", show_alert=True)

    config["operator_usernames"][str(user_id)] = callback.from_user.username or f"user_{user_id}"
    save_config(config)
    await callback.answer(f"Registered as: {role}", show_alert=True)
    try:
        await callback.message.edit_text(operator_status_text(), reply_markup=admin_keyboard(), parse_mode="Markdown")
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "unregister")
async def unregister_callback(callback: types.CallbackQuery):
    if not await require_admin_callback(callback):
        return
    user_id = callback.from_user.id
    config = load_config()
    for role in config["operators"]:
        if user_id in config["operators"][role]:
            config["operators"][role].remove(user_id)
    if str(user_id) in config["operator_usernames"]:
        del config["operator_usernames"][str(user_id)]
    save_config(config)
    await callback.answer("Unregistered.", show_alert=True)
    try:
        await callback.message.edit_text(operator_status_text(), reply_markup=admin_keyboard(), parse_mode="Markdown")
    except TelegramBadRequest:
        pass


# === КУРЬЕР: ПРИНЯТИЕ И ЗАВЕРШЕНИЕ ДОСТАВКИ ===
@dp.callback_query(F.data.startswith("courier_accept_"))
async def courier_accept_order(callback: types.CallbackQuery):
    order_id = callback.data.replace("courier_accept_", "")
    courier_id = callback.from_user.id
    config = load_config()

    if courier_id not in config["operators"].get("courier", []):
        return await callback.answer("You are not a courier.", show_alert=True)

    if database.accept_delivery(order_id, courier_id):
        await callback.answer("Order accepted!", show_alert=True)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Заказ выполнен / Order completed", callback_data=f"courier_complete_{order_id}")]
        ])
        try:
            await callback.message.edit_reply_markup(reply_markup=markup)
        except TelegramBadRequest:
            pass

        # Уведомляем админов
        admins = config.get("admins", [])
        for admin_id in admins:
            try:
                await bot.send_message(
                    admin_id,
                    f"🚚 Курьер @{callback.from_user.username or courier_id} принял заказ #{order_id}.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    else:
        await callback.answer("Order already taken or not found.", show_alert=True)


@dp.callback_query(F.data.startswith("courier_complete_"))
async def courier_complete_order(callback: types.CallbackQuery):
    order_id = callback.data.replace("courier_complete_", "")
    courier_id = callback.from_user.id

    if database.complete_delivery(order_id, courier_id):
        # Начисляем зарплату курьеру
        delivery = database.get_delivery_assignment(order_id)
        if delivery:
            check_total = delivery.get("total_amount", 0)
            courier_salary = DELIVERY_FEE_USD + (check_total * 0.05)
            database.record_salary(order_id, courier_id, "courier", courier_salary,
                                   f"Delivery #{order_id}: 10 + 5% of {check_total}")

        await callback.answer("Delivery completed!", show_alert=True)
        try:
            await callback.message.edit_text(
                f"✅ Доставка #{order_id} завершена! Заработок начислен.\n"
                f"✅ Delivery #{order_id} completed! Earnings credited."
            )
        except TelegramBadRequest:
            pass

        # Уведомляем всех админов и курьера
        config = load_config()
        admins = config.get("admins", [])
        notification = (
            f"✅ **ДОСТАВКА ЗАВЕРШЕНА #{order_id}**\n"
            f"Курьер: @{callback.from_user.username or courier_id}"
        )
        for admin_id in admins:
            try:
                await bot.send_message(admin_id, notification, parse_mode="Markdown")
            except Exception:
                pass
    else:
        await callback.answer("Cannot complete. Not accepted or already done.", show_alert=True)


# === КЛИЕНТ: ЗАКАЗ ИЗ WEBAPP ===
@dp.message(F.web_app_data)
async def handle_order(message: types.Message, state: FSMContext):
    if await check_spam(message):
        return
    if not is_verified_or_admin(message.from_user):
        return
    try:
        data = json.loads(message.web_app_data.data)
        items = data.get("items", [])
        if not items:
            return
        # Проверяем есть ли галочка доставки
        wants_delivery = data.get("delivery", False)
        await state.update_data(
            order_data=data,
            current_item_index=0,
            chosen_districts=[],
            wants_delivery=wants_delivery,
        )
        await ask_for_district(message, state)
    except Exception as e:
        logger.error(f"Order error: {e}")
        await message.answer("⚠️ Error processing order. Try again.")


async def ask_for_district(message: types.Message, state: FSMContext):
    data = await state.get_data()
    index = data.get('current_item_index', 0)
    items = data['order_data']['items']
    wants_delivery = data.get('wants_delivery', False)

    if index >= len(items):
        # Все товары обработаны — если доставка, спрашиваем адрес
        if wants_delivery:
            lang = get_user_lang(message.chat.id)
            await bot.send_message(
                message.chat.id,
                I18N["delivery_address_ask"].get(lang, I18N["delivery_address_ask"]["en"])
            )
            await state.set_state(ClientStates.waiting_for_delivery_address)
            return
        return await show_final_receipt(message, state)

    item = items[index]
    category = item.get('category', '').lower()

    # === ЕСЛИ ДОСТАВКА — НЕ ИЩЕМ НА КАРТЕ, ставим "Доставка" для всех позиций ===
    if wants_delivery:
        chosen = data.get('chosen_districts', [])
        chosen.append("Доставка")
        await state.update_data(chosen_districts=chosen, current_item_index=index + 1)
        return await ask_for_district(message, state)

    # Без доставки — обычная логика
    if category == 'bakery':
        buttons = [
            [InlineKeyboardButton(text="🚚 Delivery", callback_data="dist_Доставка")],
            [InlineKeyboardButton(text="📦 Pickup", callback_data="dist_Самовывоз")],
        ]
        await bot.send_message(
            message.chat.id,
            f"🛒 **{item['title']}**\nChoose delivery or pickup:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="Markdown",
        )
    else:
        weight = database.normalize_weight(item.get('weight', item.get('count')))
        districts = database.get_available_districts(item['title'], weight)
        if not districts:
            chosen = data.get('chosen_districts', [])
            chosen.append("N/A")
            await state.update_data(chosen_districts=chosen, current_item_index=index + 1)
            await bot.send_message(
                message.chat.id,
                f"⚠️ **{item['title']}** ({weight}g) out of stock. Skipping.",
                parse_mode="Markdown",
            )
            return await ask_for_district(message, state)
        buttons = [[InlineKeyboardButton(text=d, callback_data=f"dist_{d}")] for d in districts]
        await bot.send_message(
            message.chat.id,
            f"🛒 **{item['title']}** ({weight}g)\nChoose district:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="Markdown",
        )


@dp.callback_query(F.data.startswith("dist_"))
async def process_district(callback: types.CallbackQuery, state: FSMContext):
    if await check_spam(callback.message):
        return
    district = callback.data.replace("dist_", "")
    data = await state.get_data()
    chosen = data.get('chosen_districts', [])
    chosen.append(district)
    await state.update_data(chosen_districts=chosen, current_item_index=data.get('current_item_index', 0) + 1)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await ask_for_district(callback.message, state)


@dp.message(ClientStates.waiting_for_delivery_address)
async def receive_delivery_address(message: types.Message, state: FSMContext):
    if await check_spam(message):
        return
    address = (message.text or "").strip()
    if not address or len(address) < 5:
        await message.answer("⚠️ Please enter a valid address (at least 5 characters).")
        return
    await state.update_data(delivery_address=address)
    data = await state.get_data()
    # Добавляем "Доставка" в districts если ещё нет
    chosen = data.get('chosen_districts', [])
    if not has_delivery(chosen):
        # Помечаем что доставка есть
        pass
    lang = get_user_lang(message.from_user.id)
    await message.answer(I18N["delivery_address_saved"].get(lang, "✅ Address saved.").format(address=address))
    await state.set_state(None)
    await show_final_receipt(message, state)


async def show_final_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    original_order = data['order_data']
    original_districts = data['chosen_districts']
    wants_delivery = data.get('wants_delivery', False)
    delivery_address = data.get('delivery_address', '')

    order, districts, skipped_items = filter_payable_order(original_order, original_districts)
    items = order['items']

    if not items:
        await state.clear()
        return await bot.send_message(
            message.chat.id,
            "⚠️ All items are out of stock. Please choose other items or contact support."
        )

    # Если доставка выбрана через галочку, добавляем fee
    if wants_delivery and not has_delivery(districts):
        # Добавляем доставку к сумме
        pass

    receipt = "🧾 **YOUR RECEIPT:**\n\n"
    if skipped_items:
        receipt += "⚠️ Out-of-stock items excluded.\n\n"

    for i, item in enumerate(items):
        unit = item.get('unit') or ("pc" if item.get('category', '').lower() == "bakery" else "g")
        receipt += f"• {item['title']} x {item['count']}{unit_label(unit)} | {district_label(districts[i])}\n"

    # Пересчитываем total с учётом доставки
    if wants_delivery:
        # Убеждаемся что доставка учтена
        order["_force_delivery"] = True

    total_val = 0.0
    for i, item in enumerate(items):
        if districts[i] != "N/A":
            total_val += _safe_item_amount(item)
    if wants_delivery:
        total_val += DELIVERY_FEE_USD
        receipt += f"\n🚚 Delivery: {DELIVERY_FEE_USD} USDT"
        if delivery_address:
            receipt += f"\n📍 Address: {delivery_address}"

    total = format_amount(total_val)
    order["total"] = total
    order["delivery_address"] = delivery_address

    receipt += f"\n\n💰 **TOTAL: {total} USDT**\n\nChoose payment network:"

    order_id = datetime.now().strftime("%Y%m%d%H%M%S")
    await state.update_data(order_id=order_id, final_total=total, order_data=order, chosen_districts=districts)
    save_order_record(build_order_record(order_id, message.from_user, order, districts, total, "created"))
    await notify_operators_new_order(message.from_user, order_id, order, districts, total, delivery_address)

    buttons = [
        [InlineKeyboardButton(text="TRC20", callback_data=f"pay_TRC20_{total}_{order_id}")],
        [InlineKeyboardButton(text="BEP20", callback_data=f"pay_BEP20_{total}_{order_id}")],
        [InlineKeyboardButton(text="TON", callback_data=f"pay_TON_{total}_{order_id}")],
    ]
    await bot.send_message(message.chat.id, receipt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")


# === ОПЛАТА ===
@dp.callback_query(F.data.startswith("pay_"))
async def start_payment(callback: types.CallbackQuery):
    if not is_verified_or_admin(callback.from_user):
        return
    parts = callback.data.split("_")
    if len(parts) < 4:
        return
    net, amount, oid = parts[1], parts[2], parts[3]
    wallet = WALLETS.get(net)
    text = (
        f"✅ Network: {net}\n"
        f"💵 Amount: `{amount}` USDT\n"
        f"📍 Wallet:\n`{wallet}`\n\n"
        f"After payment, press the button below and send TX hash.\n"
        f"Wait 1-2 minutes before sending TX hash."
    )
    btn = [
        [InlineKeyboardButton(text="🔎 Send TX hash", callback_data=f"hash_{net}_{amount}_{oid}")],
        [InlineKeyboardButton(text="🔍 Auto check", callback_data=f"check_{net}_{amount}_{oid}")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btn), parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data.startswith("hash_"))
async def ask_tx_hash(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 4:
        return
    net, amount, oid = parts[1], parts[2], parts[3]
    await state.update_data(payment_network=net, payment_amount=amount, payment_order_id=oid)
    await state.set_state(ClientStates.waiting_for_tx_hash)
    await callback.message.answer(
        f"🔎 Send TX hash for order #{oid}.\n"
        f"Network: {net} | Amount: {amount} USDT"
    )
    await callback.answer()


@dp.message(ClientStates.waiting_for_tx_hash)
async def receive_tx_hash(message: types.Message, state: FSMContext):
    if await check_spam(message):
        return
    tx_hash = (message.text or "").strip()
    if len(tx_hash) < 12:
        await message.answer("⚠️ This doesn't look like a TX hash. Please copy the full hash.")
        return

    data = await state.get_data()
    net = data.get("payment_network")
    amount = data.get("payment_amount")
    oid = data.get("payment_order_id")

    if not net or not amount or not oid:
        await state.clear()
        await message.answer("⚠️ Payment data expired. Please start over.")
        return

    # Проверяем дубликат
    existing_usage = get_saved_tx_hash_usage(tx_hash)
    if existing_usage:
        existing_order_id = str(existing_usage.get("order_id") or "")
        if existing_order_id != str(oid):
            await message.answer(f"⛔ TX hash already used for order #{existing_order_id}.")
            await notify_operators_duplicate_tx_hash(message.from_user, oid, amount, net, tx_hash, existing_usage)
            await state.clear()
            return
        if existing_usage.get("status") == "paid":
            await message.answer(f"⛔ TX hash already confirmed for order #{oid}.")
            await state.clear()
            return

    await message.answer("⏳ Checking TX hash...")
    check_result = await payments.check_payment_by_hash(net, WALLETS.get(net, ""), amount, tx_hash)
    paid = bool(check_result.get("paid"))
    status = "paid" if paid else "hash_received"
    reason = check_result.get("reason") or "unknown"

    if not database.save_tx_hash_usage(tx_hash, oid, message.from_user.id, net, amount, status):
        existing_usage = get_saved_tx_hash_usage(tx_hash) or {}
        await message.answer(f"⛔ TX hash already used for order #{existing_usage.get('order_id', '?')}.")
        await notify_operators_duplicate_tx_hash(message.from_user, oid, amount, net, tx_hash, existing_usage)
        await state.clear()
        return

    update_order_payment_fields(oid, status, network=net, tx_hash=tx_hash, payment_check=reason)
    await notify_operators_tx_hash(message.from_user, oid, amount, net, tx_hash, check_result)

    order = data.get("order_data")
    districts = data.get("chosen_districts", [])
    delivery_address = data.get("delivery_address", "") or (order or {}).get("delivery_address", "")

    if paid:
        await message.answer(f"✅ Payment confirmed! Order #{oid} is being processed.")
        if order:
            await send_paid_order_items_and_notify(
                message.from_user, oid, order, districts, amount, net,
                payment_check=reason, tx_hash=tx_hash, delivery_address=delivery_address
            )
        else:
            await message.answer("⚠️ Session expired. TX hash saved, operator will contact you.")
    else:
        await message.answer(
            f"🧾 TX hash saved and sent to operators for manual check.\n"
            f"Reason: {reason}"
        )
    await state.clear()


@dp.callback_query(F.data.startswith("check_"))
async def check_pay(callback: types.CallbackQuery, state: FSMContext):
    if not is_verified_or_admin(callback.from_user):
        return
    parts = callback.data.split("_")
    net, amount, oid = parts[1], parts[2], parts[3]
    await callback.answer("Checking... ⏳")

    is_paid = False
    if net == "TRC20":
        is_paid = await payments.check_tron_payment(WALLETS[net], amount)
    elif net == "BEP20":
        is_paid = await payments.check_bsc_payment(WALLETS[net], amount)
    elif net == "TON":
        is_paid = await payments.check_ton_payment(WALLETS[net], amount)

    if is_paid:
        data = await state.get_data()
        if not data or 'order_data' not in data:
            return await callback.message.answer("⚠️ Session expired. Contact support.")

        items = data['order_data']['items']
        districts = data['chosen_districts']
        delivery_address = data.get('delivery_address', '') or data.get('order_data', {}).get('delivery_address', '')

        await callback.message.edit_text("✅ Payment confirmed! Processing your order.")

        order = data['order_data']
        await send_paid_order_items_and_notify(
            callback.from_user, oid, order, districts, amount, net,
            payment_check="auto_wallet_history", delivery_address=delivery_address
        )
        save_order_record(build_order_record(oid, callback.from_user, order, districts, amount, "paid", network=net, payment_check="auto_wallet_history"))
        await state.clear()
    else:
        await callback.message.answer("❌ Payment not found. Try again in a minute.")


# === ОБЩИЙ ОБРАБОТЧИК ТЕКСТА (для кнопок клавиатуры) ===
@dp.message(F.text)
async def general_text_handler(message: types.Message, state: FSMContext):
    if await check_spam(message):
        return
    # Проверяем кнопки помощи на разных языках
    help_texts = [I18N["help_btn"].get(lang, "") for lang in LANGUAGES]
    if message.text in help_texts:
        await help_handler(message)
        return


# --- ЗАПУСК ---
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
