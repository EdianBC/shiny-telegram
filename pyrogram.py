import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client, filters, enums
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
import state_machine as sm

load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID") # Requerido por Pyrogram
API_HASH = os.getenv("TELEGRAM_API_HASH") # Requerido por Pyrogram
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Inicializamos el cliente
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN)

editable_messages = {}

async def initialize_background_tasks():
    # Equivalente a post_init
    await sm.start_state_machine()
    # Registramos comandos de forma global
    await app.set_bot_commands([
        BotCommand("start", "Inicia el bot")
    ])
    # Iniciamos el handler de tareas
    asyncio.create_task(task_handler())

@app.on_message(filters.command("start") & filters.private)
async def start_command_handler(client, message):
    user_id = message.from_user.id 
    sm.set_user_state(user_id, "START")
    await sm.run_state_machine_step({"id": user_id})

@app.on_message(filters.text & filters.private & ~filters.command)
async def message_handler(client, message):
    text = message.text
    data = {"id": message.from_user.id, "message": text}
    await sm.run_state_machine_step(data)

async def task_handler():
    while True:
        try:
            # Asumimos que sm.task_queue es un asyncio.Queue
            user_id, action = sm.task_queue.get_nowait()
            await answer_to_user(user_id, action)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error in task_handler: {e}\n\nAction: {action}")

async def answer_to_user(user_id, action) -> None:
    # Helper para parse_mode
    parse_mode = enums.ParseMode.MARKDOWN

    if action[0] == "text":
        await app.send_message(chat_id=user_id, text=action[1], parse_mode=parse_mode)
    
    elif action[0] == "keyboard":
        keyboard = ReplyKeyboardMarkup([[KeyboardButton(caption) for caption in row] for row in action[1]], resize_keyboard=True)
        await app.send_message(chat_id=user_id, text="...", reply_markup=keyboard)
    
    elif action[0] == "textkeyboard":
        keyboard = ReplyKeyboardMarkup([[KeyboardButton(caption) for caption in row] for row in action[2]], resize_keyboard=True)
        await app.send_message(chat_id=user_id, text=action[1], reply_markup=keyboard)
    
    elif action[0] == "textnokeyboard":
        await app.send_message(chat_id=user_id, text=action[1], reply_markup=ReplyKeyboardRemove())
    
    elif action[0] == "quiz":
        # Pyrogram usa send_poll; para quiz pasamos type=enums.PollType.QUIZ
        await app.send_poll(
            chat_id=user_id,
            question=action[1]["question"],
            options=action[1]["options"],
            type=enums.PollType.QUIZ,
            correct_option_id=action[1]["correct_option_id"],
            is_anonymous=action[1].get("is_anonymous", False),
            open_period=action[1].get("open_period")
        )
    
    elif action[0] == "run":
        await sm.run_state_machine_step(action[1])

    elif action[0] in ["editabletext", "editabletextkeyboard"]:
        tag = action[1]
        text = action[2]
        markup = None
        if action[0] == "editabletextkeyboard":
            # Pyrogram no acepta ReplyKeyboardMarkup en edit_message_text fácilmente (ver notas)
            markup = ReplyKeyboardMarkup([[KeyboardButton(caption) for caption in row] for row in action[3]], resize_keyboard=True)
        
        msg = await app.send_message(chat_id=user_id, text=text, reply_markup=markup, parse_mode=parse_mode)
        editable_messages.setdefault(user_id, {})[tag] = msg.id

    elif action[0] in ["edittext", "edittextkeyboard"]:
        tag = action[1]
        text = action[2]
        
        if user_id in editable_messages and tag in editable_messages[user_id]:
            try:
                # En Pyrogram edit_message_text es para el contenido del mensaje
                await app.edit_message_text(chat_id=user_id, message_id=editable_messages[user_id][tag], text=text, parse_mode=parse_mode)
            except Exception as e:
                print(f"Failed to edit: {e}")
        else:
            msg = await app.send_message(chat_id=user_id, text=text, parse_mode=parse_mode)
            editable_messages.setdefault(user_id, {})[tag] = msg.id

if __name__ == "__main__":
    # Ejecutamos el cliente
    app.run(initialize_background_tasks())