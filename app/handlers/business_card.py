from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.database.models import User

router = Router(name="business_card")


@router.message(Command("visiting_card"))
@router.message(F.text == "👤 Визитка")
async def cmd_visiting_card(message: Message, user: User):
    """Генерация визитки врача — переслайте сообщение, чтобы поделиться"""
    card_text = _format_business_card_text(user)

    if user.photo_url:
        await message.answer_photo(
            photo=user.photo_url,
            caption=card_text
        )
    else:
        await message.answer(card_text)

    # Подсказка и кнопка «Назад»
    back_keyboard = ReplyKeyboardBuilder()
    back_keyboard.button(text="⬅️ Назад в меню")
    await message.answer(
        "💡 *Чтобы поделиться:* удерживайте сообщение выше и нажмите «Переслать»",
        reply_markup=back_keyboard.as_markup(resize_keyboard=True)
    )


def _format_business_card_text(user: User) -> str:
    """Форматирование визитки — все поля регистрации + ссылка на навигатор"""
    lines = [
        "👤 **ВИЗИТКА ВРАЧА**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👨‍⚕️ **{user.full_name or 'Не указано'}**",
        f"🏥 Специализация: {user.specialization or 'Не указано'}",
        f"📞 Телефон: {user.phone or 'Не указан'}",
        f"📍 Адрес: {user.address or 'Не указан'}",
        "",
    ]

    if user.location_lat and user.location_lon:
        maps_url = f"https://www.google.com/maps?q={user.location_lat},{user.location_lon}"
        yandex_url = f"https://yandex.ru/maps/?pt={user.location_lon},{user.location_lat}&z=17"
        lines.append(f"🗺 [Открыть в Google Maps]({maps_url})")
        lines.append(f"🗺 [Открыть в Яндекс.Картах]({yandex_url})")
        lines.append("")
    else:
        lines.append("🗺 Местоположение: не указано")
        lines.append("")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        "💡 Удерживайте сообщение и нажмите «Переслать» чтобы поделиться",
    ])

    return "\n".join(lines)

