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

# Единая точка входа: SERVICE_TYPE=web — только админка, иначе бот + админка в фоне.
# В Railway для сервиса «только админка» задайте переменную SERVICE_TYPE=web, Start Command не меняйте.
CMD ["python", "-m", "app.start"]
