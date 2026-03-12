from aiogram.fsm.state import State, StatesGroup


class VoiceBookingStates(StatesGroup):
    """FSM для записи через голос/скриншот."""
    choosing_patient = State()      # Выбор из нескольких найденных пациентов
    entering_patient_phone = State() # Ввод телефона нового пациента
    entering_date = State()          # Ручной ввод даты (если не распознана)
    entering_time = State()          # Ручной ввод времени (если не распознано)
    choosing_service = State()       # Выбор услуги (если не распознана)
    confirming = State()             # Подтверждение записи
