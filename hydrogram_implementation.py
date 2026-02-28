import os
import asyncio
from dotenv import load_dotenv

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from hydrogram import Client, filters, enums, idle
from hydrogram.types import (
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from hydrogram.errors import RPCError

import state_machine as sm

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
# hydrogram requiere API_ID y API_HASH
API_ID = os.getenv("API_ID") 
API_HASH = os.getenv("API_HASH")

# Inicializar cliente de hydrogram
app = Client(
    "mi_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=TOKEN
)

saved_messages = {}

async def set_bot_commands():
    '''
    This function sets the bot commands that appear when the user types "/" in the chat.
    '''
    commands = [
        BotCommand("start", "Inicia el bot")
    ]
    await app.set_bot_commands(commands)

# --- HANDLERS ---

@app.on_message(filters.command("start"))
async def start_command_handler(client, message):
    user_id = message.from_user.id 
    sm.set_user_state(user_id, "START")
    await sm.run_state_machine_step({"id": user_id})

@app.on_message(filters.text & ~filters.command("start"))
async def message_handler(client, message):
    text = message.text
    data = {"id": message.from_user.id, "message": text}
    await sm.run_state_machine_step(data)

@app.on_callback_query()
async def callback_query_handler(client, callback_query):
    query_data = callback_query.data
    user_id = callback_query.from_user.id
    data = {"id": user_id, "callback_data": query_data}
    await sm.run_state_machine_step(data)

@app.on_message(filters.photo)
async def photo_handler(client, message):
    photo_file_id = message.photo.file_id # hydrogram ya extrae la de mejor calidad
    user_id = message.from_user.id
    caption = message.caption
    data = {"id": user_id, "photo_file_id": photo_file_id, "caption": caption}
    await sm.run_state_machine_step(data)

@app.on_message(filters.document)
async def document_handler(client, message):
    document_file_id = message.document.file_id
    user_id = message.from_user.id
    caption = message.caption
    data = {"id": user_id, "document_file_id": document_file_id, "caption": caption}
    await sm.run_state_machine_step(data)

@app.on_message(filters.video)
async def video_handler(client, message):
    video_file_id = message.video.file_id
    user_id = message.from_user.id
    caption = message.caption
    data = {"id": user_id, "video_file_id": video_file_id, "caption": caption}
    await sm.run_state_machine_step(data)


# --- BACKGROUND TASKS ---

async def task_handler():
    while True:
        try:
            user_id, action, params = sm.task_queue.get_nowait()
            await execute_task(user_id, action, params)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error in task_handler: {e}\n\nAction: {action}")

async def execute_task(user_id, action, params) -> None:
    message_sent = None

    if action == "message":
        text = params.get("text", None)
        parse_mode = params.get("parse_mode", None)
        disable_web_page_preview = params.get("disable_web_page_preview", None)
        disable_notification = params.get("disable_notification", None)
        protect_content = params.get("protect_content", None)
        reply_to_message_id = saved_messages.get(params.get("reply_to_message_id", None), None)
        
        keyboard = None if not params.get("keyboard", None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("keyboard")], resize_keyboard=True)
        keyboard = ReplyKeyboardRemove() if params.get("remove_keyboard", False) else keyboard
        inline_keyboard = None if not params.get("inline_keyboard", None) else InlineKeyboardMarkup([[InlineKeyboardButton(text=caption, callback_data=data) for caption, data in row] for row in params.get("inline_keyboard")])

        if keyboard and inline_keyboard:
            raise ValueError("Cannot use both keyboard and inline_keyboard in the same message. Please choose one or the other.")
        else:
            reply_markup = keyboard if keyboard else inline_keyboard

        message_sent = await app.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            disable_notification=disable_notification,
            protect_content=protect_content,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup
        )
        if params.get("save", None):
            saved_messages[params.get("save")] = message_sent.id # hydrogram usa .id

    elif action == "editmessage":
        message_id = saved_messages.get(params.get("message_id", None), None)
        if message_id:
            text = params.get("text", None)
            parse_mode = params.get("parse_mode", None)
            disable_web_page_preview = params.get("disable_web_page_preview", None)
            
            keyboard = None if not params.get("keyboard", None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("keyboard")], resize_keyboard=True)
            keyboard = ReplyKeyboardRemove() if params.get("remove_keyboard", False) else keyboard
            inline_keyboard = None if not params.get("inline_keyboard", None) else InlineKeyboardMarkup([[InlineKeyboardButton(text=caption, callback_data=data) for caption, data in row] for row in params.get("inline_keyboard")])

            if keyboard and inline_keyboard:
                raise ValueError("Cannot use both keyboard and inline_keyboard in the same message. Please choose one or the other.")
            else:
                reply_markup = keyboard if keyboard else inline_keyboard

            try:
                await app.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_markup=reply_markup
                )
            except RPCError as e:
                print(f"Failed to edit message for user {user_id}: {e}")
        else:
            print(f"Message ID not found for editing: {params.get('message_id', None)}")

        if params.get("save", None):
            saved_messages[params.get("save")] = message_id

    elif action == "delete": 
        message_id = saved_messages.get(params.get("message_id", None), None)
        if message_id:
            try:
                # hydrogram usa delete_messages (plural) y message_ids
                await app.delete_messages(chat_id=user_id, message_ids=message_id)
            except RPCError as e:
                print(f"Failed to delete message for user {user_id}: {e}")
        else:
            print(f"Message ID not found for deletion: {params.get('message_id', None)}")

    elif action == "photo":
        photo = params.get("photo", None)
        caption = params.get("caption", None)
        parse_mode = params.get("parse_mode", None)
        disable_notification = params.get("disable_notification", None)
        protect_content = params.get("protect_content", None)
        reply_to_message_id = saved_messages.get(params.get("reply_to_message_id", None), None)
        
        keyboard = None if not params.get("keyboard", None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("keyboard")], resize_keyboard=True)
        keyboard = ReplyKeyboardRemove() if params.get("remove_keyboard", False) else keyboard
        inline_keyboard = None if not params.get("inline_keyboard", None) else InlineKeyboardMarkup([[InlineKeyboardButton(text=caption, callback_data=data) for caption, data in row] for row in params.get("inline_keyboard")])

        if keyboard and inline_keyboard:
            raise ValueError("Cannot use both keyboard and inline_keyboard in the same message.")
        else:
            reply_markup = keyboard if keyboard else inline_keyboard

        message_sent = await app.send_photo(
            chat_id=user_id,
            photo=photo, 
            caption=caption,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
            protect_content=protect_content,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup
        )

        if params.get("save", None):
            saved_messages[params.get("save")] = message_sent.id

    elif action == "document":
        document = params.get("document", None)
        caption = params.get("caption", None)
        parse_mode = params.get("parse_mode", None)
        disable_notification = params.get("disable_notification", None)
        protect_content = params.get("protect_content", None)
        reply_to_message_id = saved_messages.get(params.get("reply_to_message_id", None), None)
        
        keyboard = None if not params.get("keyboard", None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("keyboard")], resize_keyboard=True)
        keyboard = ReplyKeyboardRemove() if params.get("remove_keyboard", False) else keyboard
        inline_keyboard = None if not params.get("inline_keyboard", None) else InlineKeyboardMarkup([[InlineKeyboardButton(text=caption, callback_data=data) for caption, data in row] for row in params.get("inline_keyboard")])

        if keyboard and inline_keyboard:
            raise ValueError("Cannot use both keyboard and inline_keyboard in the same message.")
        else:
            reply_markup = keyboard if keyboard else inline_keyboard

        message_sent = await app.send_document(
            chat_id=user_id,
            document=document,
            caption=caption,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
            protect_content=protect_content,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup
        )

        if params.get("save", None):
            saved_messages[params.get("save")] = message_sent.id
    
    elif action == "video":
        video = params.get("video", None) 
        caption = params.get("caption", None)
        parse_mode = params.get("parse_mode", None)
        disable_notification = params.get("disable_notification", None)
        protect_content = params.get("protect_content", None)
        reply_to_message_id = saved_messages.get(params.get("reply_to_message_id", None), None)
        
        keyboard = None if not params.get("keyboard", None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("keyboard")], resize_keyboard=True)
        keyboard = ReplyKeyboardRemove() if params.get("remove_keyboard", False) else keyboard
        inline_keyboard = None if not params.get("inline_keyboard", None) else InlineKeyboardMarkup([[InlineKeyboardButton(text=caption, callback_data=data) for caption, data in row] for row in params.get("inline_keyboard")])

        if keyboard and inline_keyboard:
            raise ValueError("Cannot use both keyboard and inline_keyboard in the same message.")
        else:
            reply_markup = keyboard if keyboard else inline_keyboard

        message_sent = await app.send_video(
            chat_id=user_id,
            video=video,
            caption=caption,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
            protect_content=protect_content,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup
        )

        if params.get("save", None):
            saved_messages[params.get("save")] = message_sent.id

    elif action == "poll":
        question = params.get("question", None)
        options = params.get("options", None)
        type = params.get("type", None) # enums.PollType.REGULAR or enums.PollType.QUIZ en hydrogram
        correct_option_id = params.get("correct_option_id", None)
        is_anonymous = params.get("is_anonymous", None)
        open_period = params.get("open_period", None)
        allow_multiple_answers = params.get("allow_multiple_answers", None)
        explanation = params.get("explanation", None)
        explanation_parse_mode = params.get("explanation_parse_mode", None)
        reply_to_message_id = saved_messages.get(params.get("reply_to_message_id", None), None)
        
        keyboard = None if not params.get("keyboard", None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("keyboard")], resize_keyboard=True)
        keyboard = ReplyKeyboardRemove() if params.get("remove_keyboard", False) else keyboard
        inline_keyboard = None if not params.get("inline_keyboard", None) else InlineKeyboardMarkup([[InlineKeyboardButton(text=caption, callback_data=data) for caption, data in row] for row in params.get("inline_keyboard")])

        if keyboard and inline_keyboard:
            raise ValueError("Cannot use both keyboard and inline_keyboard in the same message.")
        else:
            reply_markup = keyboard if keyboard else inline_keyboard

        message_sent = await app.send_poll(
            chat_id=user_id,
            question=question,
            options=options,
            type=type,
            correct_option_id=correct_option_id,
            is_anonymous=is_anonymous,
            open_period=open_period,
            allows_multiple_answers=allow_multiple_answers, # Nota: En hydrogram es 'allows_' con 's'
            explanation=explanation,
            explanation_parse_mode=explanation_parse_mode,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup
        )

        if params.get("save", None):
            saved_messages[params.get("save")] = message_sent.id

    elif action == "run":
        await sm.run_state_machine_step(params)
    
    else:
        print(f"Unknown action: {action} for user {user_id}")

# --- MAIN LOOP ---

async def main():
    print("Iniciando sesión del bot...")
    await app.start()
    print("Configurando comandos y dependencias...")
    await set_bot_commands()
    await sm.start_state_machine()
    asyncio.create_task(task_handler())
    
    print("El bot de hydrogram ha iniciado. Presiona Ctrl+C para detenerlo.")
    await idle()  # Mantiene el bot corriendo
    
    print("Deteniendo bot...")
    await app.stop()

if __name__ == "__main__":
    # hydrogram maneja su propio event loop si usas app.run(), 
    # pero como necesitamos iniciar tareas en background (task_handler) 
    # antes de bloquear con idle(), lo arrancamos manualmente.
    asyncio.run(main())