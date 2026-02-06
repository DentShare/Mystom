from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import Config
from app.database.models import Base

# Создание асинхронного движка БД
engine = create_async_engine(
    Config.DATABASE_URL,
    echo=False,  # Установить True для отладки SQL запросов
    future=True,
    pool_pre_ping=True,   # Проверка соединения перед использованием (устойчивость к обрывам)
    pool_recycle=3600,    # Переподключение к БД каждые 60 мин (для долгой работы на сервере)
)

# Создание фабрики сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Инициализация базы данных (создание таблиц)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Закрытие соединения с БД"""
    await engine.dispose()

