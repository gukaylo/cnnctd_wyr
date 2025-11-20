import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

vote_state = {
    'votes': {},           # {user_id: {'choice': 'A'/'B', 'name': str}}
    'message_id': None,
    'chat_id': None,
    'timer_started': False,
    'lock': threading.Lock()
}

QUESTION = "Вы бы предпочли A или B?"

def start_vote(update: Update, context: CallbackContext):
    with vote_state['lock']:
        vote_state['votes'] = {}
        vote_state['timer_started'] = False

    keyboard = [
        [InlineKeyboardButton("A", callback_data='A')],
        [InlineKeyboardButton("B", callback_data='B')]
    ]

    msg = context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=QUESTION + "\nГолосуйте ниже!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    with vote_state['lock']:
        vote_state['message_id'] = msg.message_id
        vote_state['chat_id'] = update.effective_chat.id

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    choice = query.data

    with vote_state['lock']:
        vote_state['votes'][user.id] = {'choice': choice, 'name': user.first_name}
        votes_len = len(vote_state['votes'])
        timer_started = vote_state['timer_started']

    # Обновляем сообщение с проголосовавшими
    text = summary_text()
    update_message(context, text)

    # Старт таймера только при 2 и более голосах
    if votes_len >= 2 and not timer_started:
        with vote_state['lock']:
            vote_state['timer_started'] = True
        # Обновляем сообщение с предупреждением о 20 секундах
        text_with_timer = "⚠️ Осталось 20 секунд!\n\n" + summary_text()
        update_message(context, text_with_timer)
        # Запускаем таймер в отдельном потоке
        threading.Thread(target=countdown, args=(context,)).start()

    query.answer("Голос засчитан!")

def countdown(context: CallbackContext):
    time.sleep(20)
    # После таймера — подведение итогов
    with vote_state['lock']:
        results = vote_state['votes'].copy()

    a_votes = [v['name'] for v in results.values() if v['choice'] == 'A']
    b_votes = [v['name'] for v in results.values() if v['choice'] == 'B']

    total = len(a_votes) + len(b_votes)
    a_percent = int((len(a_votes) / total) * 100) if total > 0 else 0
    b_percent = int((len(b_votes) / total) * 100) if total > 0 else 0

    result_text = "Голосование завершено!\n\n"
    result_text += f"🔵 A — {a_percent}% ({len(a_votes)} голосов)\n"
    result_text += f"   Участники: {', '.join(a_votes) if a_votes else 'никто'}\n\n"
    result_text += f"🔴 B — {b_percent}% ({len(b_votes)} голосов)\n"
    result_text += f"   Участники: {', '.join(b_votes) if b_votes else 'никто'}"

    # Обновляем исходное сообщение без кнопок
    update_message(context, result_text, remove_keyboard=True)

def summary_text():
    with vote_state['lock']:
        votes = vote_state['votes'].copy()
    if votes:
        names = [v['name'] for v in votes.values()]
        return f"{QUESTION}\nПроголосовало: {len(votes)} — {', '.join(names)}"
    else:
        return f"{QUESTION}\nПроголосовало: 0"

def update_message(context, text, remove_keyboard=False):
    with vote_state['lock']:
        chat_id = vote_state['chat_id']
        message_id = vote_state['message_id']

    try:
        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=None if remove_keyboard else InlineKeyboardMarkup([
                [InlineKeyboardButton("A", callback_data='A')],
                [InlineKeyboardButton("B", callback_data='B')]
            ])
        )
    except Exception as e:
        logger.warning("Не удалось обновить сообщение: %s", e)

def main():
    updater = Updater("YOUR_TELEGRAM_BOT_TOKEN", use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_vote))
    dp.add_handler(CommandHandler("wyr", start_vote))
    dp.add_handler(CallbackQueryHandler(button))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
