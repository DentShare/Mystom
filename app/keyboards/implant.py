"""Клавиатуры для имплантологической карты"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


# Зубная формула FDI: 4 ряда
TOOTH_ROWS = [
    [18, 17, 16, 15, 14, 13, 12, 11],  # Верхний правый
    [21, 22, 23, 24, 25, 26, 27, 28],  # Верхний левый
    [31, 32, 33, 34, 35, 36, 37, 38],  # Нижний левый
    [41, 42, 43, 44, 45, 46, 47, 48],  # Нижний правый
]


def get_tooth_chart_keyboard(selected_teeth: list[int]) -> InlineKeyboardMarkup:
    """Карта зубов: 4 строки × 8 столбцов (FDI), мультивыбор"""
    builder = InlineKeyboardBuilder()
    
    for row in TOOTH_ROWS:
        for tooth in row:
            prefix = "✓" if tooth in selected_teeth else ""
            builder.button(
                text=f"{prefix}{tooth}" if prefix else str(tooth),
                callback_data=f"tooth_t_{tooth}"
            )
    
    builder.button(text="✍️ Ввести вручную", callback_data="tooth_manual")
    if selected_teeth:
        builder.button(text="✓ Подтвердить выбор", callback_data="tooth_confirm")
    builder.button(text="❌ Отмена", callback_data="implant_cancel")
    
    # 4 ряда по 8 зубов + кнопки действий в последнюю строку
    action_count = 3 if selected_teeth else 2
    builder.adjust(8, 8, 8, 8, action_count)
    
    return builder.as_markup()


def get_implant_systems_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с популярными системами имплантов"""
    builder = InlineKeyboardBuilder()
    
    popular_systems = [
        "MegaGen", "Osstem", "Straumann", "Nobel",
        "Astra Tech", "Ankylos", "Dentium", "Alpha-Bio"
    ]
    
    for system in popular_systems:
        builder.button(text=system, callback_data=f"system_{system}")
    
    builder.button(text="✍️ Ввести вручную", callback_data="system_custom")
    builder.button(text="❌ Отмена", callback_data="implant_cancel")
    builder.adjust(2, 1)
    
    return builder.as_markup()


# Диаметр: 3.0, 3.3, 3.5, 4.0 ... 8.0 с шагом 0.5
DIAMETER_OPTIONS = [3.0, 3.3, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]

# Длина: 7, 8.5, 10, 11.5, 13, 14.5, 16, 17.5, 18 с шагом 1.5
LENGTH_OPTIONS = [7.0, 8.5, 10.0, 11.5, 13.0, 14.5, 16.0, 17.5, 18.0]


def get_diameter_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора диаметра импланта (мм)"""
    builder = InlineKeyboardBuilder()
    
    for d in DIAMETER_OPTIONS:
        builder.button(text=f"{d} мм", callback_data=f"diam_{d}")
    
    builder.button(text="✍️ Ввести вручную", callback_data="diam_manual")
    builder.button(text="❌ Отмена", callback_data="implant_cancel")
    builder.adjust(4, 1)
    
    return builder.as_markup()


def get_length_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора длины импланта (мм)"""
    builder = InlineKeyboardBuilder()
    
    for L in LENGTH_OPTIONS:
        builder.button(text=f"{L} мм", callback_data=f"len_{L}")
    
    builder.button(text="✍️ Ввести вручную", callback_data="len_manual")
    builder.button(text="❌ Отмена", callback_data="implant_cancel")
    builder.adjust(4, 1)
    
    return builder.as_markup()


# Обратная совместимость
def get_tooth_formula_keyboard() -> InlineKeyboardMarkup:
    """Алиас для карты зубов (одиночный выбор через мультивыбор)"""
    return get_tooth_chart_keyboard([])


def get_implant_sizes_keyboard() -> InlineKeyboardMarkup:
    """Устаревшая клавиатура — используем диаметр и длину отдельно"""
    builder = InlineKeyboardBuilder()
    popular_sizes = ["3.5 x 10.0", "4.0 x 10.0", "4.0 x 11.5", "4.5 x 10.0", "4.5 x 11.5", "5.0 x 10.0", "5.0 x 11.5"]
    for size in popular_sizes:
        builder.button(text=size, callback_data=f"size_{size}")
    builder.button(text="✍️ Ввести вручную", callback_data="size_manual")
    builder.button(text="❌ Отмена", callback_data="implant_cancel")
    builder.adjust(2, 1)
    return builder.as_markup()
