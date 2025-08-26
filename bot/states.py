from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    waiting_for_api = State()
    waiting_for_doc = State()
    waiting_for_sheet = State()
    waiting_for_calendar_pick = State()