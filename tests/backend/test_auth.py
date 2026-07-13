import pytest
import httpx
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch

from backend.auth import verify_supabase_user


@pytest.mark.asyncio
async def test_verify_supabase_user_accepts_existing_user(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = AsyncMock()
    client.get.return_value = httpx.Response(200, json={"id": "user-1"})
    client.__aenter__.return_value = client

    with patch("backend.auth.httpx.AsyncClient", return_value=client) as client_factory:
        await verify_supabase_user("token", "user-1")

    client_factory.assert_called_once_with(timeout=5.0)
    client.get.assert_awaited_once_with(
        "https://example.supabase.co/auth/v1/user",
        headers={"apikey": "anon-key", "Authorization": "Bearer token"},
    )


@pytest.mark.asyncio
async def test_verify_supabase_user_rejects_deleted_user():
    client = AsyncMock()
    client.get.return_value = httpx.Response(401, json={"message": "User not found"})
    client.__aenter__.return_value = client

    with patch.dict(
        "os.environ",
        {
            "NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        },
    ), patch("backend.auth.httpx.AsyncClient", return_value=client):
        with pytest.raises(HTTPException) as error:
            await verify_supabase_user("token", "deleted-user")

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_supabase_user_returns_service_unavailable_on_network_error(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("connection failed")
    client.__aenter__.return_value = client

    with patch("backend.auth.httpx.AsyncClient", return_value=client):
        with pytest.raises(HTTPException) as error:
            await verify_supabase_user("token", "user-1")

    assert error.value.status_code == 503
