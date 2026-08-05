import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from sawtai.auth.service import DEMO_TOKEN, DEMO_USER, get_current_user, require
from sawtai.main import app


@pytest.mark.asyncio
async def test_demo_auth_accepts_missing_and_valid_credentials() -> None:
    assert await get_current_user(None) == DEMO_USER
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=DEMO_TOKEN)
    assert await get_current_user(credentials) == DEMO_USER


@pytest.mark.asyncio
async def test_demo_auth_rejects_unknown_token() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
    with pytest.raises(HTTPException) as error:
        await get_current_user(credentials)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_permission_dependency_enforces_required_permissions() -> None:
    dependency = require("analytics:read")
    assert await dependency(user=DEMO_USER) == DEMO_USER

    forbidden = require("admin:write")
    with pytest.raises(HTTPException) as error:
        await forbidden(user=DEMO_USER)
    assert error.value.status_code == 403


def test_login_and_profile_contract() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/token",
            json={"email": "demo@sawtai.ae", "password": "demo"},
        )
        profile = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert profile.status_code == 200
    assert profile.json()["tenant_id"] == DEMO_USER.tenant_id


def test_login_rejects_invalid_credentials() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/token",
            json={"email": "demo@sawtai.ae", "password": "wrong"},
        )
    assert response.status_code == 401
