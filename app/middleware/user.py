from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import User, DoctorAssistant
from app.database.session import async_session_maker
from app.utils.permissions import full_permissions, normalize_permissions


class UserMiddleware(BaseMiddleware):
    """Middleware: пользователь из БД, effective_doctor и права ассистента."""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        telegram_user: TelegramUser | None = None
        if hasattr(event, "from_user") and event.from_user:
            telegram_user = event.from_user
        elif hasattr(event, "message") and event.message and event.message.from_user:
            telegram_user = event.message.from_user
        elif hasattr(event, "callback_query") and event.callback_query and event.callback_query.from_user:
            telegram_user = event.callback_query.from_user
        
        if not telegram_user:
            return await handler(event, data)
        
        async with async_session_maker() as session:
            stmt = select(User).where(User.telegram_id == telegram_user.id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                full_name = (
                    f"{telegram_user.first_name or ''} {telegram_user.last_name or ''}".strip()
                    or "Не указано"
                )
                user = User(
                    telegram_id=telegram_user.id,
                    full_name=full_name,
                    subscription_tier=0,
                    role="owner",
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            
            effective_doctor = user
            assistant_permissions = full_permissions()
            
            if getattr(user, "role", "owner") == "assistant" and getattr(user, "owner_id", None):
                stmt_owner = select(User).where(User.id == user.owner_id)
                res_owner = await session.execute(stmt_owner)
                owner = res_owner.scalar_one_or_none()
                if owner:
                    effective_doctor = owner
                    link_stmt = select(DoctorAssistant).where(
                        DoctorAssistant.doctor_id == owner.id,
                        DoctorAssistant.assistant_id == user.id,
                    )
                    link_res = await session.execute(link_stmt)
                    link = link_res.scalar_one_or_none()
                    if link and link.permissions:
                        assistant_permissions = normalize_permissions(link.permissions)
            
            data["user"] = user
            data["db_session"] = session
            data["effective_doctor"] = effective_doctor
            data["assistant_permissions"] = assistant_permissions
            return await handler(event, data)

