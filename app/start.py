"""
Единая точка входа для Railway: по переменной SERVICE_TYPE запускается
либо только веб-админка, либо бот (с админкой в фоне). Не нужно менять Start Command в UI.

SERVICE_TYPE=web  → только python -m admin_webapp.run_web (порт из PORT)
SERVICE_TYPE не задан или =bot → alembic upgrade head, админка в фоне, затем бот
"""
import os
import subprocess
import sys


def main() -> None:
    service_type = (os.environ.get("SERVICE_TYPE") or "").strip().lower()

    if service_type == "web":
        # Только веб-админка: run_web сам читает PORT из окружения
        os.execv(sys.executable, [sys.executable, "-m", "admin_webapp.run_web"])
        return

    # Режим бота: миграции, админка в фоне, затем бот
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "admin_webapp.run_web"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        import asyncio
        from app.main import main as bot_main
        asyncio.run(bot_main())
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
