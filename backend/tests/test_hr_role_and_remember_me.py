import pytest
from jose import jwt

from app.core.config import settings


async def _register(client, token=None, **overrides):
    payload = {
        "full_name": "Test User",
        "username": "testuser1",
        "email": "test1@example.com",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
        "role": "employee",
        "position": "Officer",
    }
    payload.update(overrides)
    headers = {"Authorization": f"Bearer {token}"} if token else None
    resp = await client.post("/api/v1/auth/register", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_human_resource_role_auto_activates_and_sees_everything(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    hr = await _register(client, username="hr1", email="hr1@example.com", role="human_resource", position="HR Officer")
    assert hr["access_token"], "HR auto-activates and logs in immediately, no admin approval gate"
    assert hr["user"]["status"] == "active"
    hr_token = hr["access_token"]

    # HR can see the full user list (unrestricted visibility, like Director/Super Admin)
    users_resp = await client.get("/api/v1/users", headers=_auth(hr_token))
    assert users_resp.status_code == 200
    assert len(users_resp.json()) >= 2  # admin + hr at minimum

    # HR can see complaints list (empty is fine — the point is it's not 403)
    complaints_resp = await client.get("/api/v1/complaints", headers=_auth(hr_token))
    assert complaints_resp.status_code == 200


@pytest.mark.asyncio
async def test_remember_me_extends_refresh_token_lifetime(client):
    reg = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    assert reg["access_token"]

    # Login without remember_me -> short-lived refresh token
    short_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin1@example.com", "password": "StrongPass1", "remember_me": False},
    )
    assert short_login.status_code == 200
    short_refresh = short_login.json()["refresh_token"]
    short_payload = jwt.decode(short_refresh, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    # Login with remember_me -> long-lived refresh token
    long_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin1@example.com", "password": "StrongPass1", "remember_me": True},
    )
    assert long_login.status_code == 200
    long_refresh = long_login.json()["refresh_token"]
    long_payload = jwt.decode(long_refresh, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    # The remembered token must expire meaningfully later than the non-remembered one
    assert long_payload["exp"] > short_payload["exp"]
    expected_extra_seconds = (
        settings.REMEMBER_ME_REFRESH_TOKEN_EXPIRE_DAYS - settings.REFRESH_TOKEN_EXPIRE_DAYS
    ) * 86400
    actual_extra_seconds = long_payload["exp"] - short_payload["exp"]
    # allow a couple seconds of test-execution drift
    assert abs(actual_extra_seconds - expected_extra_seconds) < 5
