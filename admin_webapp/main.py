"""
Веб-админка MiniStom: список пользователей, уровни подписки, сроки.
Запуск из корня проекта: uvicorn admin_webapp.main:app --reload --port 8001
"""
import logging
import sys
from pathlib import Path

# Запуск из корня проекта (e.g. python -m uvicorn admin_webapp.main:app)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Config
from app.database.base import async_session_maker
from app.database.models import User

from admin_webapp.auth import validate_init_data

# Логи в stdout, чтобы в Railway INFO не помечались как "error" (stderr = error в UI)
_log_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(_log_fmt))
logger = logging.getLogger("admin_webapp")
logger.setLevel(logging.INFO)
logger.addHandler(_handler)
logger.propagate = False

app = FastAPI(title="MiniStom Admin")

# Лог конфигурации при старте (для отладки)
def _mask_token(t: str) -> str:
    if not t or len(t) < 12:
        return "(пусто или слишком короткий)"
    return f"{t[:8]}...{t[-4:]} (len={len(t)})"

logger.info(
    "Конфигурация: BOT_TOKEN=%s, ADMIN_IDS=%s",
    "задан" if Config.BOT_TOKEN else "НЕ ЗАДАН",
    Config.ADMIN_IDS,
)
if Config.BOT_TOKEN:
    logger.info("BOT_TOKEN для сверки с ботом: %s", _mask_token(Config.BOT_TOKEN))

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


def require_admin(telegram_id: int) -> None:
    if telegram_id not in Config.ADMIN_IDS:
        logger.warning(
            "require_admin: доступ запрещён — telegram_id=%s не в ADMIN_IDS=%s",
            telegram_id,
            Config.ADMIN_IDS,
        )
        raise HTTPException(status_code=403, detail="Access denied")


def _check_admin_auth(
    endpoint: str,
    x_telegram_init_data: Optional[str],
    request_host: Optional[str] = None,
) -> int:
    """Проверка initData и прав админа. Возвращает telegram_id или raises HTTPException."""
    if request_host is not None:
        logger.info("[%s] запрос с Host=%s", endpoint, request_host)
    if not x_telegram_init_data:
        logger.warning("[%s] заголовок X-Telegram-Init-Data отсутствует", endpoint)
        raise HTTPException(status_code=401, detail="Missing initData")
    logger.info("[%s] initData получен, len=%d", endpoint, len(x_telegram_init_data))
    user_id = validate_init_data(x_telegram_init_data, Config.BOT_TOKEN)
    if user_id is None:
        logger.warning("[%s] validate_init_data вернул None", endpoint)
        raise HTTPException(status_code=401, detail="Invalid initData")
    require_admin(user_id)
    logger.info("[%s] авторизация OK, user_id=%s", endpoint, user_id)
    return user_id


@app.get("/api/me")
async def api_me(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Проверка авторизации: возвращает user_id если initData валиден и пользователь админ."""
    user_id = _check_admin_auth("api_me", x_telegram_init_data, request.headers.get("host"))
    return {"telegram_id": user_id, "ok": True}


@app.get("/api/users")
async def api_list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Список пользователей (только для админов)."""
    _check_admin_auth("api_users", x_telegram_init_data, request.headers.get("host"))

    result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(200)
    )
    users = list(result.scalars().all())
    return [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "full_name": u.full_name or "",
            "specialization": u.specialization or "",
            "subscription_tier": u.subscription_tier,
            "subscription_end_date": (
                u.subscription_end_date.isoformat()[:10]
                if u.subscription_end_date else None
            ),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class UpdateUserBody(BaseModel):
    subscription_tier: Optional[int] = None
    subscription_end_date: Optional[str] = None  # YYYY-MM-DD или null для "без срока"


@app.patch("/api/users/{user_id}")
async def api_update_user(
    user_id: int,
    body: UpdateUserBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Обновить уровень подписки и/или дату окончания (только админ)."""
    _check_admin_auth("api_update_user", x_telegram_init_data, request.headers.get("host"))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.subscription_tier is not None:
        if body.subscription_tier not in (0, 1, 2):
            raise HTTPException(status_code=400, detail="tier must be 0, 1 or 2")
        user.subscription_tier = body.subscription_tier
    if body.subscription_end_date is not None:
        if body.subscription_end_date == "" or body.subscription_end_date.lower() == "null":
            user.subscription_end_date = None
        else:
            try:
                user.subscription_end_date = datetime.strptime(
                    body.subscription_end_date.strip()[:10], "%Y-%m-%d"
                )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="subscription_end_date must be YYYY-MM-DD",
                )
    await db.commit()
    await db.refresh(user)
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "full_name": user.full_name,
        "subscription_tier": user.subscription_tier,
        "subscription_end_date": (
            user.subscription_end_date.isoformat()[:10]
            if user.subscription_end_date else None
        ),
    }


# Раздача статики (index.html и т.д.)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    logger.info("GET / запрос, Host=%s", request.headers.get("host", "(нет)"))
    path = STATIC_DIR / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
