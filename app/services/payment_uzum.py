"""
Планируемая интеграция платёжной системы Uzum Click Pay (Узбекистан).

Сейчас подписка оформляется через администратора (перевод на карту).
После подключения Uzum Click Pay здесь будут:
- Создание платежа (create payment) по API Uzum Click
- Проверка статуса оплаты (callback или polling)
- Автоматическая активация подписки при успешной оплате (вызов логики установки tier + subscription_end_date)

Документация API: https://click.uz/ (или актуальный URL платёжной системы)
В .env потребуются: UZUM_CLICK_MERCHANT_ID, UZUM_CLICK_SERVICE_ID, UZUM_CLICK_SECRET_KEY (или аналог).
"""

# TODO: реализовать при подключении Uzum Click Pay
# async def create_subscription_payment(telegram_id: int, tier: int, months: int) -> str:
#     """Создать платёж, вернуть URL для перехода пользователя или invoice_id."""
#     ...
#
# async def check_payment_status(transaction_id: str) -> bool:
#     """Проверить статус платежа (успех/неуспех)."""
#     ...
#
# async def on_payment_success(transaction_id: str, user_id: int, tier: int, months: int):
#     """После успешной оплаты: обновить подписку в БД."""
#     ...
