import html
import os
import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.db import (
    ensure_user,
    create_book_with_plan,
    get_active_book,
    get_user_books,
    get_book_by_id,
    set_active_book,
)
from services.converter import convert_book_to_markdown, count_words
from services.splitter import estimate_pages, split_text_into_days

router = Router()


class BookUploadStates(StatesGroup):
    waiting_for_book = State()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return cleaned or "book"


def _books_switch_keyboard(books: list[dict], active_book_id: int | None) -> InlineKeyboardMarkup | None:
    if not books:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for b in books[:10]:
        pct = min(100, round(b.get("read_words", 0) / max(1, b.get("total_words", 1)) * 100))
        prefix = "▶️ " if b["id"] == active_book_id else "📘 "
        short_title = b["title"][:28] + ("…" if len(b["title"]) > 28 else "")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{short_title} ({pct}%)",
                    callback_data=f"switch_book:{b['id']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("book"))
@router.message(F.text == "📚 Кітап")
async def cmd_book(message: Message, state: FSMContext) -> None:
    default_reminder = f"{settings.MORNING_HOUR:02d}:{settings.MORNING_MINUTE:02d}"
    db_path = str(settings.DB_PATH)

    await ensure_user(
        db_path=db_path,
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        default_reminder_time=default_reminder,
        default_portion_pages=settings.DEFAULT_PORTION_PAGES,
    )

    active_book = await get_active_book(db_path, message.from_user.id)
    books = await get_user_books(db_path, message.from_user.id)
    active_id = active_book["id"] if active_book else None

    info_lines = []
    if active_book:
        read_pages = min(
            active_book["total_pages"],
            round(active_book.get("read_words", 0) / max(1, settings.WORDS_PER_PAGE)),
        )
        pct = min(
            100,
            round(active_book.get("read_words", 0) / max(1, active_book.get("total_words", 1)) * 100),
        )
        info_lines.append(
            f"📘 <b>Қазіргі белсенді кітап:</b> {html.escape(active_book['title'])}\n"
            f"📊 Прогресс: <b>~{read_pages} / ~{active_book['total_pages']} бет ({pct}%)</b>\n"
        )

    if len(books) > 1:
        info_lines.append("Төмендегі кітаптардың бірін таңдап, тоқтаған жеріңізден жалғастыра аласыз:\n")

    info_lines.append(
        "Жаңа кітап жүктеу үшін <b>PDF</b> немесе <b>EPUB</b> файлын жіберіңіз.\n"
        f"Бот кітапты <b>{settings.DAYS_PER_BOOK} күнге</b> бөліп, күнделікті норманы есептейді."
    )

    await state.set_state(BookUploadStates.waiting_for_book)
    kb = _books_switch_keyboard(books, active_id) if len(books) > 1 else None
    await message.answer("\n".join(info_lines), reply_markup=kb)


@router.callback_query(F.data.startswith("switch_book:"))
async def on_switch_book(callback: CallbackQuery) -> None:
    try:
        book_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Қате кітап нөмірі.", show_alert=True)
        return

    db_path = str(settings.DB_PATH)
    book = await get_book_by_id(db_path, book_id, callback.from_user.id)
    if not book:
        await callback.answer("Кітап табылмады.", show_alert=True)
        return

    await set_active_book(db_path, callback.from_user.id, book_id)

    read_pages = min(
        book["total_pages"],
        round(book.get("read_words", 0) / max(1, settings.WORDS_PER_PAGE)),
    )
    pct = min(
        100,
        round(book.get("read_words", 0) / max(1, book.get("total_words", 1)) * 100),
    )

    await callback.message.answer(
        f"✅ Белсенді кітап ауыстырылды: <b>{html.escape(book['title'])}</b>\n"
        f"📍 Тоқтаған жеріңіз: <b>~{read_pages} / ~{book['total_pages']} бет ({pct}%)</b>\n\n"
        "Жалғастыру үшін <b>«📖 Порция ал»</b> батырмасын басыңыз!"
    )
    await callback.answer("Кітап ауыстырылды")


@router.message(BookUploadStates.waiting_for_book, F.document)
async def process_book_document(message: Message, state: FSMContext, bot: Bot) -> None:
    doc = message.document
    file_name = doc.file_name or "book.pdf"
    ext = os.path.splitext(file_name)[1].lower()

    if ext not in {".pdf", ".epub"}:
        await message.answer(
            "⚠️ Тек <b>.pdf</b> немесе <b>.epub</b> форматтағы файлдар қабылданады.\n"
            "Басқа файл жіберіп көріңіз."
        )
        return

    status_msg = await message.answer("⏳ Кітап қабылданды, өңделіп жатыр... Біраз уақыт алуы мүмкін.")

    db_path = str(settings.DB_PATH)
    user_dir = settings.BOOKS_DIR / str(message.from_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    base_title = os.path.splitext(file_name)[0]
    safe_stem = _safe_filename(base_title)
    saved_file_path = str(user_dir / f"{safe_stem}{ext}")
    md_output_path = str(user_dir / f"{safe_stem}.md")

    try:
        await bot.download(doc, destination=saved_file_path)

        markdown_text, total_words = convert_book_to_markdown(
            file_path=saved_file_path,
            md_output_path=md_output_path,
        )

        total_pages = estimate_pages(total_words, words_per_page=settings.WORDS_PER_PAGE)
        day_chunks = split_text_into_days(markdown_text, days=settings.DAYS_PER_BOOK)
        day_word_counts = [count_words(chunk) for chunk in day_chunks]

        await create_book_with_plan(
            db_path=db_path,
            user_id=message.from_user.id,
            title=base_title,
            file_path=saved_file_path,
            md_path=md_output_path,
            total_words=total_words,
            total_pages=total_pages,
            day_word_counts=day_word_counts,
        )

        await state.clear()

        avg_daily_pages = max(1, round(total_pages / max(1, settings.DAYS_PER_BOOK)))
        plan_preview = "\n".join(
            f"• {i}-күн: ~{max(1, round(w / max(1, settings.WORDS_PER_PAGE)))} бет ({w:,} сөз)"
            for i, w in enumerate(day_word_counts, start=1)
        )

        await status_msg.edit_text(
            f"✅ <b>«{html.escape(base_title)}»</b> сәтті жүктелді!\n\n"
            f"📊 Жалпы көлемі: <b>~{total_pages} бет</b> ({total_words:,} сөз)\n"
            f"📅 Бөліну мерзімі: <b>{settings.DAYS_PER_BOOK} күн</b> "
            f"(орташа күніне ~{avg_daily_pages} бет)\n\n"
            f"<b>Күндер бойынша жоспар:</b>\n{plan_preview}\n\n"
            f"Оқуды бастау үшін <b>«📖 Порция ал»</b> батырмасын басыңыз!"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Кітапты өңдеу кезінде қате шықты:\n<code>{html.escape(str(e))}</code>\n\n"
            "Басқа PDF/EPUB файл жіберіп көріңіз."
        )