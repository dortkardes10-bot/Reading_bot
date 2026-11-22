import html
import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from config import settings
from database.db import (
    ensure_user,
    get_user,
    get_active_book,
    get_user_books_stats,
    get_book_progress_summary,
    update_user_reminder_time,
    set_user_paused,
    skip_current_day_plan,
    apply_catchup_decision,
)
from handlers.portion import _send_portion_to_user

router = Router()

TIME_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


async def _ensure(message: Message) -> None:
    default_reminder = f"{settings.MORNING_HOUR:02d}:{settings.MORNING_MINUTE:02d}"
    await ensure_user(
        db_path=str(settings.DB_PATH),
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        default_reminder_time=default_reminder,
        default_portion_pages=settings.DEFAULT_PORTION_PAGES,
    )


@router.message(F.text == "⚙️ Баптаулар")
@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    await _ensure(message)
    user = await get_user(str(settings.DB_PATH), message.from_user.id)

    reminder = user["reminder_time"] if user else f"{settings.MORNING_HOUR:02d}:{settings.MORNING_MINUTE:02d}"
    portion_pages = user["portion_pages"] if user else settings.DEFAULT_PORTION_PAGES
    paused_text = "⏸ Кідірісте (`/resume` арқылы қос)" if (user and user["is_paused"]) else "▶️ Белсенді (`/pause` арқылы тоқтат)"

    await message.answer(
        "⚙️ <b>Баптаулар мен командалар</b>\n\n"
        f"⏰ Таңертеңгі еске салғыш уақыты: <b>{reminder}</b>\n"
        f"📖 Бір порция көлемі: <b>~{portion_pages} бет</b>\n"
        f"🔔 Хабарлама күйі: <b>{paused_text}</b>\n\n"
        "<b>Пайдалы командалар:</b>\n"
        "• <code>/time 08:30</code> — еске салғыш уақытын өзгерту\n"
        "• <code>/today</code> — бүгінгі норманы көру\n"
        "• <code>/stats</code> — жалпы оқу статистикасы\n"
        "• <code>/pause</code> / <code>/resume</code> — еске салғышты уақытша тоқтату/қосу\n"
        "• <code>/skip_day</code> — бүгінгі күнді өткізіп, қалғанын бөлу\n"
        "• <code>/book</code> — жаңа кітап жүктеу"
    )


