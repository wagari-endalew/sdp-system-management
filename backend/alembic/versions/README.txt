Run this once you have a real DATABASE_URL configured (Supabase or any Postgres):

    cd backend
    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head

That will generate the first migration file in this folder from the models
in app/models/. The app also auto-creates tables on startup for local/dev
convenience (see app/main.py -> init_models()), but Alembic migrations are
the source of truth for production schema changes.
