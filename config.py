from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    BOT_TOKEN: str
    TIMEZONE: str = "Asia/Almaty"

    BASE_DIR: Path = Path(__file__).parent
    DATA_DIR: Path = BASE_DIR / "data"
    BOOKS_DIR: Path = DATA_DIR / "books"
    DB_PATH: Path = DATA_DIR / "reading_bot.db"

    WORDS_PER_PAGE: int = 290
    DAYS_PER_BOOK: int = 7
    DEFAULT_PORTION_PAGES: int = 7
    MORNING_HOUR: int = 9
    MORNING_MINUTE: int = 55


settings = Settings()

settings.BOOKS_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)