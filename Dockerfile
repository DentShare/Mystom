# MiniStom Telegram Bot — образ для Railway (с поддержкой WeasyPrint)
FROM python:3.11-slim-bookworm

WORKDIR /app

# Системные зависимости для WeasyPrint (Cairo, Pango, GDK-Pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY . .

# Миграции при старте; веб-админка слушает PORT (для Railway health check).
# Бот и админка в одном процессе: uvicorn в фоне, затем бот.
CMD ["sh", "-c", "alembic upgrade head && (python -m admin_webapp.run_web &) && python -m app.main"]
