from aiogram.fsm.state import State, StatesGroup


class HistoryStates(StatesGroup):
    """Состояния FSM для добавления записи в историю болезни"""
    select_service_category = State()
    select_service = State()
    enter_service_manual = State()
    enter_comment = State()
    enter_discount = State()  # Premium: скидка на услугу (%, сумма или /skip)
    # Внесение оплаты (Premium)
    payment_whole_discount = State()  # скидка на всю работу
    payment_amount = State()         # внесённая сумма
    payment_method = State()         # наличные / карта / перевод
