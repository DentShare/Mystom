import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Явный путь к .env (работает при запуске из любой директории)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


class Config:
    """Конфигурация приложения"""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/ministom")
    
    # Admin
    ADMIN_IDS: List[int] = [
        int(admin_id.strip())
        for admin_id in os.getenv("ADMIN_IDS", "").split(",")
        if admin_id.strip().isdigit()
    ]
    # URL Web App админки (если задан — в /admin показывается кнопка)
    ADMIN_WEBAPP_URL: str = os.getenv("ADMIN_WEBAPP_URL", "").strip()
    
    # Timezone (опционально)
    TIMEZONE_API_KEY: str = os.getenv("TIMEZONE_API_KEY", "")

    # Покупка подписки: реквизиты для оплаты переводом
    PAYMENT_CARD: str = os.getenv("PAYMENT_CARD", "").strip()  # Номер карты или текст "по запросу"
    PAYMENT_RECEIVER: str = os.getenv("PAYMENT_RECEIVER", "").strip()  # Получатель (ФИО или название)
    ADMIN_CONTACT: str = os.getenv("ADMIN_CONTACT", "").strip()  # Контакт администратора: @username или ссылка
    # Тексты цен для отображения (например: "99 000 сум/мес" или "Бессрочно — 299 000")
    SUBSCRIPTION_STANDARD_PRICE: str = os.getenv("SUBSCRIPTION_STANDARD_PRICE", "по запросу")
    SUBSCRIPTION_PREMIUM_PRICE: str = os.getenv("SUBSCRIPTION_PREMIUM_PRICE", "по запросу")

    # Будущая интеграция Uzum Click Pay (пока не используется)
    # UZUM_CLICK_MERCHANT_ID: str = os.getenv("UZUM_CLICK_MERCHANT_ID", "")
    # UZUM_CLICK_SERVICE_ID: str = os.getenv("UZUM_CLICK_SERVICE_ID", "")
    # UZUM_CLICK_SECRET_KEY: str = os.getenv("UZUM_CLICK_SECRET_KEY", "")

    @classmethod
    def validate(cls) -> bool:
        """Проверка обязательных параметров"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не установлен в .env")
        if not cls.DATABASE_URL:
            raise ValueError("DATABASE_URL не установлен в .env")
        return True

