from aiogram.fsm.state import State, StatesGroup


class ImplantStates(StatesGroup):
    """Состояния FSM для добавления имплантов"""
    select_teeth = State()       # Мультивыбор зубов
    select_system = State()      # Компания/система
    enter_system = State()       # Ручной ввод системы
    select_diameter = State()   # Диаметр
    enter_diameter = State()    # Ручной ввод диаметра
    select_length = State()     # Длина
    enter_length = State()      # Ручной ввод длины
    enter_notes = State()       # Заметки (опционально)
    add_more = State()          # Добавить ещё / Завершить
