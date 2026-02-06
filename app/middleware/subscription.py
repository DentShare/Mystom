from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.dispatcher.flags import get_flag

from app.database.models import User


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для проверки уровня подписки через флаги хендлеров"""
    
    TIER_NAMES = {
        0: "Basic",
        1: "Standard",
        2: "Premium"
    }
    
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
        
        # Получаем пользователя из data (добавлен UserMiddleware)
        user: User | None = data.get("user")
        
        if not user:
            return await handler(event, data)
        
        # Проверяем уровень подписки
        if user.subscription_tier < required_tier:
            # Блокируем выполнение и отправляем сообщение
            tier_name = self.TIER_NAMES.get(required_tier, f"уровень {required_tier}")
            
            if isinstance(event, (Message, CallbackQuery)):
                message = event.message if isinstance(event, CallbackQuery) else event
                if message:
                    await message.answer(
                        f"🚫 Эта функция доступна только в подписке {tier_name}.\n"
                        f"Ваш текущий уровень: {self.TIER_NAMES.get(user.subscription_tier, 'Basic')}.\n"
                        f"Обновите тариф для доступа к этой функции."
                    )
            
            # Прерываем выполнение
            return
        
        # Если доступ разрешен, пропускаем дальше
        return await handler(event, data)

