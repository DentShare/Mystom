from aiogram.fsm.state import State, StatesGroup


class TeamStates(StatesGroup):
    """Состояния для раздела «Моя команда» и привязки ассистента."""
    enter_invite_code = State()
