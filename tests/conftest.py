"""Общие фикстуры для тестов."""
import pytest
from app.utils.permissions import (
    full_permissions, default_permissions,
    FEATURE_CALENDAR, FEATURE_PATIENTS, FEATURE_HISTORY,
    FEATURE_IMPLANTS, FEATURE_SERVICES, FEATURE_FINANCE,
    FEATURE_EXPORT, FEATURE_SETTINGS,
    LEVEL_NONE, LEVEL_VIEW, LEVEL_EDIT,
)


@pytest.fixture
def owner_permissions():
    """Полные права (врач/владелец)."""
    return full_permissions()


@pytest.fixture
def default_assistant_permissions():
    """Права ассистента по умолчанию."""
    return default_permissions()


@pytest.fixture
def view_only_permissions():
    """Все разделы — только просмотр."""
    return {f: LEVEL_VIEW for f in [
        FEATURE_CALENDAR, FEATURE_PATIENTS, FEATURE_HISTORY,
        FEATURE_IMPLANTS, FEATURE_SERVICES, FEATURE_FINANCE,
        FEATURE_EXPORT, FEATURE_SETTINGS,
    ]}


@pytest.fixture
def no_permissions():
    """Нет доступа ни к чему."""
    return {f: LEVEL_NONE for f in [
        FEATURE_CALENDAR, FEATURE_PATIENTS, FEATURE_HISTORY,
        FEATURE_IMPLANTS, FEATURE_SERVICES, FEATURE_FINANCE,
        FEATURE_EXPORT, FEATURE_SETTINGS,
    ]}
