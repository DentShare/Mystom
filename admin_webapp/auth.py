"""Валидация initData Telegram Web App и проверка прав админа."""
import hmac
import hashlib
from urllib.parse import parse_qs, unquote
from typing import Optional


def validate_init_data(init_data: str, bot_token: str) -> Optional[int]:
    """
    Проверяет подпись initData и возвращает telegram user_id при успехе, иначе None.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed = parse_qs(unquote(init_data), keep_blank_values=True)
        hash_val = parsed.get("hash")
        if not hash_val or len(hash_val) != 1:
            return None
        hash_val = hash_val[0]
        # data_check_string: пары key=value без hash, отсортированы по key
        pairs = sorted(
            (k, v[0] if isinstance(v, list) else v)
            for k, v in parsed.items()
            if k != "hash"
        )
        data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
        # secret_key = HMAC-SHA256(token, "WebAppData")
        secret_key = hmac.new(
            bot_token.encode(), b"WebAppData", hashlib.sha256
        ).digest()
        # calculated_hash = HMAC-SHA256(secret_key, data_check_string)
        calculated = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated, hash_val):
            return None
        user = parsed.get("user")
        if not user:
            return None
        user_str = user[0] if isinstance(user, list) else user
        # user — JSON строка, нужен id
        import json
        data = json.loads(user_str)
        return int(data.get("id"))
    except Exception:
        return None
