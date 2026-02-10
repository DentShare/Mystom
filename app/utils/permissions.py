"""
Права ассистента по разделам бота.
Уровни: "none" — нет доступа, "view" — просмотр, "edit" — просмотр и редактирование.
"""
from typing import Dict, Any

# Ключи разделов (совпадают с кнопками/хендлерами)
FEATURE_CALENDAR = "calendar"
FEATURE_PATIENTS = "patients"
FEATURE_HISTORY = "history"
FEATURE_IMPLANTS = "implants"
FEATURE_SERVICES = "services"
FEATURE_FINANCE = "finance"
FEATURE_EXPORT = "export"
FEATURE_SETTINGS = "settings"

ALL_FEATURES = [
    FEATURE_CALENDAR,
    FEATURE_PATIENTS,
    FEATURE_HISTORY,
    FEATURE_IMPLANTS,
    FEATURE_SERVICES,
    FEATURE_FINANCE,
    FEATURE_EXPORT,
    FEATURE_SETTINGS,
]

# Человекочитаемые названия для настроек
FEATURE_LABELS = {
    FEATURE_CALENDAR: "Календарь / расписание",
    FEATURE_PATIENTS: "Пациенты",
    FEATURE_HISTORY: "История болезни",
    FEATURE_IMPLANTS: "Импланты",
    FEATURE_SERVICES: "Прайс-лист",
    FEATURE_FINANCE: "Финансы",
    FEATURE_EXPORT: "Экспорт",
    FEATURE_SETTINGS: "Настройки (ограничено)",
}

LEVEL_NONE = "none"
LEVEL_VIEW = "view"
LEVEL_EDIT = "edit"


def default_permissions() -> Dict[str, str]:
    """Права по умолчанию для нового ассистента: просмотр основных разделов."""
    return {
        FEATURE_CALENDAR: LEVEL_VIEW,
        FEATURE_PATIENTS: LEVEL_VIEW,
        FEATURE_HISTORY: LEVEL_VIEW,
        FEATURE_IMPLANTS: LEVEL_VIEW,
        FEATURE_SERVICES: LEVEL_VIEW,
        FEATURE_FINANCE: LEVEL_NONE,
        FEATURE_EXPORT: LEVEL_NONE,
        FEATURE_SETTINGS: LEVEL_NONE,
    }


def full_permissions() -> Dict[str, str]:
    """Все права на редактирование (для владельца)."""
    return {f: LEVEL_EDIT for f in ALL_FEATURES}


def normalize_permissions(perms: Dict[str, Any] | None) -> Dict[str, str]:
    """Приводит словарь прав к виду {feature: level}."""
    if not perms:
        return default_permissions()
    out = default_permissions().copy()
    for k in ALL_FEATURES:
        if k in perms and perms[k] in (LEVEL_NONE, LEVEL_VIEW, LEVEL_EDIT):
            out[k] = perms[k]
    return out


def can_access(permissions: Dict[str, str], feature: str, required_level: str = LEVEL_VIEW) -> bool:
    """
    Проверяет доступ к разделу.
    required_level: "view" — достаточно просмотра, "edit" — нужно право на редактирование.
    """
    level = permissions.get(feature, LEVEL_NONE)
    if level == LEVEL_NONE:
        return False
    if required_level == LEVEL_VIEW:
        return level in (LEVEL_VIEW, LEVEL_EDIT)
    if required_level == LEVEL_EDIT:
        return level == LEVEL_EDIT
    return False
