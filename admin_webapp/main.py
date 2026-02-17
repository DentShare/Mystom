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

from fastapi import FastAPI, Depends, HTTPException, Header, Request, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Config
from app.database.base import async_session_maker
from app.database.models import User, Patient, Appointment, Treatment

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
        logger.warning("[%s] 401: заголовок X-Telegram-Init-Data отсутствует или пустой", endpoint)
        raise HTTPException(status_code=401, detail="Missing initData")
    logger.info("[%s] initData получен, len=%d", endpoint, len(x_telegram_init_data))
    user_id = validate_init_data(x_telegram_init_data, Config.BOT_TOKEN)
    if user_id is None:
        logger.warning("[%s] 401: validate_init_data вернул None (неверная подпись или нет user)", endpoint)
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
    q: Optional[str] = Query(None, description="Поиск по имени, телефону или telegram_id"),
    tier: Optional[int] = Query(None, description="Фильтр по уровню подписки"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Список пользователей с поиском, фильтром и пагинацией."""
    _check_admin_auth("api_users", x_telegram_init_data, request.headers.get("host"))

    stmt = select(User)

    # Поиск
    if q and q.strip():
        search = f"%{q.strip()}%"
        # Если строка — число, ищем также по telegram_id
        if q.strip().isdigit():
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(search),
                    User.phone.ilike(search),
                    User.telegram_id == int(q.strip()),
                )
            )
        else:
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(search),
                    User.phone.ilike(search),
                )
            )

    # Фильтр по тарифу
    if tier is not None:
        stmt = stmt.where(User.subscription_tier == tier)

    # Общее количество (для пагинации)
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    # Данные с пагинацией
    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": [
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "full_name": u.full_name or "",
                "specialization": u.specialization or "",
                "phone": u.phone or "",
                "role": getattr(u, "role", "owner"),
                "subscription_tier": u.subscription_tier,
                "subscription_end_date": (
                    u.subscription_end_date.isoformat()[:10]
                    if u.subscription_end_date else None
                ),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


@app.get("/api/stats")
async def api_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Статистика проекта для дашборда."""
    _check_admin_auth("api_stats", x_telegram_init_data, request.headers.get("host"))

    # Кол-во пользователей по тарифам
    tier_counts = {}
    for tier_val in (0, 1, 2):
        r = await db.execute(
            select(func.count()).where(User.subscription_tier == tier_val)
        )
        tier_counts[tier_val] = r.scalar() or 0
    total_users = sum(tier_counts.values())

    # Кол-во пациентов, записей, лечений
    patients_count = (await db.execute(select(func.count()).select_from(Patient))).scalar() or 0
    appointments_count = (await db.execute(select(func.count()).select_from(Appointment))).scalar() or 0
    treatments_count = (await db.execute(select(func.count()).select_from(Treatment))).scalar() or 0

    return {
        "total_users": total_users,
        "tier_counts": {
            "basic": tier_counts[0],
            "standard": tier_counts[1],
            "premium": tier_counts[2],
        },
        "total_patients": patients_count,
        "total_appointments": appointments_count,
        "total_treatments": treatments_count,
    }


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
    admin_id = _check_admin_auth("api_update_user", x_telegram_init_data, request.headers.get("host"))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes = []
    if body.subscription_tier is not None:
        if body.subscription_tier not in (0, 1, 2):
            raise HTTPException(status_code=400, detail="tier must be 0, 1 or 2")
        if user.subscription_tier != body.subscription_tier:
            changes.append(f"tier: {user.subscription_tier} → {body.subscription_tier}")
        user.subscription_tier = body.subscription_tier
    if body.subscription_end_date is not None:
        old_date = user.subscription_end_date.isoformat()[:10] if user.subscription_end_date else "null"
        if body.subscription_end_date == "" or body.subscription_end_date.lower() == "null":
            user.subscription_end_date = None
            changes.append(f"end_date: {old_date} → null")
        else:
            try:
                user.subscription_end_date = datetime.strptime(
                    body.subscription_end_date.strip()[:10], "%Y-%m-%d"
                )
                changes.append(f"end_date: {old_date} → {body.subscription_end_date.strip()[:10]}")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="subscription_end_date must be YYYY-MM-DD",
                )

    if changes:
        logger.info(
            "AUDIT: admin=%s изменил user=%s (%s): %s",
            admin_id, user_id, user.full_name, "; ".join(changes),
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


# Health check для Railway (без авторизации)
@app.get("/health")
async def health():
    return {"status": "ok"}


# Временный диагностический эндпоинт (убрать после отладки)
@app.get("/api/debug_auth")
async def debug_auth(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Показывает шаги валидации initData без require_admin."""
    info: dict = {"step": "start", "bot_token_len": len(Config.BOT_TOKEN), "bot_token_set": bool(Config.BOT_TOKEN)}
    if not x_telegram_init_data:
        info["error"] = "no X-Telegram-Init-Data header"
        return info
    info["init_data_len"] = len(x_telegram_init_data)

    # Парсим ключи
    keys_found = []
    hash_present = False
    for part in x_telegram_init_data.split("&"):
        if "=" not in part:
            continue
        k, _, _ = part.partition("=")
        keys_found.append(k)
        if k == "hash":
            hash_present = True
    info["keys"] = keys_found
    info["hash_present"] = hash_present

    # Валидация
    user_id = validate_init_data(x_telegram_init_data, Config.BOT_TOKEN)
    info["user_id"] = user_id
    info["valid"] = user_id is not None
    if user_id is not None:
        info["is_admin"] = user_id in Config.ADMIN_IDS
        info["admin_ids"] = Config.ADMIN_IDS
    info["step"] = "done"
    return info


# Раздача статики (index.html и т.д.)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    host = request.headers.get("host", "(нет)")
    logger.info("GET / запрос, Host=%s", host)
    path = STATIC_DIR / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
