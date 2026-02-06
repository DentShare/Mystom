from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    """Состояния FSM для редактирования настроек"""
    enter_full_name = State()
    enter_specialization = State()
    enter_phone = State()
    enter_address = State()
    enter_location = State()
    enter_photo = State()
    enter_timezone = State()
    enter_reminder_minutes = State()
