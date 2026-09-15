# SDP Internal Performance & Workflow Management System

A working full-stack app: **FastAPI (async SQLAlchemy 2.x) + PostgreSQL/Supabase** backend,
and a single-page **HTML/JS** frontend. Login/Register is the first screen; after
authenticating you land on a role-specific dashboard.

Every backend module below is real, tested code (13 automated tests pass, including
full end-to-end registration → activation → login and the performance-plan / leave /
complaint approval chains) — not placeholders.

## What's included

**Auth**: register (role-specific fields — Employees pick their Team Leader, Team
Leaders pick their Director), login, JWT access + rotating refresh tokens, logout /
logout-all, forgot/reset password, change password, login history.

**RBAC**: Employee, Team Leader, Director, Technical Committee, Super Admin — enforced
in the API layer (every list/detail endpoint scopes results to what that role is
allowed to see).

**Modules**: Performance Plans (1/3/6/9-month & yearly, submit → Team Leader
approve/reject/escalate → Director decide, Technical Committee comments, edit &
resubmit after rejection, DOCX download with a QR verification code), Leave Requests
(5/10/15/20/25 days or a 30-day "one month" break, same approval chain), Complaints
(Team Leader → Director → Super Admin escalation), Notifications, Departments/Teams/
User management, Audit Logs, Dashboard summary, CSV report export.

## What's simplified vs. the full enterprise brief (being upfront about this)

- **PDF/WeasyPrint → DOCX + QR code.** WeasyPrint needs native system libraries that
  aren't guaranteed on every host. `python-docx` + `qrcode` is pure-Python and always
  installable, and DOCX converts to PDF with `soffice --convert-to pdf` if you need PDF.
- **Redis rate limiting → in-process limiter.** Same interface, swap-in-ready; fine for
  a single backend instance, not yet wired to Redis for multi-instance scaling.
- **Frontend is a single HTML/JS file**, not the full React 19 + TypeScript + Vite +
  Tailwind + shadcn/ui stack — it calls the real API and every workflow works, but it's
  hand-rolled rather than componentized. Say the word and I'll build the React version.
- **Postgres Row-Level Security** is not written as SQL policies — access control is
  enforced in the FastAPI service layer instead (same effective guarantee, different
  layer). If you need literal Postgres RLS policies for a compliance requirement, ask
  and I'll add them.
- **Alembic** is wired and working, but no migration file is pre-generated (I can't
  reach your real Supabase database from here to autogenerate one safely) — run the
  one command below and it writes itself from the models.
- No Playwright/Vitest E2E suite, GitHub Actions, or dark mode yet.

## 1. Backend setup (Supabase)

1. Create a project at supabase.com, then go to **Project Settings → Database** and
   copy the connection string.
2. `cd backend && cp .env.example .env`, then edit `.env`:
   - `DATABASE_URL` = paste the Supabase string exactly as given (the app auto-converts
     `postgresql://` to the async driver it needs at startup — no manual editing needed)
   - `SECRET_KEY` = generate one: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
3. Install & run:
   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   alembic revision --autogenerate -m "initial schema"
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
4. API docs: http://localhost:8000/api/docs
   (The app also auto-creates tables on startup for convenience — Alembic is the
   source of truth once you have a migration history.)

## 2. Frontend setup

The frontend is one static file — no build step.

```bash
cd frontend
python3 -m http.server 8080
```
Open http://localhost:8080. It talks to `http://localhost:8000/api/v1` by default
(see the `API_BASE` constant at the top of `index.html` if you deploy the backend
elsewhere).

## 3. Or run everything with Docker Compose (local Postgres, not Supabase)

```bash
docker compose up --build
```
Backend on :8000, frontend on :8080, local Postgres + Redis included. Useful for
trying the whole thing without a Supabase account; point `DATABASE_URL` back at
Supabase for the deployed version.

## 4. First login

Register the **first account as Super Admin**. Every role now auto-activates on
registration and can log in immediately — Employees and Team Leaders still need
to pick their Team Leader / Director at registration (required, not optional).

### Optional: seed a starting org hierarchy

If the Team Leader / Director dropdowns are empty because you haven't registered
any yet, run the seed script to create a starting set (2 Directors, 2 Team
Leaders, correctly linked):

```bash
cd backend
python3 -m scripts.seed_org
```

Safe to re-run — it skips any account that already exists. Prints the accounts
created and a shared temporary password; change it after first login.

## 5. Tests

```bash
cd backend && source .venv/bin/activate
pip install pytest pytest-asyncio
pytest -v
```
13 tests cover registration/activation/login, token refresh & rotation, the full
performance-plan and leave escalation chains, complaint escalation to Super Admin,
and role-scoped dashboard counts — all passing against an in-memory SQLite DB (the
same models run unchanged against Postgres/Supabase).

## Project layout

```
backend/
  app/
    core/       config, database, security (JWT/bcrypt), RBAC deps, rate limiter
    models/     SQLAlchemy models (portable UUID/JSON so tests use SQLite, prod uses Postgres)
    schemas/    Pydantic v2 request/response models
    services/   business logic (workflow state machines, RBAC scoping, DOCX generation)
    api/v1/     FastAPI routers
  alembic/      migration environment
  tests/        pytest suite (real HTTP requests via httpx against the ASGI app)
frontend/
  index.html    login/register + role dashboards, calls the API directly
docker-compose.yml
```
