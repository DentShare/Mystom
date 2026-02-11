from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния FSM для регистрации: выбор роли, врач или ассистент."""
    choose_role = State()
    # Врач (стоматолог)
    enter_full_name = State()
    enter_specialization = State()
    enter_phone = State()
    enter_address = State()
    enter_location = State()  # Геолокация
    enter_photo = State()  # Фото врача (опционально)
    enter_timezone = State()  # Часовой пояс
    # Ассистент (после привязки по коду)
    assistant_enter_name = State()
    assistant_enter_phone = State()

