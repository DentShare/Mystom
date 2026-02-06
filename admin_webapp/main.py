"""
Веб-админка MiniStom: список пользователей, уровни подписки, сроки.
Запуск из корня проекта: uvicorn admin_webapp.main:app --reload --port 8001
"""
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

app = FastAPI(title="MiniStom Admin")

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
        raise HTTPException(status_code=403, detail="Access denied")


@app.get("/api/me")
async def api_me(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Проверка авторизации: возвращает user_id если initData валиден и пользователь админ."""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing initData")
    user_id = validate_init_data(x_telegram_init_data, Config.BOT_TOKEN)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid initData")
    require_admin(user_id)
    return {"telegram_id": user_id, "ok": True}


@app.get("/api/users")
async def api_list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Список пользователей (только для админов)."""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing initData")
    user_id = validate_init_data(x_telegram_init_data, Config.BOT_TOKEN)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid initData")
    require_admin(user_id)

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
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing initData")
    admin_telegram_id = validate_init_data(x_telegram_init_data, Config.BOT_TOKEN)
    if admin_telegram_id is None:
        raise HTTPException(status_code=401, detail="Invalid initData")
    require_admin(admin_telegram_id)

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
async def index():
    path = STATIC_DIR / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
