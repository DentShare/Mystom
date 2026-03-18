import os
import ssl as ssl_module

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


def _get_ssl_context():
    """SSL-контекст для asyncpg: включается если DB_SSL=require или ?sslmode=require в URL."""
    db_ssl = os.getenv("DB_SSL", "").strip().lower()
    db_url = Config.DATABASE_URL or ""
    if db_ssl == "require" or "sslmode=require" in db_url:
        ctx = ssl_module.create_default_context()
        # Railway/managed DB: сертификат не проверяем (нет CA)
        ctx.check_hostname = False
        ctx.verify_mode = ssl_module.CERT_NONE
        return ctx
    return None


# Создание асинхронного движка БД (обязательно postgresql+asyncpg, иначе Railway подхватит psycopg2)
_db_url = _async_database_url(Config.DATABASE_URL)
if "+asyncpg" not in _db_url:
    raise RuntimeError(
        f"DATABASE_URL must use postgresql+asyncpg for async engine, got: {_db_url[:30]}..."
    )

_ssl_ctx = _get_ssl_context()
_connect_args = {"ssl": _ssl_ctx} if _ssl_ctx else {}

engine = create_async_engine(
    _db_url,
    echo=False,  # Установить True для отладки SQL запросов
    future=True,
    pool_pre_ping=True,   # Проверка соединения перед использованием (устойчивость к обрывам)
    pool_recycle=3600,    # Переподключение к БД каждые 60 мин (для долгой работы на сервере)
    connect_args=_connect_args,
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

