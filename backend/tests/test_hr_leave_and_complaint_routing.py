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


@pytest.mark.asyncio
async def test_plan_period_only_accepts_six_months_or_one_year(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]

    tl = await _register(
        client, token=admin_token, username="tl1", email="tl1@example.com", role="team_leader", position="TL",
        director_id=director_id,
    )
    emp = await _register(
        client, username="emp1", email="emp1@example.com", role="employee", position="Officer",
        team_leader_id=tl["user"]["id"],
    )
    emp_token = emp["access_token"]

    rejected = await client.post(
        "/api/v1/performance-plans",
        json={"period": "3_months", "title": "X", "goals": [{"text": "g"}]},
        headers=_auth(emp_token),
    )
    assert rejected.status_code == 422

    ok = await client.post(
        "/api/v1/performance-plans",
        json={"period": "1_year", "title": "Annual Plan", "goals": [{"text": "g"}]},
        headers=_auth(emp_token),
    )
    assert ok.status_code == 201, ok.text


@pytest.mark.asyncio
async def test_non_employee_leave_request_routes_to_hr(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]
    director_token = director["access_token"]

    tl = await _register(
        client, token=admin_token, username="teamlead1", email="teamlead1@example.com", role="team_leader",
        position="Team Leader", director_id=director_id,
    )
    tl_token = tl["access_token"]

    hr = await _register(client, username="hr1", email="hr1@example.com", role="human_resource", position="HR Officer")
    hr_token = hr["access_token"]

    # Team Leader requests their own leave -> should go straight to HR, not to a "team leader" queue
    create = await client.post(
        "/api/v1/leave-requests",
        json={"leave_type": "annual", "days": 10, "start_date": "2026-09-01", "reason": "Personal matters"},
        headers=_auth(tl_token),
    )
    assert create.status_code == 201, create.text
    leave_id = create.json()["id"]
    assert create.json()["status"] == "pending_hr"

    # Director cannot decide this (it's pending HR, and a Team Leader's own
    # leave isn't a normal employee-under-them escalation, so this is
    # correctly rejected as outside the Director's coverage)
    forbidden = await client.post(f"/api/v1/leave-requests/{leave_id}/director-approve", headers=_auth(director_token))
    assert forbidden.status_code == 403

    # HR approves it
    approve = await client.post(f"/api/v1/leave-requests/{leave_id}/hr-approve", headers=_auth(hr_token))
    assert approve.status_code == 200
    assert approve.json()["status"] == "hr_approved"

    # HR can download the approved leave PDF
    download = await client.get(f"/api/v1/leave-requests/{leave_id}/download", headers=_auth(hr_token))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_hr_own_leave_request_requires_super_admin(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    hr = await _register(client, username="hr1", email="hr1@example.com", role="human_resource", position="HR Officer")
    hr_token = hr["access_token"]

    # A second HR account
    hr2 = await _register(client, username="hr2", email="hr2@example.com", role="human_resource", position="HR Officer")
    hr2_token = hr2["access_token"]

    create = await client.post(
        "/api/v1/leave-requests",
        json={"leave_type": "annual", "days": 5, "start_date": "2026-09-01", "reason": "Rest"},
        headers=_auth(hr_token),
    )
    assert create.status_code == 201
    leave_id = create.json()["id"]

    # Another HR member cannot approve an HR member's own leave
    other_hr_attempt = await client.post(f"/api/v1/leave-requests/{leave_id}/hr-approve", headers=_auth(hr2_token))
    assert other_hr_attempt.status_code == 403

    # Super Admin can
    admin_decides = await client.post(f"/api/v1/leave-requests/{leave_id}/hr-approve", headers=_auth(admin_token))
    assert admin_decides.status_code == 200


@pytest.mark.asyncio
async def test_any_role_can_submit_complaint_and_hr_can_answer(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    hr = await _register(client, username="hr1", email="hr1@example.com", role="human_resource", position="HR Officer")
    hr_token = hr["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]

    tl = await _register(client, token=admin_token, username="tl1", email="tl1@example.com", role="team_leader", position="TL", director_id=director_id)
    tl_token = tl["access_token"]

    complaint = await client.post(
        "/api/v1/complaints",
        json={"category": "Suggestion", "subject": "Better coffee", "message": "Please upgrade the office coffee machine."},
        headers=_auth(tl_token),
    )
    assert complaint.status_code == 201, complaint.text
    assert complaint.json()["current_handler_role"] == "human_resource"
    complaint_id = complaint.json()["id"]

    respond = await client.post(
        f"/api/v1/complaints/{complaint_id}/respond",
        json={"message": "Noted, ordering a new machine.", "resolve": True},
        headers=_auth(hr_token),
    )
    assert respond.status_code == 200
    assert respond.json()["status"] == "resolved"
