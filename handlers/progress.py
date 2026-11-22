import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from database.db import ensure_user, get_user, get_active_book, get_book_progress_summary

router = Router()


@router.message(Command("progress"))
@router.message(F.text == "📊 Бүгінгі прогресс")
async def cmd_progress(message: Message) -> None:
    db_path = str(settings.DB_PATH)
    default_reminder = f"{settings.MORNING_HOUR:02d}:{settings.MORNING_MINUTE:02d}"

    await ensure_user(
        db_path=db_path,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        default_reminder_time=default_reminder,
        default_portion_pages=settings.DEFAULT_PORTION_PAGES,
    )

    user = await get_user(db_path, message.from_user.id)
    book = await get_active_book(db_path, message.from_user.id)

    if not book:
        await message.answer(
            "📊 Қазір белсенді кітап жоқ.\n"
            "Кітап жүктеу үшін <b>«📚 Кітап»</b> батырмасын басыңыз."
        )
        return

    summary = await get_book_progress_summary(db_path, book["id"])
    current_day = summary["current_day"]

    total_words = max(1, book["total_words"])
    read_words = book["read_words"]
    book_pct = min(100, round(read_words / total_words * 100))
    read_pages = min(book["total_pages"], round(read_words / max(1, settings.WORDS_PER_PAGE)))

    day_line = ""
    if current_day:
        d_target = max(1, current_day["target_words"])
        d_read = current_day["read_words"]
        d_pct = min(100, round(d_read / d_target * 100))
        d_target_pages = max(1, round(d_target / max(1, settings.WORDS_PER_PAGE)))
        d_read_pages = round(d_read / max(1, settings.WORDS_PER_PAGE))
        day_line = (
            f"📅 <b>{current_day['day_number']}-күн нормасы:</b> "
            f"{d_read_pages} / ~{d_target_pages} бет ({d_pct}%)\n"
        )

    streak = user["streak_days"] if user else 0
    portion_pages = user["portion_pages"] if user else settings.DEFAULT_PORTION_PAGES

    await message.answer(
        f"📊 <b>Прогресс — {html.escape(book['title'])}</b>\n\n"
        f"{day_line}"
        f"📚 <b>Кітап бойынша:</b> ~{read_pages} / ~{book['total_pages']} бет ({book_pct}%)\n"
        f"🔥 Қатарынан оқылған күн: <b>{streak} күн</b>\n"
        f"📖 Әдепкі порция өлшемі: <b>~{portion_pages} бет</b>"
    )