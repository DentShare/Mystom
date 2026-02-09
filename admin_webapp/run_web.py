"""
Точка входа для веб-админки на Railway.
Читает PORT из окружения (Railway задаёт его), чтобы не зависеть от подстановки в shell.
Запуск: python -m admin_webapp.run_web
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "admin_webapp.main:app",
        host="0.0.0.0",
        port=port,
    )
