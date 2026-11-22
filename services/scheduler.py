import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database.db import (
    get_all_active_users,
    get_active_book,
    get_book_progress_summary,
    get_unfinished_day_for_evening_prompt,
    mark_evening_prompted,
)
from keyboards.inline import morning_norm_keyboard, evening_catchup_keyboard

logger = logging.getLogger(__name__)


async def _check_and_send_morning_reminders(bot: Bot) -> None:
    tz = ZoneInfo(settings.TIMEZONE)
    now_hm = datetime.now(tz).strftime("%H:%M")

    users = await get_all_active_users(str(settings.DB_PATH))
    for user in users:
        if user.get("reminder_time") != now_hm:
            continue

        book = await get_active_book(str(settings.DB_PATH), user["user_id"])
        if not book or book.get("is_completed"):
            continue

        summary = await get_book_progress_summary(str(settings.DB_PATH), book["id"])
        current_day = summary.get("current_day")
        if not current_day or current_day.get("is_completed"):
            continue

        remaining_words = max(0, current_day["target_words"] - current_day["read_words"])
        approx_pages = max(1, round(remaining_words / max(1, settings.WORDS_PER_PAGE)))

        try:
            await bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"☀️ Қайырлы таң! <b>{html.escape(book['title'])}</b> ({current_day['day_number']}-күн)\n"
                    f"Бүгінгі норма: <b>~{approx_pages} бет</b>\n\n"
                    "Оқуға кірісеміз бе?"
                ),
                reply_markup=morning_norm_keyboard(),
            )
        except Exception as e:
            logger.warning("Таңертеңгі хабарлама жіберілмеді (user=%s): %s", user["user_id"], e)


async def _check_and_send_evening_prompts(bot: Bot) -> None:
    users = await get_all_active_users(str(settings.DB_PATH))
    for user in users:
        book = await get_active_book(str(settings.DB_PATH), user["user_id"])
        if not book or book.get("is_completed"):
            continue

        unfinished = await get_unfinished_day_for_evening_prompt(str(settings.DB_PATH), book["id"])
        if not unfinished:
            continue

        try:
            await bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"🌙 <b>{html.escape(book['title'])}</b> ({unfinished['day_number']}-күн)\n"
                    "Бүгінгі норма аяқталмады. Ертең екі күннің порциясын бірге оқи аласыз ба?"
                ),
                reply_markup=evening_catchup_keyboard(),
            )
            await mark_evening_prompted(str(settings.DB_PATH), unfinished["id"])
        except Exception as e:
            logger.warning("Кешкі сұрақ жіберілмеді (user=%s): %s", user["user_id"], e)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    tz = ZoneInfo(settings.TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(
        _check_and_send_morning_reminders,
        trigger="cron",
        minute="*",
        args=[bot],
        id="morning_reminders_job",
        replace_existing=True,
    )

    scheduler.add_job(
        _check_and_send_evening_prompts,
        trigger="cron",
        hour=21,
        minute=0,
        args=[bot],
        id="evening_prompts_job",
        replace_existing=True,
    )

    return scheduler