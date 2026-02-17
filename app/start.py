"""
Единая точка входа для Railway: по переменной SERVICE_TYPE запускается
либо только веб-админка, либо бот (с админкой в фоне). Не нужно менять Start Command в UI.

SERVICE_TYPE=web  → только python -m admin_webapp.run_web (порт из PORT)
SERVICE_TYPE не задан или =bot → админка в фоне, миграции, затем бот
"""
import os
import subprocess
import sys
import time

# Логи в stdout для Railway
def _log(msg: str, *args: object) -> None:
    print(f"[app.start] {msg % args}", flush=True)


def main() -> None:
    service_type = (os.environ.get("SERVICE_TYPE") or "").strip().lower()
    port = os.environ.get("PORT", "не задан")

    if service_type == "web":
        _log("SERVICE_TYPE=web → запуск только веб-админки, PORT=%s", port)
        os.execv(sys.executable, [sys.executable, "-m", "admin_webapp.run_web"])
        return

    _log("Режим бота: веб в фоне (PORT=%s), затем миграции, затем бот", port)

    # 1) Сначала запускаем веб-админку — чтобы /health отвечал пока идут миграции
    proc = subprocess.Popen(
        [sys.executable, "-m", "admin_webapp.run_web"],
        stdout=None,
        stderr=None,
    )
    _log("Веб-админка запущена в фоне (PID=%s), порт из PORT=%s", proc.pid, port)

    # Даём uvicorn 2 сек на старт, чтобы /health был доступен для Railway
    time.sleep(2)

    # 2) Затем миграции (могут занять 10-30 сек)
    _log("Запуск миграций alembic upgrade head...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    _log("Миграции завершены")

    # 3) Запускаем бота
    try:
        import asyncio
        from app.main import main as bot_main
        asyncio.run(bot_main())
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
