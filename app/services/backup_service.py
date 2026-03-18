"""
Бэкап PostgreSQL: pg_dump → файл → отправка админам в Telegram.

Работает через DATABASE_URL. Запуск:
- Автоматический: фоновая задача каждые BACKUP_INTERVAL_HOURS часов
- Ручной: команда /backup (только для админов)
"""
import asyncio
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.types import FSInputFile

from app.config import Config

logger = logging.getLogger(__name__)

# Интервал бэкапов (из env или по умолчанию 24 часа)
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
# Максимальное количество локальных бэкапов (старые удаляются)
MAX_LOCAL_BACKUPS = int(os.getenv("MAX_LOCAL_BACKUPS", "3"))
# Директория для бэкапов
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/tmp/ministom_backups"))


def _parse_db_url(url: str) -> dict:
    """Извлекает host, port, dbname, user, password из DATABASE_URL."""
    # Убираем +asyncpg для парсинга
    clean = url.replace("+asyncpg", "").replace("postgres://", "postgresql://")
    parsed = urlparse(clean)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/ministom").lstrip("/"),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
    }


async def create_backup() -> Optional[Path]:
    """Создаёт SQL-дамп базы данных через pg_dump.

    Returns:
        Path к файлу дампа или None при ошибке.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    db = _parse_db_url(Config.DATABASE_URL)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ministom_backup_{timestamp}.sql"
    filepath = BACKUP_DIR / filename

    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]

    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", str(db["port"]),
        "-U", db["user"],
        "-d", db["dbname"],
        "--no-owner",
        "--no-acl",
        "-f", str(filepath),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            logger.error("pg_dump failed (code %d): %s", process.returncode, error_msg)
            return None

        size_mb = filepath.stat().st_size / (1024 * 1024)
        logger.info("Backup created: %s (%.1f MB)", filepath, size_mb)

        # Очистка старых бэкапов
        _cleanup_old_backups()

        return filepath

    except asyncio.TimeoutError:
        logger.error("pg_dump timeout (300s)")
        return None
    except FileNotFoundError:
        logger.error("pg_dump not found — установите postgresql-client")
        return None
    except Exception as e:
        logger.exception("Backup error: %s", e)
        return None


def _cleanup_old_backups():
    """Удаляет старые бэкапы, оставляя MAX_LOCAL_BACKUPS последних."""
    if not BACKUP_DIR.exists():
        return
    backups = sorted(
        BACKUP_DIR.glob("ministom_backup_*.sql"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[MAX_LOCAL_BACKUPS:]:
        try:
            old.unlink()
            logger.info("Deleted old backup: %s", old.name)
        except Exception as e:
            logger.warning("Failed to delete old backup %s: %s", old.name, e)


async def send_backup_to_admins(bot: Bot, filepath: Path) -> int:
    """Отправляет файл бэкапа всем админам. Возвращает количество успешных отправок."""
    if not Config.ADMIN_IDS:
        logger.warning("No ADMIN_IDS configured, backup not sent")
        return 0

    size_mb = filepath.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        # Telegram лимит 50 MB для документов
        for admin_id in Config.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Бэкап слишком большой ({size_mb:.1f} MB) для отправки через Telegram.\n"
                    f"Файл сохранён на сервере: `{filepath}`"
                )
            except Exception:
                pass
        return 0

    sent = 0
    caption = (
        f"💾 Бэкап БД MiniStom\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"📦 {size_mb:.1f} MB"
    )

    for admin_id in Config.ADMIN_IDS:
        try:
            doc = FSInputFile(filepath, filename=filepath.name)
            await bot.send_document(admin_id, doc, caption=caption)
            sent += 1
        except Exception as e:
            logger.warning("Failed to send backup to admin %s: %s", admin_id, e)
        await asyncio.sleep(0.1)

    return sent


async def run_backup_and_send(bot: Bot) -> str:
    """Полный цикл: создать бэкап + отправить админам. Возвращает статус."""
    filepath = await create_backup()
    if not filepath:
        return "❌ Ошибка создания бэкапа (pg_dump). Проверьте логи."

    sent = await send_backup_to_admins(bot, filepath)
    size_mb = filepath.stat().st_size / (1024 * 1024)
    return f"✅ Бэкап создан ({size_mb:.1f} MB), отправлен {sent} админам."


async def backup_scheduler(bot: Bot):
    """Фоновая задача: автоматический бэкап каждые BACKUP_INTERVAL_HOURS часов."""
    interval = BACKUP_INTERVAL_HOURS * 3600
    logger.info("Backup scheduler started: every %d hours", BACKUP_INTERVAL_HOURS)

    while True:
        try:
            await asyncio.sleep(interval)
            logger.info("Starting scheduled backup...")
            status = await run_backup_and_send(bot)
            logger.info("Scheduled backup: %s", status)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Backup scheduler error: %s", e)
            # Отправляем ошибку в мониторинг
            try:
                from app.services.error_monitor import error_monitor
                await error_monitor.report(e, context="backup scheduler")
            except Exception:
                pass
