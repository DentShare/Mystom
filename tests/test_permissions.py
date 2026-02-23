"""Тесты для app.utils.permissions."""
from app.utils.permissions import (
    can_access, default_permissions, full_permissions, normalize_permissions,
    FEATURE_CALENDAR, FEATURE_FINANCE, FEATURE_SERVICES,
    LEVEL_NONE, LEVEL_VIEW, LEVEL_EDIT,
)


class TestCanAccess:
    def test_edit_allows_edit(self, owner_permissions):
        assert can_access(owner_permissions, FEATURE_CALENDAR, "edit") is True

    def test_view_blocks_edit(self, view_only_permissions):
        assert can_access(view_only_permissions, FEATURE_CALENDAR, "edit") is False

    def test_edit_allows_view(self, owner_permissions):
        assert can_access(owner_permissions, FEATURE_CALENDAR, "view") is True

    def test_view_allows_view(self, view_only_permissions):
        assert can_access(view_only_permissions, FEATURE_CALENDAR, "view") is True

    def test_none_blocks_view(self, no_permissions):
        assert can_access(no_permissions, FEATURE_CALENDAR, "view") is False

    def test_none_blocks_edit(self, no_permissions):
        assert can_access(no_permissions, FEATURE_CALENDAR, "edit") is False

    def test_missing_feature_returns_false(self):
        assert can_access({}, FEATURE_CALENDAR) is False


class TestDefaultPermissions:
    def test_finance_is_none(self):
        perms = default_permissions()
        assert perms[FEATURE_FINANCE] == LEVEL_NONE

    def test_calendar_is_view(self):
        perms = default_permissions()
        assert perms[FEATURE_CALENDAR] == LEVEL_VIEW


class TestFullPermissions:
    def test_all_edit(self):
        perms = full_permissions()
        for level in perms.values():
            assert level == LEVEL_EDIT


class TestNormalizePermissions:
    def test_fills_missing_with_defaults(self):
        partial = {FEATURE_CALENDAR: LEVEL_EDIT}
        result = normalize_permissions(partial)
        assert result[FEATURE_CALENDAR] == LEVEL_EDIT
        assert result[FEATURE_FINANCE] == LEVEL_NONE

    def test_rejects_invalid_level(self):
        bad = {FEATURE_CALENDAR: "admin"}
        result = normalize_permissions(bad)
        # Невалидный уровень → откат к дефолту для этого раздела
        assert result[FEATURE_CALENDAR] == LEVEL_VIEW

    def test_none_input_returns_defaults(self):
        result = normalize_permissions(None)
        assert result == default_permissions()

    def test_empty_dict_returns_defaults(self):
        result = normalize_permissions({})
        assert result == default_permissions()
