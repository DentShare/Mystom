"""Тесты валидации initData Telegram Web App."""
import hashlib
import hmac
import json
import time

import pytest

from admin_webapp.auth import validate_init_data, _verify_signature


def _build_init_data(bot_token: str, user_id: int = 123456, extra_pairs: dict | None = None, expire: bool = False) -> str:
    """Помощник: собирает валидный initData с корректной HMAC-подписью."""
    auth_date = str(int(time.time()) - (90000 if expire else 10))
    user_json = json.dumps({"id": user_id, "first_name": "Test"})

    pairs = {"auth_date": auth_date, "user": user_json}
    if extra_pairs:
        pairs.update(extra_pairs)

    # data_check_string: отсортированные key=value через \n
    sorted_pairs = sorted(pairs.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_pairs)

    # HMAC
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    # URL-encode не нужен для теста (значения без спецсимволов кроме user json)
    from urllib.parse import quote
    raw_parts = []
    for k, v in pairs.items():
        raw_parts.append(f"{k}={quote(v)}")
    raw_parts.append(f"hash={hash_val}")
    return "&".join(raw_parts)


BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ"


class TestValidateInitData:
    """Тесты validate_init_data."""

    def test_valid_init_data(self):
        init_data = _build_init_data(BOT_TOKEN, user_id=42)
        result = validate_init_data(init_data, BOT_TOKEN)
        assert result == 42

    def test_wrong_bot_token(self):
        init_data = _build_init_data(BOT_TOKEN, user_id=42)
        result = validate_init_data(init_data, "wrong_token")
        assert result is None

    def test_empty_init_data(self):
        assert validate_init_data("", BOT_TOKEN) is None
        assert validate_init_data(None, BOT_TOKEN) is None

    def test_empty_bot_token(self):
        init_data = _build_init_data(BOT_TOKEN)
        assert validate_init_data(init_data, "") is None
        assert validate_init_data(init_data, None) is None

    def test_expired_init_data(self):
        init_data = _build_init_data(BOT_TOKEN, expire=True)
        result = validate_init_data(init_data, BOT_TOKEN)
        assert result is None

    def test_missing_hash(self):
        # initData без hash
        init_data = "auth_date=1234567890&user=%7B%22id%22%3A42%7D"
        result = validate_init_data(init_data, BOT_TOKEN)
        assert result is None

    def test_missing_user_field(self):
        """initData без поля user — подпись верна, но user отсутствует."""
        auth_date = str(int(time.time()) - 10)
        pairs = {"auth_date": auth_date, "query_id": "AAA"}
        sorted_pairs = sorted(pairs.items())
        dcs = "\n".join(f"{k}={v}" for k, v in sorted_pairs)
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        init_data = f"auth_date={auth_date}&query_id=AAA&hash={h}"
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_tampered_data(self):
        init_data = _build_init_data(BOT_TOKEN, user_id=42)
        # Подмена user_id в строке
        tampered = init_data.replace("42", "99")
        result = validate_init_data(tampered, BOT_TOKEN)
        assert result is None

    def test_extra_fields_preserved(self):
        """Дополнительные поля не ломают валидацию."""
        init_data = _build_init_data(BOT_TOKEN, user_id=7, extra_pairs={"chat_instance": "12345"})
        result = validate_init_data(init_data, BOT_TOKEN)
        assert result == 7


class TestVerifySignature:
    """Тесты внутренней функции _verify_signature."""

    def test_correct_signature(self):
        dcs = "auth_date=1234"
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        assert _verify_signature("raw", dcs, h, BOT_TOKEN) is True

    def test_wrong_signature(self):
        assert _verify_signature("raw", "auth_date=1234", "deadbeef", BOT_TOKEN) is False

    def test_empty_token(self):
        assert _verify_signature("raw", "data", "hash", "") is False
