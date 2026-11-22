from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton(text="📖 Порция ал"),
            KeyboardButton(text="📊 Бүгінгі прогресс"),
        ],
        [
            KeyboardButton(text="📚 Кітап"),
            KeyboardButton(text="⚙️ Баптаулар"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Команданы таңдаңыз..."
    )