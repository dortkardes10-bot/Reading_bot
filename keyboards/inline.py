from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def portion_keyboard(portion_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Оқыдым",
                    callback_data=f"portion_read:{portion_id}",
                ),
                InlineKeyboardButton(
                    text="⏳ Кейінірек",
                    callback_data=f"portion_later:{portion_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➖ Азырақ",
                    callback_data=f"portion_smaller:{portion_id}",
                ),
                InlineKeyboardButton(
                    text="➕ Көбірек",
                    callback_data=f"portion_bigger:{portion_id}",
                ),
            ],
        ]
    )


def morning_norm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Қабылдаймын",
                    callback_data="morning_accept",
                ),
                InlineKeyboardButton(
                    text="⏳ Кейінірек",
                    callback_data="morning_later",
                ),
            ]
        ]
    )


def evening_catchup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Иә",
                    callback_data="evening_catchup_yes",
                ),
                InlineKeyboardButton(
                    text="❌ Жоқ",
                    callback_data="evening_catchup_no",
                ),
            ]
        ]
    )