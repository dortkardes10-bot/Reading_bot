import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from config import settings
from database.db import (
    ensure_user,
    get_user,
    get_active_book,
    get_read_char_offset,
    get_pending_portion,
    create_portion,
    get_portion_by_id,
    set_portion_status,
    mark_portion_read_and_update_progress,
    get_book_progress_summary,
    update_user_portion_pages,
)
from keyboards.inline import portion_keyboard
from services.progress_service import extract_next_portion, split_message_chunks

router = Router()


async def _send_portion_to_user(
    message: Message,
    user_id: int,
    portion_pages: int | None = None,
) -> None:
    default_reminder = f"{settings.MORNING_HOUR:02d}:{settings.MORNING_MINUTE:02d}"
    db_path = str(settings.DB_PATH)

    await ensure_user(
        db_path=db_path,
        user_id=user_id,
        username=message.from_user.username if message.from_user else None,
        full_name=message.from_user.full_name if message.from_user else None,
        default_reminder_time=default_reminder,
        default_portion_pages=settings.DEFAULT_PORTION_PAGES,
    )

    user = await get_user(db_path, user_id)
    book = await get_active_book(db_path, user_id)

    if not book:
        await message.answer(
            "📚 Сізде әлі белсенді кітап жоқ.\n"
            "Алдымен <b>«📚 Кітап»</b> батырмасын басып, PDF немесе EPUB файл жіберіңіз."
        )
        return

    pages_to_read = portion_pages or (user["portion_pages"] if user else settings.DEFAULT_PORTION_PAGES)
    target_words = max(150, pages_to_read * settings.WORDS_PER_PAGE)

    # Егер бұрын «Кейінірек» деп қалдырылған порция болса, соны қайта ұсыну
    pending = await get_pending_portion(db_path, user_id, book["id"])
    if pending and portion_pages is None:
        portion_id = pending["id"]
        portion_text = pending["content_text"]
        actual_words = pending["words_count"]
        day_num = pending["day_number"]
        await set_portion_status(db_path, portion_id, "pending")
    else:
        start_char = await get_read_char_offset(db_path, book["id"])
        portion_text, actual_words, actual_start, end_char, is_finished = extract_next_portion(
            md_path=book["md_path"],
            start_char=start_char,
            target_words=target_words,
        )

        if not portion_text or is_finished and actual_words == 0:
            await message.answer(
                f"🎉 Құттықтаймын! <b>«{html.escape(book['title'])}»</b> кітабын толық аяқтадыңыз!\n"
                "Жаңа кітап жүктеу үшін <b>«📚 Кітап»</b> батырмасын басыңыз."
            )
            return

        summary = await get_book_progress_summary(db_path, book["id"])
        day_num = summary["current_day"]["day_number"] if summary["current_day"] else 1

        portion_id = await create_portion(
            db_path=db_path,
            user_id=user_id,
            book_id=book["id"],
            day_number=day_num,
            words_count=actual_words,
            start_char=actual_start,
            end_char=end_char,
            content_text=portion_text,
        )

    approx_pages = max(1, round(actual_words / max(1, settings.WORDS_PER_PAGE)))
    chunks = split_message_chunks(portion_text, max_len=3800)

    header = (
        f"📖 <b>{html.escape(book['title'])}</b> — {day_num}-күн\n"
        f"Көлемі: <b>~{approx_pages} бет</b> ({actual_words} сөз) | Бөлік саны: {len(chunks)}"
    )
    await message.answer(header)

    for idx, chunk in enumerate(chunks, start=1):
        safe_chunk = html.escape(chunk)
        if idx < len(chunks):
            await message.answer(f"{safe_chunk}\n\n<i>({idx}/{len(chunks)})</i>")
        else:
            await message.answer(
                f"{safe_chunk}\n\n<i>({idx}/{len(chunks)})</i>",
                reply_markup=portion_keyboard(portion_id),
            )


@router.message(F.text == "📖 Порция ал")
async def on_get_portion(message: Message) -> None:
    await _send_portion_to_user(message=message, user_id=message.from_user.id)


@router.callback_query(F.data.startswith("portion_read:"))
async def on_portion_read(callback: CallbackQuery) -> None:
    portion_id = int(callback.data.split(":", 1)[1])
    portion = await get_portion_by_id(str(settings.DB_PATH), portion_id)

    if not portion:
        await callback.answer("Порция табылмады.", show_alert=True)
        return

    if portion["status"] == "read":
        await callback.answer("Бұл порция бұрыннан «Оқыдым» деп белгіленген.")
        return

    await mark_portion_read_and_update_progress(
        db_path=str(settings.DB_PATH),
        user_id=portion["user_id"],
        book_id=portion["book_id"],
        portion_id=portion_id,
        words_count=portion["words_count"],
    )

    approx_pages = max(1, round(portion["words_count"] / max(1, settings.WORDS_PER_PAGE)))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Тамаша! <b>~{approx_pages} бет</b> ({portion['words_count']} сөз) оқылды деп белгіленді.\n"
        "Келесі бөлік үшін <b>«📖 Порция ал»</b> батырмасын басыңыз."
    )
    await callback.answer("Оқылды деп сақталды!")


@router.callback_query(F.data.startswith("portion_later:"))
async def on_portion_later(callback: CallbackQuery) -> None:
    portion_id = int(callback.data.split(":", 1)[1])
    portion = await get_portion_by_id(str(settings.DB_PATH), portion_id)

    if not portion:
        await callback.answer("Порция табылмады.", show_alert=True)
        return

    await set_portion_status(str(settings.DB_PATH), portion_id, "later")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ Жарайды, порция кейінге қалдырылды.\n"
        "Қайта оқуға дайын болғанда <b>«📖 Порция ал»</b> батырмасын басыңыз — сол жерден жалғастырамыз."
    )
    await callback.answer("Кейінге қалдырылды")


@router.callback_query(F.data.startswith("portion_smaller:"))
async def on_portion_smaller(callback: CallbackQuery) -> None:
    portion_id = int(callback.data.split(":", 1)[1])
    portion = await get_portion_by_id(str(settings.DB_PATH), portion_id)
    user_id = portion["user_id"] if portion else callback.from_user.id

    user = await get_user(str(settings.DB_PATH), user_id)
    current_pages = user["portion_pages"] if user else settings.DEFAULT_PORTION_PAGES
    new_pages = max(3, current_pages - 2)
    await update_user_portion_pages(str(settings.DB_PATH), user_id, new_pages)

    if portion and portion["status"] != "read":
        await set_portion_status(str(settings.DB_PATH), portion_id, "cancelled")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"Порция көлемі ~{new_pages} бетке азайтылды")
    await _send_portion_to_user(message=callback.message, user_id=user_id, portion_pages=new_pages)


@router.callback_query(F.data.startswith("portion_bigger:"))
async def on_portion_bigger(callback: CallbackQuery) -> None:
    portion_id = int(callback.data.split(":", 1)[1])
    portion = await get_portion_by_id(str(settings.DB_PATH), portion_id)
    user_id = portion["user_id"] if portion else callback.from_user.id

    user = await get_user(str(settings.DB_PATH), user_id)
    current_pages = user["portion_pages"] if user else settings.DEFAULT_PORTION_PAGES
    new_pages = min(20, current_pages + 3)
    await update_user_portion_pages(str(settings.DB_PATH), user_id, new_pages)

    if portion and portion["status"] != "read":
        await set_portion_status(str(settings.DB_PATH), portion_id, "cancelled")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"Порция көлемі ~{new_pages} бетке ұлғайтылды")
    await _send_portion_to_user(message=callback.message, user_id=user_id, portion_pages=new_pages)