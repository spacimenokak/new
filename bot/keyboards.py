from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_action_keyboard(target_user_id: int):
    """Кнопки для лайка/скипа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❤️ Лайк", callback_data=f"like:{target_user_id}"),
            InlineKeyboardButton(text="❌ Скип", callback_data=f"skip:{target_user_id}")
        ],
        [InlineKeyboardButton(text="💤 Спящий режим", callback_data="sleep")]
    ])