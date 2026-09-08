import pytest


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
    return await client.post("/api/v1/auth/register", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_bootstrap_super_admin_auto_activates(client):
    resp = await _register(
        client,
        username="admin1",
        email="admin1@example.com",
        role="super_admin",
        position="System Administrator",
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"], "first super admin should auto-login"
    assert body["user"]["status"] == "active"


@pytest.mark.asyncio
async def test_second_super_admin_also_auto_activates(client):
    # Registration no longer requires Super Admin approval for any role —
    # every account is active immediately, including a second Super Admin.
    await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    resp = await _register(client, username="admin2", email="admin2@example.com", role="super_admin", position="Admin")
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"], "every role auto-activates and logs in immediately"
    assert body["user"]["status"] == "active"


@pytest.mark.asyncio
async def test_employee_registration_requires_team_leader(client):
    resp = await _register(client)
    assert resp.status_code == 422
    assert "Team Leader" in resp.text


@pytest.mark.asyncio
async def test_password_mismatch_rejected(client):
    resp = await _register(client, team_leader_id=None, confirm_password="Different1")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_full_org_registration_chain_and_login(client):
    # 1. Bootstrap super admin
    admin_resp = await _register(
        client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin"
    )
    assert admin_resp.status_code == 201
    admin_token = admin_resp.json()["access_token"]

    # 2. Director created by the Super Admin — Director/Team Leader creation
    # is a Super Admin-only action, not open self-registration (see
    # api/v1/auth.py:register). Still returns real tokens for the new
    # account; it just requires an authenticated Super Admin caller.
    director_resp = await _register(
        client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director"
    )
    assert director_resp.status_code == 201
    director_id = director_resp.json()["user"]["id"]
    assert director_resp.json()["user"]["status"] == "active"
    assert director_resp.json()["access_token"], "directors log in immediately, no admin activation needed"

    # 3. Team leader also created by the Super Admin, selecting the director
    tl_resp = await _register(
        client,
        token=admin_token,
        username="teamlead1",
        email="teamlead1@example.com",
        role="team_leader",
        position="Team Leader",
        director_id=director_id,
    )
    assert tl_resp.status_code == 201, tl_resp.text
    tl_id = tl_resp.json()["user"]["id"]
    assert tl_resp.json()["access_token"], "team leaders are active immediately"

    # 4. Employee registers, selecting the team leader
    emp_resp = await _register(
        client,
        username="employee1",
        email="employee1@example.com",
        role="employee",
        position="Officer",
        team_leader_id=tl_id,
    )
    assert emp_resp.status_code == 201, emp_resp.text
    emp_token = emp_resp.json()["access_token"]

    # 5. Employee can fetch /me
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {emp_token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "employee1"

    # 6. Invalid team_leader_id is rejected
    bad = await _register(
        client,
        username="employee2",
        email="employee2@example.com",
        role="employee",
        position="Officer",
        team_leader_id=director_id,  # director is not a team leader
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_login_wrong_password_fails(client):
    await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    resp = await client.post("/api/v1/auth/login", json={"email": "admin1@example.com", "password": "WrongPass1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_and_logout_flow(client):
    reg = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    tokens = reg.json()

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["access_token"] != tokens["access_token"]

    # Old refresh token should now be revoked (rotation)
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401

    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
    assert logout.status_code == 200
