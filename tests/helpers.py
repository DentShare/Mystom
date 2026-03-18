"""Хелперы для тестирования хендлеров aiogram — моки Message, CallbackQuery, FSMContext."""
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from aiogram.types import User as TgUser


def make_tg_user(user_id: int = 111111, first_name: str = "Test") -> TgUser:
    """Создаёт мок Telegram-пользователя."""
    return TgUser(id=user_id, is_bot=False, first_name=first_name)


def make_message(text: str = "", user_id: int = 111111) -> AsyncMock:
    """Мок aiogram Message с .answer() и .from_user."""
    msg = AsyncMock()
    msg.text = text
    msg.from_user = make_tg_user(user_id)
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = AsyncMock()
    return msg


def make_callback(data: str = "", user_id: int = 111111) -> AsyncMock:
    """Мок aiogram CallbackQuery с .answer(), .message.edit_text()."""
    cb = AsyncMock()
    cb.data = data
    cb.from_user = make_tg_user(user_id)
    cb.answer = AsyncMock()
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.bot = AsyncMock()
    return cb


def make_state() -> AsyncMock:
    """Мок aiogram FSMContext."""
    state = AsyncMock()
    _data = {}

    async def update_data(**kwargs):
        _data.update(kwargs)

    async def get_data():
        return _data.copy()

    async def set_state(new_state=None):
        state._current_state = new_state

    async def clear():
        _data.clear()
        state._current_state = None

    state.update_data = update_data
    state.get_data = get_data
    state.set_state = set_state
    state.clear = clear
    state._current_state = None
    return state
