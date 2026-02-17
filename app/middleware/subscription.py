from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.dispatcher.flags import get_flag

from app.database.models import User
from app.utils.constants import TIER_NAMES


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для проверки уровня подписки через флаги хендлеров"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем требуемый уровень подписки из флагов хендлера
        required_tier = get_flag(data, "tier")
        
        # Если флаг не установлен, функция доступна всем
        if required_tier is None:
            return await handler(event, data)
        
        # Уровень подписки берём у effective_doctor (врач/владелец), чтобы ассистент имел доступ по тарифу врача
        user: User | None = data.get("user")
        effective_doctor: User | None = data.get("effective_doctor")
        
        if not user:
            return await handler(event, data)
        
        tier_to_check = (effective_doctor.subscription_tier if effective_doctor else user.subscription_tier)
        if tier_to_check < required_tier:
            # Блокируем выполнение и отправляем сообщение
            tier_name = TIER_NAMES.get(required_tier, f"уровень {required_tier}")
            deny_text = (
                f"🚫 Эта функция доступна только в подписке {tier_name}.\n"
                f"Текущий уровень тарифа: {TIER_NAMES.get(tier_to_check, 'Basic')}.\n"
                f"Обновите тариф для доступа к этой функции."
            )

            if isinstance(event, CallbackQuery):
                await event.answer(deny_text, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(deny_text)

            # Прерываем выполнение
            return
        
        # Если доступ разрешен, пропускаем дальше
        return await handler(event, data)

