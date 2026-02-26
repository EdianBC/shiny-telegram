import os
from dotenv import load_dotenv
import telegram
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import state_machine as sm


load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

saved_messages = {}

async def post_init(application):
    # This function runs after the bot is initialized and before it starts polling
    # It's used to set up commands, initialize the state machine, and start the task handler
    # If you have any setup that needs to be done before the bot starts, you can add it here
    await set_bot_commands(application)
    await sm.start_state_machine()
    asyncio.create_task(task_handler(application))


async def set_bot_commands(application):
    # This function sets the commands that the bot will recognize. You can add more commands to the list as needed
    commands = [
        BotCommand("start", "Inicia el bot")
    ]
    await application.bot.set_my_commands(commands)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id 
    sm.set_user_state(user_id, "START")
    await sm.run_state_machine_step({"id": user_id})
    

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    data = {"id": update.effective_user.id, "message": text}
    await sm.run_state_machine_step(data)
    #asyncio.create_task(sm.run_state_machine_step(data))

async def task_handler(application):
    while True:
        try:
            user_id, action, params = sm.task_queue.get_nowait()
            await execute_task(application, user_id, action, params)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error in task_handler: {e}\n\nAction: {action}")

async def execute_task(application, user_id, action, params) -> None:
    if action == "message":
        text = params.get("text", None)
        parse_mode = params.get("parse_mode", None)
        # entities = params.get("entities", None)
        disable_web_page_preview = params.get("disable_web_page_preview", None)
        disable_notification = params.get("disable_notification", None)
        protect_content = params.get("protect_content", None)
        reply_to_message_id = saved_messages.get(params.get("reply_to_message_id", None), None)
        allow_sending_without_reply = params.get("allow_sending_without_reply", None)
        reply_markup = None if not params.get(reply_markup, None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("reply_markup")], resize_keyboard=True)
        reply_markup = telegram.ReplyKeyboardRemove() if params.get("remove_keyboard", False) else reply_markup
        # message_thread_id = params.get("message_thread_id", None)

        message_sent = await application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=parse_mode,
            # entities=entities,
            disable_web_page_preview=disable_web_page_preview,
            disable_notification=disable_notification,
            protect_content=protect_content,
            reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=allow_sending_without_reply,
            reply_markup=reply_markup
            # message_thread_id=message_thread_id
        )
        if params.get("save", None):
            saved_messages[params.get("save")] = message_sent.message_id

    elif action == "editmessage":
        message_id = saved_messages.get(params.get("message_id", None), None)
        if message_id:
            text = params.get("text", None)
            parse_mode = params.get("parse_mode", None)
            # entities = params.get("entities", None)
            disable_web_page_preview = params.get("disable_web_page_preview", None)
            disable_notification = params.get("disable_notification", None)
            protect_content = params.get("protect_content", None)
            reply_markup = None if not params.get(reply_markup, None) else ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in params.get("reply_markup")], resize_keyboard=True)
            reply_markup = telegram.ReplyKeyboardRemove() if params.get("remove_keyboard", False) else reply_markup

            try:
                await application.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                    # entities=entities,
                    disable_web_page_preview=disable_web_page_preview,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                    reply_markup=reply_markup
                )
            except telegram.error.TelegramError as e:
                print(f"Failed to edit message for user {user_id}: {e}")
        else:
            print(f"Message ID not found for editing: {params.get('message_id', None)}")

    elif action == "run": # ("action type", {"id": user_id, ...})
        await sm.run_state_machine_step(params)
        #asyncio.create_task(sm.run_state_machine_step(data))
    
    else:
        print(f"Unknown action: {action} for user {user_id}")


def main() -> None:
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("El bot ha iniciado. Presiona Ctrl+C para detenerlo.")
    application.run_polling(poll_interval=0.5)


if __name__ == "__main__":
    main()
