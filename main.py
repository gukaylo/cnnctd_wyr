from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Укажите его в .env файле или переменных окружения.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CHOICE_A = "1"
CHOICE_B = "2"

QUESTIONS_FILE = Path(__file__).with_name("questions.18")

# --- Загрузка вопросов ---
def parse_questions_raw(raw: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ". " in stripped:
            _, rest = stripped.split(". ", 1)
        else:
            rest = stripped
        if " / " not in rest:
            raise ValueError(f"Неверный формат строки с вопросом: {stripped}")
        left, right = rest.split(" / ", 1)
        result.append((left.strip(), right.strip()))
    if not result:
        raise ValueError("Список вопросов пуст.")
    return result

def load_questions() -> list[tuple[str, str]]:
    try:
        raw = QUESTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError("Файл questions.18 не найден рядом с main.py") from exc
    return parse_questions_raw(raw)

QUESTIONS = load_questions()

# --- Активный раунд ---
@dataclass
class ActiveRound:
    chat_id: int
    message_id: int
    question_index: int
    question_a: str
    question_b: str
    votes: Dict[int, str] = field(default_factory=dict)
    timer_started: bool = False
    timer_task: asyncio.Task | None = None

RoundKey = Tuple[int, int]

active_rounds: Dict[RoundKey, ActiveRound] = {}
last_question_index: Dict[int, int] = {}
chat_locks: Dict[int, asyncio.Lock] = {}

# --- Помощники ---
def get_chat_lock(chat_id: int) -> asyncio.Lock:
    lock = chat_locks.get(chat_id)
    if not lock:
        lock = asyncio.Lock()
        chat_locks[chat_id] = lock
    return lock

def format_user_name(user: Message.from_user.__class__):
    username = user.username
    if username:
        return f"@{username}"
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    full_name = full_name or "Без имени"
    sanitized = full_name.replace("\n", " ")
    return f"{sanitized}"

def build_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🔵 Вариант 1", callback_data=f"vote:{CHOICE_A}"),
        InlineKeyboardButton(text="🔴 Вариант 2", callback_data=f"vote:{CHOICE_B}"),
    )
    builder.adjust(2)
    return builder.as_markup()

def pick_question(chat_id: int) -> tuple[int, str, str]:
    total = len(QUESTIONS)
    last_idx = last_question_index.get(chat_id)
    candidates = list(range(total))
    if last_idx is not None and total > 1 and last_idx in candidates:
        candidates.remove(last_idx)
    question_index = random.choice(candidates)
    last_question_index[chat_id] = question_index
    question_a, question_b = QUESTIONS[question_index]
    return question_index, question_a, question_b

def get_round_key(chat_id: int, message_id: int) -> RoundKey:
    return (chat_id, message_id)

def get_voter_names(round_data: ActiveRound) -> list[str]:
    return [round_data.votes[uid] for uid in round_data.votes]

def build_question_text(round_data: ActiveRound, timer_warning: bool = False) -> str:
    voters = [f"{uid}" for uid in round_data.votes.values()]
    voters_text = ", ".join(voters) if voters else "пока никто не проголосовал"
    warning = "⚠️ Осталось 20 секунд!\n\n" if timer_warning else ""
    return (
        f"{warning}[18+] Would you rather…\n\n"
        f"🔵 {round_data.question_a}\n"
        f"🔴 {round_data.question_b}\n\n"
        f"👥 Уже проголосовали — {voters_text}"
    )

# --- Логика старта нового раунда ---
async def start_new_round(message: Message) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer(
            "Добавь меня в группу, выдай право отправлять сообщения и используй /would_you_rather."
        )
        return

    chat_id = message.chat.id
    async with get_chat_lock(chat_id):
        question_index, question_a, question_b = pick_question(chat_id)
        round_data = ActiveRound(
            chat_id=chat_id,
            message_id=0,  # временно, потом обновим
            question_index=question_index,
            question_a=question_a,
            question_b=question_b,
        )
        sent = await message.answer(build_question_text(round_data), reply_markup=build_keyboard())
        round_data.message_id = sent.message_id
        active_rounds[get_round_key(chat_id, sent.message_id)] = round_data

# --- Таймер для подведения итогов ---
async def conclude_round_later(round_data: ActiveRound):
    await asyncio.sleep(20)
    async with get_chat_lock(round_data.chat_id):
        # итоговые голоса
        votes = round_data.votes
        total_votes = len(votes)
        a_votes = [uid for uid, choice in votes.items() if choice == CHOICE_A]
        b_votes = [uid for uid, choice in votes.items() if choice == CHOICE_B]
        a_percent = int(len(a_votes) / total_votes * 100) if total_votes else 0
        b_percent = int(len(b_votes) / total_votes * 100) if total_votes else 0
        a_names = ", ".join(a_votes) if a_votes else "никто"
        b_names = ", ".join(b_votes) if b_votes else "никто"
        text = (
            "Итоги раунда:\n\n"
            f"🔵 {round_data.question_a} — {a_percent}% ({len(a_votes)} голосов)\n"
            f"   Участники: {a_names}\n\n"
            f"🔴 {round_data.question_b} — {b_percent}% ({len(b_votes)} голосов)\n"
            f"   Участники: {b_names}"
        )
        try:
            await bot.edit_message_text(
                chat_id=round_data.chat_id,
                message_id=round_data.message_id,
                text=text,
                reply_markup=None
            )
        except TelegramBadRequest:
            pass
        # удаляем раунд
        active_rounds.pop(get_round_key(round_data.chat_id, round_data.message_id), None)

# --- Обработчики команд ---
@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "Я играю в 18+ Would you rather… Добавь меня в группу, дай право писать сообщения "
            "и используй команду /would_you_rather (или /wyr, /18), чтобы запустить раунд."
        )
    else:
        await message.reply("Я готов к раунду! Используй /would_you_rather, /wyr или /18.")

@dp.message(Command(commands=["would_you_rather", "wyr", "18"]))
async def handle_command(message: Message) -> None:
    await start_new_round(message)

# --- Обработчик голосов ---
@dp.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return

    choice = callback.data.split(":")[1]
    if choice not in {CHOICE_A, CHOICE_B}:
        await callback.answer("Неверный выбор")
        return

    chat_id = callback.message.chat.id
    user_name = callback.from_user.first_name or "Без имени"

    async with get_chat_lock(chat_id):
        round_data = active_rounds.get(get_round_key(chat_id, callback.message.message_id))
        if not round_data:
            await callback.answer("Раунд уже завершён.", show_alert=True)
            return

        # обновляем голос
        round_data.votes[user_name] = choice
        await callback.answer("Голос засчитан!")

        # проверка для таймера
        if len(round_data.votes) >= 2 and not round_data.timer_started:
            round_data.timer_started = True
            # обновляем сообщение с предупреждением
            try:
                await bot.edit_message_text(
                    chat_id=round_data.chat_id,
                    message_id=round_data.message_id,
                    text=build_question_text(round_data, timer_warning=True),
                    reply_markup=build_keyboard()
                )
            except TelegramBadRequest:
                pass
            # запускаем таймер
            round_data.timer_task = asyncio.create_task(conclude_round_later(round_data))
        else:
            # просто обновляем список проголосовавших
            try:
                await bot.edit_message_text(
                    chat_id=round_data.chat_id,
                    message_id=round_data.message_id,
                    text=build_question_text(round_data),
                    reply_markup=build_keyboard()
                )
            except TelegramBadRequest:
                pass

# --- Старт бота ---
def main() -> None:
    try:
        asyncio.run(dp.start_polling(bot))
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")

if __name__ == "__main__":
    main()
