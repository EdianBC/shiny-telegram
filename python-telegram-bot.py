import os
from dotenv import load_dotenv
import telegram
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import state_machine as sm


load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

editable_messages = {}

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
    username = update.effective_user.username
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
            user_id, action = sm.task_queue.get_nowait()
            await answer_to_user(application, user_id, action)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error in task_handler: {e}\n\nAction: {action}")

async def answer_to_user(application, user_id, action) -> None:
     
    if action[0] == "text": # ("action type", "text to send")
        message_sent = await application.bot.send_message(chat_id=user_id, text=action[1], parse_mode="Markdown")
    elif action[0] == "keyboard": # ("action type", [["button1", "button2"], ["button3"], ...])
        keyboard = ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in action[1]], resize_keyboard=True)
        message_sent = await application.bot.send_message(chat_id=user_id, text="...", reply_markup=keyboard, parse_mode="Markdown")  
    elif action[0] == "textkeyboard": # ("action type", "text to send", [["button1", "button2"], ["button3"], ...])
        keyboard = ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in action[1]], resize_keyboard=True)
        message_sent = await application.bot.send_message(chat_id=user_id, text=action[1], reply_markup=keyboard, parse_mode="Markdown")
    elif action[0] == "textnokeyboard": # ("action type", "text to send")
        message_sent = await application.bot.send_message(chat_id=user_id, text=action[1], reply_markup=telegram.ReplyKeyboardRemove(), parse_mode="Markdown")
    elif action[0] == "quiz": # ("action type", {"question": "Question?", "options": ["Option 1", "Option 2"], "correct_option_id": 0, "is_anonymous": False, "open_period": 30})
        await application.bot.send_poll(
            chat_id=user_id,
            question=action[1]["question"],
            options=action[1]["options"],
            type="quiz",
            correct_option_id=action[1]["correct_option_id"],
            is_anonymous=action[1]["is_anonymous"],
            open_period=action[1].get("open_period")
        )
    elif action[0] == "run": # ("action type", {"id": user_id, ...})
        data = action[1]
        await sm.run_state_machine_step(data)
        #asyncio.create_task(sm.run_state_machine_step(data))
    elif action[0] == "editabletext": # ("action type", "tag for the message", "text to send")
        tag = action[1]
        message_sent = await application.bot.send_message(chat_id=user_id, text=action[2], parse_mode="Markdown")
        editable_messages.setdefault(user_id, {})[tag] = message_sent.message_id
    elif action[0] == "editabletextkeyboard": # ("action type", "tag for the message", "text to send", [["button1", "button2"], ["button3"], ...])
        tag = action[1]
        message_sent = await application.bot.send_message(chat_id=user_id, text=action[2], reply_markup=action[3], parse_mode="Markdown")
        editable_messages.setdefault(user_id, {})[tag] = message_sent.message_id
    elif action[0] == "edittext": # ("action type", "tag for the message", "new text to send")
        tag = action[1]
        if user_id in editable_messages and tag in editable_messages[user_id]:
            try:
                await application.bot.edit_message_text(chat_id=user_id, message_id=editable_messages[user_id][tag], text=action[2], parse_mode="Markdown")
            except telegram.error.TelegramError as e:
                print(f"Failed to edit message for user {user_id}: {e}")
        else:
            message_sent = await application.bot.send_message(chat_id=user_id, text=action[2], parse_mode="Markdown")
            editable_messages.setdefault(user_id, {})[tag] = message_sent.message_id
    elif action[0] == "edittextkeyboard":
        tag = action[1]
        keyboard = ReplyKeyboardMarkup([[KeyboardButton(text=caption) for caption in row] for row in action[3]], resize_keyboard=True)
        if user_id in editable_messages and tag in editable_messages[user_id]:
            try:
                await application.bot.edit_message_text(chat_id=user_id, message_id=editable_messages[user_id][tag], text=action[2], reply_markup=keyboard, parse_mode="Markdown")
            except telegram.error.TelegramError as e:
                print(f"Failed to edit message for user {user_id}: {e}")
        else:
            message_sent = await application.bot.send_message(chat_id=user_id, text=action[2], reply_markup=keyboard, parse_mode="Markdown")
            editable_messages.setdefault(user_id, {})[tag] = message_sent.message_id
    else:
        message_sent = await application.bot.send_message(chat_id=user_id, text= f"Mmm... Thinking... Brrrr Bip Bop... System Overload... Error 404... Just kidding!")
        print(f"Unknown action type: {action[0]}")



def main() -> None:
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("El bot ha iniciado. Presiona Ctrl+C para detenerlo.")
    application.run_polling(poll_interval=0.5)


if __name__ == "__main__":
    main()
