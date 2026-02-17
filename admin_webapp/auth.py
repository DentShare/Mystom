"""Валидация initData Telegram Web App и проверка прав админа."""
import hmac
import hashlib
import json
import logging
import os
import time
from urllib.parse import parse_qs, unquote
from typing import Optional

# initData — это фактически сессионный токен Mini App.
# HMAC-подпись не даёт его подделать; auth_date — дополнительная защита от replay.
# 24 часа — разумный баланс: пользователь не будет держать вкладку дольше.
_MAX_AUTH_AGE_SECONDS = 86400

logger = logging.getLogger(__name__)


def _verify_signature(init_data: str, data_check_string: str, hash_val: str, bot_token: str) -> bool:
    """Проверяет подпись. Возвращает True если hash совпадает.
    По док. Telegram: secret_key = HMAC-SHA256(key='WebAppData', message=bot_token).
    """
    bot_token = (bot_token or "").strip()
    if not bot_token:
        return False
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    calculated = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(calculated, hash_val)


def validate_init_data(init_data: str, bot_token: str) -> Optional[int]:
    """
    Проверяет подпись initData и возвращает telegram user_id при успехе, иначе None.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Алгоритм (подтверждён эмпирически):
    1. Разбить RAW initData по '&' (до URL-декодирования — безопасное разделение).
    2. Извлечь hash, остальные пары — URL-декодировать значения.
    3. Отсортировать по ключу, склеить через '\\n' в формате key=decoded_value.
    4. HMAC-SHA256(secret, data_check_string) должен совпасть с hash.
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
        # Шаг 1-2: split по RAW '&', декодируем значения, hash извлекаем отдельно
        pairs = []
        hash_val = None
        for part in init_data.split("&"):
            if "=" not in part:
                continue
            key, _, raw_value = part.partition("=")
            if key == "hash":
                hash_val = raw_value
            else:
                pairs.append((key, unquote(raw_value)))
        if not hash_val:
            logger.warning("validate_init_data: отсутствует hash в initData")
            return None

        # Шаг 3: сортировка + data_check_string
        pairs.sort(key=lambda x: x[0])
        data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
        logger.info(
            "validate_init_data: dcs len=%d, keys=%s",
            len(data_check_string),
            [k for k, _ in pairs],
        )

        # Шаг 4: HMAC-SHA256
        if not _verify_signature(init_data, data_check_string, hash_val, bot_token):
            logger.warning(
                "validate_init_data: неверная подпись (BOT_TOKEN len=%d, hash=%s…)",
                len(bot_token), hash_val[:12],
            )
            return None

        # Проверяем auth_date
        pairs_dict = dict(pairs)
        auth_date_str = pairs_dict.get("auth_date")
        if auth_date_str:
            try:
                age = time.time() - int(auth_date_str)
                if age > _MAX_AUTH_AGE_SECONDS:
                    logger.warning(
                        "validate_init_data: initData устарела — возраст=%.0f сек (макс %d)",
                        age, _MAX_AUTH_AGE_SECONDS,
                    )
                    return None
            except (ValueError, TypeError):
                pass

        # Извлекаем user
        user_json = pairs_dict.get("user")
        if not user_json:
            logger.warning("validate_init_data: в initData нет поля user")
            return None
        data = json.loads(user_json)
        user_id = int(data["id"])
        logger.info("validate_init_data: OK, user_id=%s", user_id)
        return user_id
    except Exception as e:
        logger.exception("validate_init_data: ошибка парсинга initData — %s", e)
        return None
