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


@pytest.mark.asyncio
async def test_complaint_routed_to_specific_director_blocks_other_directors(client):
    """A complaint addressed to one specific Director must not be visible
    to, or actionable by, a different Director who happens to share the
    same role — the whole point of picking a specific person."""
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    dir1 = await _register(client, token=admin_token, username="dir1", email="dir1@example.com", role="director", position="Director")
    dir1_id, dir1_token = dir1["user"]["id"], dir1["access_token"]

    dir2 = await _register(client, token=admin_token, username="dir2", email="dir2@example.com", role="director", position="Director")
    dir2_token = dir2["access_token"]

    tl = await _register(client, token=admin_token, username="tlfordir1", email="tlfordir1@example.com", role="team_leader", position="TL", director_id=dir1_id)
    tl_id = tl["user"]["id"]

    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl_id)
    emp_token = emp["access_token"]

    r = await client.post(
        "/api/v1/complaints",
        json={"category": "HR", "subject": "Workplace conflict", "message": "Details here.",
              "recipient": "director", "target_user_id": dir1_id},
        headers=_auth(emp_token),
    )
    assert r.status_code == 201, r.text
    complaint = r.json()
    assert complaint["target_label"]  # director's full_name
    cid = complaint["id"]

    # Wrong director: blocked from viewing, from history, and from responding.
    wrong_view = await client.get(f"/api/v1/complaints/{cid}", headers=_auth(dir2_token))
    assert wrong_view.status_code == 403, wrong_view.text
    wrong_history = await client.get(f"/api/v1/complaints/{cid}/history", headers=_auth(dir2_token))
    assert wrong_history.status_code == 403, wrong_history.text
    wrong_respond = await client.post(f"/api/v1/complaints/{cid}/respond", json={"message": "x", "resolve": True}, headers=_auth(dir2_token))
    assert wrong_respond.status_code == 403, wrong_respond.text
    wrong_list = await client.get("/api/v1/complaints", headers=_auth(dir2_token))
    assert not any(c["id"] == cid for c in wrong_list.json())

    # Right director: can view, see history, and resolve it.
    right_view = await client.get(f"/api/v1/complaints/{cid}", headers=_auth(dir1_token))
    assert right_view.status_code == 200
    right_history = await client.get(f"/api/v1/complaints/{cid}/history", headers=_auth(dir1_token))
    assert right_history.status_code == 200
    right_respond = await client.post(f"/api/v1/complaints/{cid}/respond", json={"message": "Resolved.", "resolve": True}, headers=_auth(dir1_token))
    assert right_respond.status_code == 200, right_respond.text
    assert right_respond.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_complaint_direct_get_blocks_unrelated_team_leader(client):
    """GET /complaints/{id} and its /history must enforce the same
    visibility rules as the list endpoint — an unrelated Team Leader (not
    the submitter's own, not the addressed target) must not be able to
    read a complaint just by knowing its id."""
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    dir1 = await _register(client, token=admin_token, username="dir1", email="dir1@example.com", role="director", position="Director")
    dir1_id = dir1["user"]["id"]

    tl_owner = await _register(client, token=admin_token, username="tlowner", email="tlowner@example.com", role="team_leader", position="TL", director_id=dir1_id)
    tl_owner_id = tl_owner["user"]["id"]

    tl_stranger = await _register(client, token=admin_token, username="tlstranger", email="tlstranger@example.com", role="team_leader", position="TL", director_id=dir1_id)
    tl_stranger_token = tl_stranger["access_token"]

    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl_owner_id)
    emp_token = emp["access_token"]

    r = await client.post(
        "/api/v1/complaints",
        json={"category": "General", "subject": "Issue", "message": "Something happened."},
        headers=_auth(emp_token),
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    stranger_view = await client.get(f"/api/v1/complaints/{cid}", headers=_auth(tl_stranger_token))
    assert stranger_view.status_code == 403, stranger_view.text
    stranger_history = await client.get(f"/api/v1/complaints/{cid}/history", headers=_auth(tl_stranger_token))
    assert stranger_history.status_code == 403, stranger_history.text


@pytest.mark.asyncio
async def test_complaint_routed_to_technical_committee_is_actionable(client):
    """Technical Committee must actually be able to see and respond to a
    complaint addressed to them — a routing option that nobody could act on
    would be a dead end."""
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    tc = await _register(client, token=admin_token, username="tc1", email="tc1@example.com", role="technical_committee", position="TC Member")
    tc_token = tc["access_token"]

    dir1 = await _register(client, token=admin_token, username="dirtc", email="dirtc@example.com", role="director", position="Director")
    tl = await _register(client, token=admin_token, username="tltc", email="tltc@example.com", role="team_leader", position="TL", director_id=dir1["user"]["id"])
    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl["user"]["id"])
    emp_token = emp["access_token"]

    r = await client.post(
        "/api/v1/complaints",
        json={"category": "Technical", "subject": "System bug", "message": "Details.", "recipient": "technical_committee"},
        headers=_auth(emp_token),
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    listing = await client.get("/api/v1/complaints", headers=_auth(tc_token))
    assert listing.status_code == 200
    assert any(c["id"] == cid for c in listing.json())

    respond = await client.post(f"/api/v1/complaints/{cid}/respond", json={"message": "Looking into it.", "resolve": False}, headers=_auth(tc_token))
    assert respond.status_code == 200, respond.text
    assert respond.json()["status"] == "in_review"
