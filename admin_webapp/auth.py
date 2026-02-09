"""Валидация initData Telegram Web App и проверка прав админа."""
import hmac
import hashlib
import json
import logging
from urllib.parse import parse_qs, unquote
from typing import Optional

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str, bot_token: str) -> Optional[int]:
    """
    Проверяет подпись initData и возвращает telegram user_id при успехе, иначе None.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Важно: data_check_string собирается из исходной строки (пары key=value как есть),
    без URL-декодирования — иначе подпись не сойдётся.
    """
    bot_token = (bot_token or "").strip()
    if not init_data or not bot_token:
        logger.warning(
            "validate_init_data: пустые данные — init_data=%s, bot_token_set=%s",
            "empty" if not init_data else f"len={len(init_data)}",
            bool(bot_token),
        )
        return None
    try:
        # Собираем data_check_string из исходной строки (значения не декодируем)
        pairs_raw = []
        hash_val = None
        for part in init_data.split("&"):
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            if key == "hash":
                hash_val = value
            else:
                pairs_raw.append((key, value))
        if not hash_val:
            logger.warning("validate_init_data: отсутствует hash в initData")
            return None
        pairs_raw.sort(key=lambda x: x[0])
        data_check_string = "\n".join(f"{k}={v}" for k, v in pairs_raw)

        # secret_key = HMAC-SHA256(token, "WebAppData")
        secret_key = hmac.new(
            bot_token.encode("utf-8"), b"WebAppData", hashlib.sha256
        ).digest()
        # calculated_hash = HMAC-SHA256(secret_key, data_check_string)
        calculated = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated, hash_val):
            logger.warning(
                "validate_init_data: неверная подпись — проверьте BOT_TOKEN (должен совпадать с токеном бота)"
            )
            return None

        # Парсим для извлечения user (уже с декодированием)
        parsed = parse_qs(unquote(init_data), keep_blank_values=True)
        user = parsed.get("user")
        if not user:
            logger.warning("validate_init_data: в initData нет поля user")
            return None
        user_str = user[0] if isinstance(user, list) else user
        data = json.loads(user_str)
        user_id = int(data.get("id"))
        logger.info("validate_init_data: OK, user_id=%s", user_id)
        return user_id
    except Exception as e:
        logger.exception("validate_init_data: ошибка парсинга initData — %s", e)
        return None
