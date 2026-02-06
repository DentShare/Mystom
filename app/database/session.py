from typing import AsyncGenerator
from app.database.base import async_session_maker


async def get_db() -> AsyncGenerator:
    """Dependency для получения сессии БД"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

