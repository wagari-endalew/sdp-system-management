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
async def test_leave_extra_fields_round_trip_and_pdf(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]
    director_token = director["access_token"]

    tl = await _register(client, token=admin_token, username="tl1", email="tl1@example.com", role="team_leader", position="Team Leader", director_id=director_id)
    tl_token = tl["access_token"]

    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl["user"]["id"])
    emp_token = emp["access_token"]

    extra = {
        "fullName": "Emp One", "empId": "EMP-001", "department": "Land Registration",
        "jobTitle": "Registration Officer", "phone": "+251911000000",
        "contactAddress": "Bole, Addis Ababa", "delegateName": "Colleague X",
        "delegateSign": "Colleague X", "leaveBalance": 18, "hrOfficer": "HR Person",
        "reqName": "Emp One", "reqDate": "2026-08-01", "appName": "", "appDate": "",
    }
    create = await client.post(
        "/api/v1/leave-requests",
        json={
            "leave_type": "annual", "days": 10, "start_date": "2026-09-01",
            "reason": "Family event", "extra_fields": extra,
        },
        headers=_auth(emp_token),
    )
    assert create.status_code == 201, create.text
    leave_id = create.json()["id"]
    assert create.json()["extra_fields"]["department"] == "Land Registration"

    # Fetch it back — extra_fields must survive a round trip
    fetched = await client.get(f"/api/v1/leave-requests/{leave_id}", headers=_auth(tl_token))
    assert fetched.status_code == 200
    assert fetched.json()["extra_fields"]["hrOfficer"] == "HR Person"

    approve = await client.post(f"/api/v1/leave-requests/{leave_id}/approve", headers=_auth(tl_token))
    assert approve.status_code == 200

    download = await client.get(f"/api/v1/leave-requests/{leave_id}/download", headers=_auth(emp_token))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")
    # With extra_fields present the PDF should be the 3-page version (bigger
    # than the plain 2-page one) -- a rough proxy is just that it's non-trivial size
    assert len(download.content) > 2000


@pytest.mark.asyncio
async def test_plan_extra_fields_with_scoring_table_round_trip_and_pdf(client):
    admin = await _register(client, username="admin1", email="admin1@example.com", role="super_admin", position="Admin")
    admin_token = admin["access_token"]

    director = await _register(client, token=admin_token, username="director1", email="director1@example.com", role="director", position="Director")
    director_id = director["user"]["id"]

    tl = await _register(client, token=admin_token, username="tl1", email="tl1@example.com", role="team_leader", position="Team Leader", director_id=director_id)
    tl_token = tl["access_token"]

    emp = await _register(client, username="emp1", email="emp1@example.com", role="employee", position="Officer", team_leader_id=tl["user"]["id"])
    emp_token = emp["access_token"]

    extra = {
        "empName": "Emp One", "empId": "EMP-001", "jobTitle": "Registration Officer",
        "grade": "IV", "directorate": "Kadaster", "supervisorName": "TL One",
        "budgetYear": "2018", "evalType": "6ወር",
        "sixMonthScores": [
            {"objective": "Register 200 land holdings", "weight": 30, "done": "Registered 210", "score": 28},
            {"objective": "Deploy new kadaster system", "weight": 25, "done": "Deployed on schedule", "score": 25},
        ],
        "totalScore": 53,
        "strengths": "Strong technical skills", "weaknesses": "Needs faster turnaround",
        "prep_name": "Emp One", "app_name": "",
    }
    create = await client.post(
        "/api/v1/performance-plans",
        json={
            "period": "6_months", "title": "H1 FY2018 Plan",
            "goals": [{"text": "Register 200 land holdings", "weight": 30, "score": 28}],
            "extra_fields": extra,
        },
        headers=_auth(emp_token),
    )
    assert create.status_code == 201, create.text
    plan_id = create.json()["id"]
    assert create.json()["extra_fields"]["totalScore"] == 53

    approve = await client.post(f"/api/v1/performance-plans/{plan_id}/approve", headers=_auth(tl_token))
    assert approve.status_code == 200

    download = await client.get(f"/api/v1/performance-plans/{plan_id}/download", headers=_auth(emp_token))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")
    assert len(download.content) > 2000
