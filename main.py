# main.py
from __future__ import annotations
import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ChatType
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env файле")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CHOICE_A = "A"
CHOICE_B = "B"

QUESTIONS_FILE = Path(__file__).with_name("questions.18")

def load_questions() -> list[Tuple[str, str]]:
    try:
        raw = QUESTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError("Файл questions.18 не найден рядом с main.py")
    questions = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if " / " not in line:
            raise ValueError(f"Неверный формат строки: {line}")
        a, b = line.split(" / ", 1)
        questions.append((a.strip(), b.strip()))
    if not questions:
        raise ValueError("Список вопросов пуст.")
    return questions

QUESTIONS = load_questions()

@dataclass
class ActiveRound:
    chat_id: int
    message_id: int
    question_a: str
    question_b: str
    votes: Dict[int, Tuple[str, str]] = field(default_factory=dict)
    timer_task: asyncio.Task | None = None
    timer_started: bool = False

active_rounds: Dict[int, ActiveRound] = {}

def format_user(user: types.User) -> str:
    if user.username:
        return f"@{user.username}"
    name = " ".join(filter(None, [user.first_name, user.last_name])) or f"id:{user.id}"
    return name

def build_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("🔵 Вариант 1", callback_data=f"vote:{CHOICE_A}")],
            [InlineKeyboardButton("🔴 Вариант 2", callback_data=f"vote:{CHOICE_B}")]
        ]
    )

def build_question_text(round_data: ActiveRound, extra_text: str = "") -> str:
    voters = [name for _, name in round_data.votes.values()]
    voters_block = ", ".join(voters) if voters else "пока никто не проголосовал"
    text = f"{extra_text}\n[18+] Would you rather…\n\n🔵 {round_data.question_a}\n🔴 {round_data.question_b}\n\n👥 Уже проголосовали — {voters_block}"
    return text.strip()

async def start_new_round(message: Message):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Добавь меня в группу и используй команду /wyr")
        return

    question_a, question_b = random.choice(QUESTIONS)
    sent = await message.answer(build_question_text(ActiveRound(0,0,question_a,question_b)), reply_markup=build_keyboard())

    round_data = ActiveRound(
        chat_id=message.chat.id,
        message_id=sent.message_id,
        question_a=question_a,
        question_b=question_b
    )
    active_rounds[sent.message_id] = round_data

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Я бот 18+ Would you rather… Используй /wyr для старта раунда")

@dp.message(Command(commands=["wyr","would_you_rather","18"]))
async def cmd_wyr(message: Message):
    await start_new_round(message)

@dp.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: types.CallbackQuery):
    if not callback.message:
        return

    choice = callback.data.split(":")[1]
    round_data = active_rounds.get(callback.message.message_id)
    if not round_data:
        await callback.answer("Раунд уже завершён", show_alert=True)
        return

    user_name = format_user(callback.from_user)
    round_data.votes[callback.from_user.id] = (choice, user_name)
    await callback.answer("Голос засчитан!")

    extra_text = ""
    if len(round_data.votes) >= 2 and not round_data.timer_started:
        round_data.timer_started = True
        extra_text = "⚠️ Осталось 20 секунд!"
        round_data.timer_task = asyncio.create_task(conclude_round_after_delay(round_data, 20))

    await callback.message.edit_text(build_question_text(round_data, extra_text), reply_markup=build_keyboard() if not round_data.timer_started else None)

async def conclude_round_after_delay(round_data: ActiveRound, delay: int):
    await asyncio.sleep(delay)
    a_count = sum(1 for choice, _ in round_data.votes.values() if choice == CHOICE_A)
    b_count = sum(1 for choice, _ in round_data.votes.values() if choice == CHOICE_B)
    total = max(a_count + b_count, 1)
    a_percent = int(a_count/total*100)
    b_percent = int(b_count/total*100)

    a_names = [name for choice,name in round_data.votes.values() if choice==CHOICE_A]
    b_names = [name for choice,name in round_data.votes.values() if choice==CHOICE_B]

    result_text = (
        f"Итоги раунда:\n\n"
        f"🔵 {round_data.question_a} — {a_percent}% ({a_count} голосов)\n"
        f"Участники: {', '.join(a_names) if a_names else 'никто'}\n\n"
        f"🔴 {round_data.question_b} — {b_percent}% ({b_count} голосов)\n"
        f"Участники: {', '.join(b_names) if b_names else 'никто'}"
    )

    await bot.edit_message_text(result_text, chat_id=round_data.chat_id, message_id=round_data.message_id)
    active_rounds.pop(round_data.message_id, None)

def main():
    try:
        import asyncio
        asyncio.run(dp.start_polling(bot))
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")

if __name__ == "__main__":
    main()
