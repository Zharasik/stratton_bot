from aiogram.fsm.state import State, StatesGroup


class SubmitStates(StatesGroup):
    waiting_video = State()


class NDAStates(StatesGroup):
    editing_fields = State()
    editing_field = State()


class AdminStates(StatesGroup):
    broadcast = State()
    nda_search = State()
