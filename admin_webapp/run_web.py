"""
Точка входа для веб-админки на Railway.
Читает PORT из окружения (Railway задаёт его), чтобы не зависеть от подстановки в shell.
Запуск: python -m admin_webapp.run_web
"""
import os
import sys
import uvicorn


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    print(f"[admin_webapp.run_web] Запуск uvicorn на 0.0.0.0:{port} (PORT из env)", flush=True)
    sys.stdout.flush()
    uvicorn.run(
        "admin_webapp.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
