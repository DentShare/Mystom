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
        # Собираем data_check_string: все пары key=value КРОМЕ hash.
        # Значения как в строке (без URL-декодирования) — Telegram подписывает сырую строку.
        # Поле signature (если есть) ВКЛЮЧАЕМ — по документации убирается только hash.
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
        keys_in_order = [k for k, _ in pairs_raw]
        logger.info(
            "validate_init_data: data_check_string len=%d, keys=%s",
            len(data_check_string),
            keys_in_order,
        )

        # Сначала пробуем переданный токен (из Config)
        if _verify_signature(init_data, data_check_string, hash_val, bot_token):
            pass  # OK below
        else:
            # При одном сервисе токен должен совпадать; пробуем os.environ на случай разницы Config vs env
            env_token = (os.environ.get("BOT_TOKEN") or "").strip()
            if env_token and env_token != bot_token and _verify_signature(init_data, data_check_string, hash_val, env_token):
                logger.warning(
                    "validate_init_data: подпись сошлась с os.environ BOT_TOKEN, но не с переданным (Config). len(env)=%d, len(передан)=%d",
                    len(env_token),
                    len(bot_token),
                )
                bot_token = env_token
            else:
                # Вычисляем хеш для лога (с переданным токеном)
                secret_key = hmac.new(
                    b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
                ).digest()
                calculated = hmac.new(
                    secret_key, data_check_string.encode("utf-8"), hashlib.sha256
                ).hexdigest()
                logger.warning(
                    "validate_init_data: неверная подпись. hash из initData: %s..., вычисленный: %s... (BOT_TOKEN len=%d)",
                    (hash_val or "")[:12],
                    calculated[:12],
                    len(bot_token),
                )
                return None

        # Проверяем auth_date — initData старше суток может быть перехвачен
        # НЕ используем unquote() перед parse_qs: parse_qs сам декодирует значения,
        # двойное декодирование ломает парсинг поля user (JSON с %xx внутри).
        parsed = parse_qs(init_data, keep_blank_values=True)
        auth_date_raw = parsed.get("auth_date")
        if auth_date_raw:
            try:
                auth_ts = int(auth_date_raw[0] if isinstance(auth_date_raw, list) else auth_date_raw)
                age = time.time() - auth_ts
                if age > _MAX_AUTH_AGE_SECONDS:
                    logger.warning(
                        "validate_init_data: initData устарела — auth_date=%s, возраст=%.0f сек (макс %d)",
                        auth_ts, age, _MAX_AUTH_AGE_SECONDS,
                    )
                    return None
            except (ValueError, TypeError):
                pass

        # Парсим для извлечения user
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
