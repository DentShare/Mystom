from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import User
from app.database.session import async_session_maker


class UserMiddleware(BaseMiddleware):
    """Middleware для получения пользователя из БД и добавления в data"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_user из события
        telegram_user: TelegramUser | None = None
        
        if hasattr(event, "from_user") and event.from_user:
            telegram_user = event.from_user
        elif hasattr(event, "message") and event.message and event.message.from_user:
            telegram_user = event.message.from_user
        elif hasattr(event, "callback_query") and event.callback_query and event.callback_query.from_user:
            telegram_user = event.callback_query.from_user
        
        if not telegram_user:
            return await handler(event, data)
        
        # Получаем пользователя из БД (сессия должна быть открыта во время handler!)
        async with async_session_maker() as session:
            stmt = select(User).where(User.telegram_id == telegram_user.id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            # Если пользователя нет, создаем нового (базовый уровень)
            if not user:
                full_name = (
                    f"{telegram_user.first_name or ''} {telegram_user.last_name or ''}".strip()
                    or "Не указано"
                )
                user = User(
                    telegram_id=telegram_user.id,
                    full_name=full_name,
                    subscription_tier=0  # Basic по умолчанию
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            
            data["user"] = user
            data["db_session"] = session
            
            # Handler выполняется ВНУТРИ блока — сессия открыта, commit сохранит данные
            return await handler(event, data)