@router.message(Command("time"))
async def cmd_set_time(message: Message) -> None:
    await _ensure(message)
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2 or not TIME_REGEX.match(parts[1].strip()):
        await message.answer(
            "⚠️ Формат қате. Мысалы: <code>/time 08:30</code> немесе <code>/time 09:55</code>"
        )
        return

    new_time = parts[1].strip()
    await update_user_reminder_time(str(settings.DB_PATH), message.from_user.id, new_time)
    await message.answer(f"✅ Таңертеңгі еске салғыш уақыты <b>{new_time}</b> етіп өзгертілді.")


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    await _ensure(message)
    await set_user_paused(str(settings.DB_PATH), message.from_user.id, True)
    await message.answer("⏸ Еске салғыштар уақытша тоқтатылды. Қайта қосу үшін <code>/resume</code> жазыңыз.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    await _ensure(message)
    await set_user_paused(str(settings.DB_PATH), message.from_user.id, False)
    await message.answer("▶️ Еске салғыштар қайта қосылды!")


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    await _ensure(message)
    book = await get_active_book(str(settings.DB_PATH), message.from_user.id)
    if not book:
        await message.answer("📚 Белсенді кітап жоқ. Алдымен <b>«📚 Кітап»</b> арқылы кітап жүктеңіз.")
        return

    summary = await get_book_progress_summary(str(settings.DB_PATH), book["id"])
    cur_day = summary.get("current_day")
    if not cur_day:
        await message.answer(f"🎉 <b>«{html.escape(book['title'])}»</b> кітабының жоспары аяқталған.")
        return

    target_pages = max(1, round(cur_day["target_words"] / max(1, settings.WORDS_PER_PAGE)))
    read_pages = round(cur_day["read_words"] / max(1, settings.WORDS_PER_PAGE))
    rem_pages = max(0, target_pages - read_pages)

    await message.answer(
        f"📅 <b>Бүгінгі норма — {html.escape(book['title'])}</b> ({cur_day['day_number']}-күн)\n"
        f"• Жоспар: <b>~{target_pages} бет</b>\n"
        f"• Оқылды: <b>~{read_pages} бет</b>\n"
        f"• Қалды: <b>~{rem_pages} бет</b>\n\n"
        "Оқу үшін <b>«📖 Порция ал»</b> батырмасын басыңыз."
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    await _ensure(message)
    user = await get_user(str(settings.DB_PATH), message.from_user.id)
    books = await get_user_books_stats(str(settings.DB_PATH), message.from_user.id)

    completed_books = sum(1 for b in books if b.get("is_completed"))
    total_read_words = sum(b.get("read_words", 0) for b in books)
    total_read_pages = round(total_read_words / max(1, settings.WORDS_PER_PAGE))
    streak = user["streak_days"] if user else 0

    await message.answer(
        "📈 <b>Жалпы оқу статистикасы</b>\n\n"
        f"• Жүктелген кітап саны: <b>{len(books)}</b>\n"
        f"• Аяқталған кітап саны: <b>{completed_books}</b>\n"
        f"• Барлық оқылған бет: <b>~{total_read_pages} бет</b> ({total_read_words:,} сөз)\n"
        f"• Қатарынан оқылған күн: <b>{streak} күн</b>"
    )


@router.message(Command("skip_day"))
async def cmd_skip_day(message: Message) -> None:
    await _ensure(message)
    book = await get_active_book(str(settings.DB_PATH), message.from_user.id)
    if not book:
        await message.answer("📚 Белсенді кітап жоқ.")
        return

    skipped = await skip_current_day_plan(str(settings.DB_PATH), book["id"])
    if not skipped:
        await message.answer("Өткізетін аяқталмаған күн табылмады.")
        return

    await message.answer(
        f"⏭ <b>{skipped['day_number']}-күн</b> жоспары өткізілді. "
        "Қалған көлем келесі күндерге тең бөлінді."
    )


@router.callback_query(F.data == "morning_accept")
async def on_morning_accept(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Жақсы, алғашқы порцияны жіберемін!")
    await _send_portion_to_user(message=callback.message, user_id=callback.from_user.id)


@router.callback_query(F.data == "morning_later")
async def on_morning_later(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ Жақсы, кейінірек оқимыз. Ыңғайлы кезде <b>«📖 Порция ал»</b> батырмасын басыңыз."
    )
    await callback.answer("Кейінге қалдырылды")


@router.callback_query(F.data == "evening_catchup_yes")
async def on_evening_catchup_yes(callback: CallbackQuery) -> None:
    book = await get_active_book(str(settings.DB_PATH), callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)

    if not book:
        await callback.answer("Белсенді кітап табылмады.", show_alert=True)
        return

    res = await apply_catchup_decision(str(settings.DB_PATH), book["id"], double_tomorrow=True)
    if res and res.get("next_day_target"):
        next_pages = max(1, round(res["next_day_target"] / max(1, settings.WORDS_PER_PAGE)))
        await callback.message.answer(
            f"💪 Керемет! Ертеңгі (<b>{res.get('next_day_number', 'келесі')}-күн</b>) нормаға бүгінгі бөлік қосылды.\n"
            f"Ертеңгі жалпы норма: <b>~{next_pages} бет</b>."
        )
    else:
        await callback.message.answer("✅ Ертеңгі жоспар жаңартылды.")
    await callback.answer("Ертеңге қосылды")


@router.callback_query(F.data == "evening_catchup_no")
async def on_evening_catchup_no(callback: CallbackQuery) -> None:
    book = await get_active_book(str(settings.DB_PATH), callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)

    if not book:
        await callback.answer("Белсенді кітап табылмады.", show_alert=True)
        return

    await apply_catchup_decision(str(settings.DB_PATH), book["id"], double_tomorrow=False)
    await callback.message.answer(
        "👌 Түсінікті, қалған бөлікті қалған күндерге біркелкі қайта бөлдім. "
        "Бастысы — жүйені үзбеу!"
    )
    await callback.answer("Қалған күндерге бөлінді")