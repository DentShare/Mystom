from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния FSM для регистрации врача"""
    enter_full_name = State()
    enter_specialization = State()
    enter_phone = State()
    enter_address = State()
    enter_location = State()  # Геолокация
    enter_photo = State()  # Фото врача (опционально)
    enter_timezone = State()  # Часовой пояс

