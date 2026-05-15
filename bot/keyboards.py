from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Тексты кнопок главного меню (используются и в F.text-хендлерах)
BTN_NEXT_PROFILE = "🔍 Следующая анкета"
BTN_PAUSE_DATING = "💤 Устал знакомиться"
BTN_RESUME_DATING = "🔍 Снова знакомиться"
BTN_EDIT_MY_PROFILE = "✏️ Редактировать мою анкету"
BTN_DELETE_MY_PROFILE = "🗑 Удалить мою анкету"


def registered_reply_kb() -> ReplyKeyboardMarkup:
    """Постоянное меню для зарегистрированных пользователей."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEXT_PROFILE)],
            [KeyboardButton(text=BTN_PAUSE_DATING)],
            [
                KeyboardButton(text=BTN_EDIT_MY_PROFILE),
                KeyboardButton(text=BTN_DELETE_MY_PROFILE),
            ],
        ],
        resize_keyboard=True,
    )


def get_action_keyboard(target_user_id: int):
    """Кнопки для лайка/скипа"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"like:{target_user_id}"),
                InlineKeyboardButton(text="❌ Скип", callback_data=f"skip:{target_user_id}"),
            ],
        ]
    )


def gender_registration_kb() -> ReplyKeyboardMarkup:
    """Только мужской / женский (+ пропуск поля)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Мужской"),
                KeyboardButton(text="Женский"),
            ],
            [KeyboardButton(text="Пропустить пол")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выбери пол или «Пропустить пол»",
    )


def partner_pref_gender_kb() -> ReplyKeyboardMarkup:
    """Кого ищешь в паре."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Мужчин"),
                KeyboardButton(text="Женщин"),
            ],
            [KeyboardButton(text="Неважно")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Мужчин / Женщин / Неважно",
    )


def get_match_keyboard(partner_id: int):
    """После мэтча — отметить инициацию диалога (поведенческий рейтинг)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ Я написал(а) первым(ой)",
                    callback_data=f"chat_init:{partner_id}",
                )
            ]
        ]
    )