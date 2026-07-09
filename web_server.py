"""
Веб-сервер для Pink Panther Mini App.
- Раздаёт index.html
- API /api/districts — возвращает доступные районы из БД
- API /api/stock — возвращает наличие по районам
- Rate limiting для защиты от DDoS
"""
import os
import time
import json
from collections import defaultdict
from aiohttp import web

import database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Rate Limiting ---
_request_log = defaultdict(list)  # {ip: [timestamp, ...]}
RATE_LIMIT_REQUESTS = 30  # максимум запросов
RATE_LIMIT_WINDOW = 10  # за N секунд
RATE_LIMIT_BAN_DURATION = 30  # бан на N секунд
_banned_ips = {}  # {ip: ban_until_timestamp}


def is_rate_limited(ip: str) -> bool:
    """Проверяет rate limit для IP."""
    now = time.time()

    # Проверяем бан
    if ip in _banned_ips:
        if now < _banned_ips[ip]:
            return True
        else:
            del _banned_ips[ip]

    # Очищаем старые записи
    _request_log[ip] = [t for t in _request_log[ip] if now - t < RATE_LIMIT_WINDOW]
    _request_log[ip].append(now)

    if len(_request_log[ip]) > RATE_LIMIT_REQUESTS:
        _banned_ips[ip] = now + RATE_LIMIT_BAN_DURATION
        return True

    return False


@web.middleware
async def rate_limit_middleware(request, handler):
    """Middleware для rate limiting."""
    ip = request.remote or request.headers.get("X-Forwarded-For", "unknown")
    if is_rate_limited(ip):
        return web.Response(
            status=429,
            text=json.dumps({"error": "Too many requests. Please wait."}),
            content_type="application/json"
        )
    response = await handler(request)
    return response


# --- Routes ---
async def index(request):
    html_path = os.path.join(BASE_DIR, 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return web.Response(text=content, content_type='text/html')


async def health(request):
    return web.Response(text='OK')


async def api_districts(request):
    """Возвращает список районов, в которых есть товар."""
    try:
        districts = database.get_all_available_districts()
        return web.json_response({"districts": districts})
    except Exception as e:
        return web.json_response({"districts": [], "error": str(e)})


async def api_stock(request):
    """Возвращает наличие товаров по районам."""
    try:
        stock = database.get_stock_by_district()
        return web.json_response({"stock": stock})
    except Exception as e:
        return web.json_response({"stock": {}, "error": str(e)})


# --- App setup ---
app = web.Application(middlewares=[rate_limit_middleware])
app.router.add_get('/', index)
app.router.add_get('/health', health)
app.router.add_get('/api/districts', api_districts)
app.router.add_get('/api/stock', api_stock)

# Serve static assets
assets_path = os.path.join(BASE_DIR, 'assets')
if os.path.exists(assets_path):
    app.router.add_static('/assets', assets_path)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080)
