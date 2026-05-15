"""Общая разметка меню редактирования анкеты (inline)."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def profile_edit_fields_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Имя", callback_data="crud:f:name"),
                InlineKeyboardButton(text="Возраст", callback_data="crud:f:age"),
            ],
            [
                InlineKeyboardButton(text="Город", callback_data="crud:f:city"),
                InlineKeyboardButton(text="Пол", callback_data="crud:f:gender"),
            ],
            [
                InlineKeyboardButton(text="О себе", callback_data="crud:f:bio"),
                InlineKeyboardButton(text="Интересы", callback_data="crud:f:interests"),
            ],
            [
                InlineKeyboardButton(text="Возраст ОТ", callback_data="crud:f:pref_from"),
                InlineKeyboardButton(text="Возраст ДО", callback_data="crud:f:pref_to"),
            ],
            [
                InlineKeyboardButton(text="Кого ищу", callback_data="crud:f:pref_gender"),
                InlineKeyboardButton(text="Фото (URL)", callback_data="crud:f:photos"),
            ],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="crud:cancel")],
        ]
    )


def profile_delete_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data="crud:del_yes"),
                InlineKeyboardButton(text="Отмена", callback_data="crud:cancel_del"),
            ]
        ]
    )
