from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import Config
from app.database.models import Base


def _async_database_url(url: str) -> str:
    """Для async движка нужен asyncpg; postgres:// и postgresql:// приводим к postgresql+asyncpg://."""
    url = (url or "").strip()
    if "+asyncpg" in url:
        return url
    # Любой вариант postgres(ql) без asyncpg -> явно asyncpg (избегаем подхвата psycopg2)
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    return url


# Создание асинхронного движка БД (обязательно postgresql+asyncpg, иначе Railway подхватит psycopg2)
_db_url = _async_database_url(Config.DATABASE_URL)
assert "+asyncpg" in _db_url, "DATABASE_URL must use postgresql+asyncpg for async engine"
engine = create_async_engine(
    _db_url,
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

