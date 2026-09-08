import base64
import io

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
    resp = await client.post("/api/v1/auth/register", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _tiny_png_data_url() -> str:
    """A minimal valid 1x1 transparent PNG, base64-encoded as a data URL —
    the same shape the frontend's signature pad canvas.toDataURL() produces."""
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


@pytest.mark.asyncio
async def test_leave_signature_capture_round_trip_and_pdf(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]
    await client.patch(f"/api/v1/users/{director_id}/status", json={"status": "active"}, headers=_auth(admin_token))

    tl = await _register(client, token=admin_token, username="tl1", email="tl1@example.com", role="team_leader", position="Team Leader", director_id=director_id)
    tl_token = tl["access_token"]

    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl["user"]["id"])
    emp_token = emp["access_token"]

    sig = _tiny_png_data_url()
    create = await client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type": "annual", "days": 5, "start_date": "2026-09-01",
            "reason": "Personal", "prepared_signature": sig,
        },
        headers=_auth(emp_token),
    )
    assert create.status_code == 201, create.text
    leave_id = create.json()["id"]
    assert create.json()["prepared_signature"] == sig

    approve = await client.post(f"/api/v1/leave-requests/{leave_id}/approve", headers=_auth(tl_token))
    assert approve.status_code == 200

    # PDF must generate cleanly with a real captured signature image embedded
    download = await client.get(f"/api/v1/leave-requests/{leave_id}/download", headers=_auth(emp_token))
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert len(download.content) > 2000


@pytest.mark.asyncio
async def test_plan_signature_capture_round_trip_and_pdf(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]
    await client.patch(f"/api/v1/users/{director_id}/status", json={"status": "active"}, headers=_auth(admin_token))

    tl = await _register(client, token=admin_token, username="tl1", email="tl1@example.com", role="team_leader", position="Team Leader", director_id=director_id)
    tl_token = tl["access_token"]

    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl["user"]["id"])
    emp_token = emp["access_token"]

    sig = _tiny_png_data_url()
    create = await client.post(
        "/api/v1/performance-plans",
        json={
            "period": "1_year", "title": "Annual Plan",
            "goals": [{"text": "Improve turnaround time"}],
            "prepared_signature": sig,
        },
        headers=_auth(emp_token),
    )
    assert create.status_code == 201, create.text
    plan_id = create.json()["id"]
    assert create.json()["prepared_signature"] == sig

    approve = await client.post(f"/api/v1/performance-plans/{plan_id}/approve", headers=_auth(tl_token))
    assert approve.status_code == 200

    download = await client.get(f"/api/v1/performance-plans/{plan_id}/download", headers=_auth(emp_token))
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert len(download.content) > 2000
