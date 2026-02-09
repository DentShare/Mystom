from aiogram.fsm.state import State, StatesGroup


class AppointmentStates(StatesGroup):
    """Состояния FSM для записи на прием"""
    select_date = State()
    select_location = State()  # Если >1 локация
    select_time = State()
    enter_patient_name = State()  # Basic: текстовый ввод "ФИО - Услуга"
    select_or_create_patient = State()  # Standard+: выбор из базы или создание
    select_service_category = State()  # Выбор категории услуги
    select_service = State()  # Выбор услуги из категории
    enter_service = State()  # Текстовый ввод (если "Другое")
    enter_discount = State()  # Premium: скидка на услугу при записи через расписание
    enter_tooth_number = State()  # Premium, опционально
    enter_price = State()  # Premium: сумма, скидка, способ оплаты

