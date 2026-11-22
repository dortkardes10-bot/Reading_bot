import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import settings
from database.db import init_db, ensure_user
from handlers import book, portion, progress, settings_cmd
from keyboards.reply import main_menu
from services.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db(str(settings.DB_PATH))

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(book.router)
    dp.include_router(portion.router)
    dp.include_router(progress.router)
    dp.include_router(settings_cmd.router)

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        default_reminder = f"{settings.MORNING_HOUR:02d}:{settings.MORNING_MINUTE:02d}"
        await ensure_user(
            db_path=str(settings.DB_PATH),
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            default_reminder_time=default_reminder,
            default_portion_pages=settings.DEFAULT_PORTION_PAGES,
        )
        await message.answer(
            f"Сәлем, {message.from_user.first_name}! 👋\n\n"
            "Мен сенің жеке оқу көмекшіңмін.\n"
            "Аптасына бір кітапты аяқтауға көмектесемін.\n\n"
            "Төмендегі батырмаларды пайдаланыңыз:",
            reply_markup=main_menu(),
        )

    scheduler = setup_scheduler(bot)
    scheduler.start()

    logger.info("Бот және жоспарлағыш (APScheduler) іске қосылуда...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот тоқтатылды")