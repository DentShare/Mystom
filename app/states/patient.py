from aiogram.fsm.state import State, StatesGroup


class PatientStates(StatesGroup):
    """Состояния FSM для работы с пациентами"""
    enter_full_name = State()
    enter_phone = State()
    enter_birth_date = State()
    enter_notes = State()
    search_patient = State()  # Поиск пациента

