"""Тесты admin API endpoints (FastAPI TestClient)."""
import hashlib
import hmac
import json
import time
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

# Мокаем Config до импорта admin_webapp
_TEST_TOKEN = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ"


def _build_init_data(bot_token: str, user_id: int = 100) -> str:
    """Собирает валидный initData."""
    auth_date = str(int(time.time()) - 10)
    user_json = json.dumps({"id": user_id, "first_name": "Admin"})
    pairs = {"auth_date": auth_date, "user": user_json}
    sorted_pairs = sorted(pairs.items())
    dcs = "\n".join(f"{k}={v}" for k, v in sorted_pairs)
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    from urllib.parse import quote
    raw = "&".join(f"{k}={quote(v)}" for k, v in pairs.items())
    return f"{raw}&hash={h}"


@pytest.fixture
def valid_headers():
    return {"X-Telegram-Init-Data": _build_init_data(_TEST_TOKEN, user_id=100)}


@pytest.mark.asyncio
async def test_health():
    """Health endpoint доступен без авторизации."""
    with patch("admin_webapp.main.async_session_maker") as mock_sm:
        # Mock DB session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 1))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sm.return_value = mock_ctx

        from admin_webapp.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_api_me_no_auth():
    """api/me без initData → 401."""
    from admin_webapp.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/me")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_me_invalid_token():
    """api/me с невалидным initData → 401."""
    from admin_webapp.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/me", headers={"X-Telegram-Init-Data": "garbage"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_me_non_admin():
    """api/me с валидным initData, но не админ → 403."""
    init_data = _build_init_data(_TEST_TOKEN, user_id=999)
    with patch("admin_webapp.main.Config") as mock_config:
        mock_config.BOT_TOKEN = _TEST_TOKEN
        mock_config.ADMIN_IDS = [100]  # 999 не в списке
        from admin_webapp.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/me", headers={"X-Telegram-Init-Data": init_data})
            assert resp.status_code == 403


@pytest.mark.asyncio
async def test_security_headers():
    """Проверяем наличие security headers."""
    with patch("admin_webapp.main.async_session_maker") as mock_sm:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 1))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sm.return_value = mock_ctx

        from admin_webapp.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.headers.get("x-content-type-options") == "nosniff"
            assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
            assert resp.headers.get("x-xss-protection") == "1; mode=block"
            assert "strict-origin" in resp.headers.get("referrer-policy", "")
