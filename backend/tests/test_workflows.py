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


async def _build_org(client):
    """Creates: super admin (active), director (activated by admin),
    team leader (reports to director), employee (reports to team leader).
    Returns dict of tokens/ids."""
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]
    await client.patch(f"/api/v1/users/{director_id}/status", json={"status": "active"}, headers=_auth(admin_token))
    director_login = await client.post("/api/v1/auth/login", json={"email": "director1@example.com", "password": "StrongPass1"})
    director_token = director_login.json()["access_token"]

    tl = await _register(
        client, token=admin_token, username="teamlead1", email="teamlead1@example.com", role="team_leader",
        position="Team Leader", director_id=director_id,
    )
    tl_token = tl["access_token"]
    tl_id = tl["user"]["id"]

    emp = await _register(
        client, username="employee1", email="employee1@example.com", role="employee",
        position="Officer", team_leader_id=tl_id,
    )
    emp_token = emp["access_token"]

    return {
        "admin_token": admin_token,
        "director_token": director_token,
        "director_id": director_id,
        "tl_token": tl_token,
        "tl_id": tl_id,
        "emp_token": emp_token,
        "emp_id": emp["user"]["id"],
    }


@pytest.mark.asyncio
async def test_performance_plan_team_leader_approve(client):
    org = await _build_org(client)

    create = await client.post(
        "/api/v1/performance-plans",
        json={
            "period": "6_months",
            "title": "Q1 Goals",
            "goals": [{"text": "Process 100 land title applications"}],
        },
        headers=_auth(org["emp_token"]),
    )
    assert create.status_code == 201, create.text
    plan_id = create.json()["id"]
    assert create.json()["status"] == "submitted"

    # Employee cannot approve their own plan
    forbidden = await client.post(f"/api/v1/performance-plans/{plan_id}/approve", headers=_auth(org["emp_token"]))
    assert forbidden.status_code == 403

    approve = await client.post(f"/api/v1/performance-plans/{plan_id}/approve", headers=_auth(org["tl_token"]))
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Download generates a real PDF file
    download = await client.get(f"/api/v1/performance-plans/{plan_id}/download", headers=_auth(org["emp_token"]))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")
    assert len(download.content) > 1000


@pytest.mark.asyncio
async def test_performance_plan_escalation_to_director(client):
    org = await _build_org(client)

    create = await client.post(
        "/api/v1/performance-plans",
        json={"period": "1_year", "title": "Annual Plan", "goals": [{"text": "Digitize archive"}]},
        headers=_auth(org["emp_token"]),
    )
    plan_id = create.json()["id"]

    escalate = await client.post(
        f"/api/v1/performance-plans/{plan_id}/escalate",
        json={"reason": "Needs director sign-off due to budget impact"},
        headers=_auth(org["tl_token"]),
    )
    assert escalate.status_code == 200
    assert escalate.json()["status"] == "escalated"

    # Team leader cannot decide it again while escalated
    late_approve = await client.post(f"/api/v1/performance-plans/{plan_id}/approve", headers=_auth(org["tl_token"]))
    assert late_approve.status_code == 400

    director_decision = await client.post(
        f"/api/v1/performance-plans/{plan_id}/director-approve", headers=_auth(org["director_token"])
    )
    assert director_decision.status_code == 200
    assert director_decision.json()["status"] == "director_approved"


@pytest.mark.asyncio
async def test_leave_request_rejects_invalid_days(client):
    org = await _build_org(client)
    resp = await client.post(
        "/api/v1/leave-requests",
        json={"leave_type": "annual", "days": 7, "start_date": "2026-08-01", "reason": "Family event"},
        headers=_auth(org["emp_token"]),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_leave_request_one_month_break_full_flow(client):
    org = await _build_org(client)

    create = await client.post(
        "/api/v1/leave-requests",
        json={"leave_type": "annual", "days": 30, "start_date": "2026-08-01", "reason": "One month leave break"},
        headers=_auth(org["emp_token"]),
    )
    assert create.status_code == 201, create.text
    leave_id = create.json()["id"]
    assert create.json()["end_date"] == "2026-08-30"

    reject = await client.post(
        f"/api/v1/leave-requests/{leave_id}/reject",
        json={"reason": "Insufficient staffing coverage in August"},
        headers=_auth(org["tl_token"]),
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_complaint_full_escalation_chain(client):
    org = await _build_org(client)

    create = await client.post(
        "/api/v1/complaints",
        json={"category": "workplace", "subject": "Unsafe equipment", "message": "The scanner in room 3 sparks."},
        headers=_auth(org["emp_token"]),
    )
    assert create.status_code == 201
    complaint_id = create.json()["id"]
    assert create.json()["current_handler_role"] == "team_leader"

    escalate1 = await client.post(
        f"/api/v1/complaints/{complaint_id}/escalate", json={"message": "Needs facilities budget approval"},
        headers=_auth(org["tl_token"]),
    )
    assert escalate1.status_code == 200
    assert escalate1.json()["current_handler_role"] == "director"

    escalate2 = await client.post(
        f"/api/v1/complaints/{complaint_id}/escalate", json={"message": "Escalating to admin for procurement"},
        headers=_auth(org["director_token"]),
    )
    assert escalate2.status_code == 200
    assert escalate2.json()["current_handler_role"] == "super_admin"

    resolve = await client.post(
        f"/api/v1/complaints/{complaint_id}/respond",
        json={"message": "New scanner ordered and installed", "resolve": True},
        headers=_auth(org["admin_token"]),
    )
    assert resolve.status_code == 200
    assert resolve.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_dashboard_summary_scoped_per_role(client):
    org = await _build_org(client)
    await client.post(
        "/api/v1/performance-plans",
        json={"period": "6_months", "title": "H1 Plan", "goals": [{"text": "goal"}]},
        headers=_auth(org["emp_token"]),
    )

    tl_summary = await client.get("/api/v1/dashboard/summary", headers=_auth(org["tl_token"]))
    assert tl_summary.status_code == 200
    assert tl_summary.json()["pending_action_plans"] == 1

    admin_summary = await client.get("/api/v1/dashboard/summary", headers=_auth(org["admin_token"]))
    assert admin_summary.status_code == 200
    assert "total_users" in admin_summary.json()
