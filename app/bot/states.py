from aiogram.fsm.state import State, StatesGroup


class DialogState(StatesGroup):
    active = State()
    waiting_scene = State()
