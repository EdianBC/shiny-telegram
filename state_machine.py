from telegram import ReplyKeyboardMarkup, KeyboardButton
import asyncio


states = {}
task_queue = asyncio.Queue()
user_state = {}
user_vault = {}

async def add_task(user_id, task):
    await task_queue.put((user_id, task))

async def set_user_state(user_id, state):
    user_state[user_id] = state
    

class State:
    entry_protocol = None
    core_protocol = None
    transition_protocol = None

    def __init__(self, entry_protocol=None, core_protocol=None, transition_protocol=None):
        self.entry_protocol = entry_protocol
        self.core_protocol = core_protocol
        self.transition_protocol = transition_protocol

async def add_state(name, entry_protocol=None, core_protocol=None, transition_protocol=None):
    states[name] = State(entry_protocol, core_protocol, transition_protocol)
    
async def run_state(state_name, data):
    state = states.get(state_name)

    if state.core_protocol:
        await state.core_protocol(data)
        
    if state.transition_protocol:
        next_state_name = await state.transition_protocol(data)
    else:
        next_state_name = state_name

    state = states.get(next_state_name)
    if state.entry_protocol:
        await state.entry_protocol(data)
    
    return next_state_name



#region State Machine Setup
async def start_state_machine():
    #          State Name   Entry Function   Core Function   Transition Function
    await add_state("START", None, start_core, start_transition)
    await add_state("MAIN", main_entry, None, main_transition)
    
    # Here you can add functions that run in the background to check for something or update something IDK
    #asyncio.create_task(background_function())

async def run_state_machine_step(data: dict) -> list:
    user_id = data.get("id")
    if user_id not in user_state: #Safeguard if the user is not in the state dict, which should never happen but just in case
        user_state[user_id] = "START"
        user_vault[user_id] = {}

    state = user_state[user_id]
    next_state = await run_state(state, data)
    user_state[user_id] = next_state



#region Protocols

# Entries must receive a dict with data (for example {"id":"12345678", "message":"hi"})
# Cores must receive a dict with data
# Transitions must receive a dict with data and return a string with the name of the next state

# START
async def start_core(data):
    add_task(data["id"], ("text", "¡Bienvenido al bot! Escribe 'Hola' para empezar a chatear."))

async def start_transition(data):
    return "MAIN"

# MAIN
async def main_entry(data):
    pass

async def main_transition(data):
    message = data.get("message")

    if message == "Hola":
        add_task(data["id"], ("text", "Hola, ¿cómo estás?"))
    else:
        await add_task(data["id"], ("text", "No entiendo lo que quieres decir."))
        return "MAIN"
