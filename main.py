"""Основной файл Telegram-бота "Would you rather..." 18+."""

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


@dataclass
class ActiveRound:
    chat_id: int
    message_id: int
    question_index: int
    question_a: str
    question_b: str
    votes: Dict[int, Tuple[str, str]] = field(default_factory=dict)
    timer_task: asyncio.Task | None = None
    timer_started: bool = False


RoundKey = Tuple[int, int]

active_rounds: Dict[RoundKey, ActiveRound] = {}
last_question_index: Dict[int, int] = {}
chat_locks: Dict[int, asyncio.Lock] = {}


def get_chat_lock(chat_id: int) -> asyncio.Lock:
    lock = chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        chat_locks[chat_id] = lock
    return lock


def format_user_name(user: Message.from_user.__class__):  # type: ignore[attr-defined]
    username = user.username
    if username:
        return f"@{username}"
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    full_name = full_name or "Без имени"
    sanitized = full_name.replace("\n", " ")
    return f"{sanitized} (id:{user.id})"


def build_question_text(
    question_a: str,
    question_b: str,
    voters: list[str],
    countdown: int | None = None,
) -> str:
    if voters:
        voters_block = f"{len(voters)} {pluralize_participants(len(voters))}: " + ", ".join(voters)
    else:
        voters_block = "пока никто не проголосовал"
    countdown_text = f"⚠️ Осталось {countdown} секунд!\n\n" if countdown is not None else ""
    return (
        f"{countdown_text}[18+] Would you rather…\n\n"
        f"🔵 {question_a}\n"
        f"🔴 {question_b}\n\n"
        f"👥 Уже проголосовали — {voters_block}"
    )


def pluralize_votes(count: int) -> str:
    if 11 <= count % 100 <= 14:
        return "голосов"
    last_digit = count % 10
    if last_digit == 1:
        return "голос"
    if 2 <= last_digit <= 4:
        return "голоса"
    return "голосов"


def pluralize_participants(count: int) -> str:
    if 11 <= count % 100 <= 14:
        return "участников"
    last_digit = count % 10
    if last_digit == 1:
        return "участник"
    if 2 <= last_digit <= 4:
        return "участника"
    return "участников"


def get_round_key(chat_id: int, message_id: int) -> RoundKey:
    return (chat_id, message_id)


def get_voter_names(round_data: ActiveRound) -> list[str]:
    return [display_name for _, display_name in round_data.votes.values()]


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
    if total == 0:
        raise RuntimeError("Список вопросов пуст.")

    last_idx = last_question_index.get(chat_id)
    candidates = list(range(total))
    if last_idx is not None and total > 1 and last_idx in candidates:
        candidates.remove(last_idx)

    question_index = random.choice(candidates)
    last_question_index[chat_id] = question_index
    question_a, question_b = QUESTIONS[question_index]
    return question_index, question_a, question_b


async def start_new_round(message: Message) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer(
            "Добавь меня в группу, выдай право отправлять сообщения и используй /would_you_rather."
        )
        return

    chat_id = message.chat.id
    async with get_chat_lock(chat_id):
        question_index, question_a, question_b = pick_question(chat_id)
        text = build_question_text(question_a, question_b, [])
        sent = await message.answer(text, reply_markup=build_keyboard())
        round_data = ActiveRound(
            chat_id=chat_id,
            message_id=sent.message_id,
            question_index=question_index,
            question_a=question_a,
            question_b=question_b,
        )
        active_rounds[get_round_key(chat_id, sent.message_id)] = round_data


def format_results(round_data: ActiveRound) -> str:
    choice_to_text = {CHOICE_A: round_data.question_a, CHOICE_B: round_data.question_b}
    grouped: Dict[str, list[str]] = {CHOICE_A: [], CHOICE_B: []}
    for _, (choice, display_name) in round_data.votes.items():
        grouped.setdefault(choice, []).append(display_name)

    total_votes = sum(len(v) for v in grouped.values()) or 1  # prevent division by zero

    def format_block(choice: str) -> str:
        voters = grouped.get(choice, [])
        count = len(voters)
        percent = round(count / total_votes * 100)
        names = ", ".join(voters) if voters else "никто"
        color = "🔵" if choice == CHOICE_A else "🔴"
        plural = pluralize_votes(count)
        return f"{color} {choice_to_text[choice]} — {percent}% ({count} {plural})\n   Участники: {names}"

    return "Итоги раунда:\n\n" + "\n\n".join([format_block(CHOICE_A), format_block(CHOICE_B)])


async def countdown_timer(round_data: ActiveRound, duration: int = 20) -> None:
    chat_id = round_data.chat_id
    message_id = round_data.message_id
    try:
        for remaining in range(duration, 0, -1):
            await asyncio.sleep(1)
            async with get_chat_lock(chat_id):
                if message_id not in [m.message_id for m in active_rounds.values()]:
                    return  # Round ended early
                await bot.edit_message_text(
                    build_question_text(
                        round_data.question_a,
                        round_data.question_b,
                        get_voter_names(round_data),
                        countdown=remaining,
                    ),
                    chat_id,
                    message_id,
                    reply_markup=build_keyboard(),
                )
        # После окончания таймера — выводим результат и удаляем кнопки
        async with get_chat_lock(chat_id):
            active_rounds.pop(get_round_key(chat_id, message_id), None)
            await bot.edit_message_text(
                format_results(round_data),
                chat_id,
                message_id,
            )
    except TelegramBadRequest:
        logging.warning("Не удалось обновить сообщение таймера")


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


@dp.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return

    choice = callback.data.split(":", maxsplit=1)[-1]
    if choice not in {CHOICE_A, CHOICE_B}:
        await callback.answer("Неверный выбор")
        return

    chat_id = callback.message.chat.id
    user = callback.from_user
    if not user:
        await callback.answer()
        return

    async with get_chat_lock(chat_id):
        round_data = active_rounds.get(get_round_key(chat_id, callback.message.message_id))
        if not round_data:
            await callback.answer("Раунд уже завершён.", show_alert=True)
            return

        previous = round_data.votes.get(user.id)
        new_record = (choice, format_user_name(user))

        if previous and previous[0] == choice:
            await callback.answer("Вы уже выбрали этот вариант.")
            return

        round_data.votes[user.id] = new_record
        feedback = "Голос обновлён." if previous else "Голос засчитан!"
        await callback.answer(feedback)

        # Обновляем текст после каждого голоса
        await callback.message.edit_text(
            build_question_text(
                round_data.question_a,
                round_data.question_b,
                get_voter_names(round_data),
            ),
            reply_markup=build_keyboard(),
        )

        # Запускаем таймер, если голосов >=2 и таймер ещё не стартовал
        if len(round_data.votes) >= 2 and not round_data.timer_started:
            round_data.timer_started = True
            round_data.timer_task = asyncio.create_task(countdown_timer(round_data))


def main() -> None:
    try:
        asyncio.run(dp.start_polling(bot))
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")


if __name__ == "__main__":
    main()
