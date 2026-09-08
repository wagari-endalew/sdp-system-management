import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import init_models
from app.core.rate_limit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("sdp")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "SDP Internal Performance & Workflow Management System API. "
        "Modules: Auth & RBAC, Employees/Departments/Teams, Performance Plans, "
        "Leave Requests, Complaints, Notifications, Audit Logs, Reports."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        errors.append({"field": loc, "message": err.get("msg")})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.on_event("startup")
async def on_startup():
    # Creates tables if they do not already exist. In production, run
    # `alembic upgrade head` instead (see /backend/alembic) and remove this
    # call once your migration history is authoritative.
    await init_models()
    await _seed_starting_org_hierarchy()
    await _add_missing_complaint_columns()
    logger.info("%s started (env=%s)", settings.APP_NAME, settings.ENV)


async def _add_missing_complaint_columns():
    """Adds target_user_id/target_label to an already-existing `complaints`
    table if they're missing. create_all() only creates whole tables that
    don't exist yet — it never alters an existing table's columns — so
    anyone who already had this app running before the complaint-routing
    feature was added would otherwise hit a real 500 on every complaint
    query. Safe to run every boot: it checks first and does nothing if the
    columns are already there."""
    try:
        from sqlalchemy import inspect, text
        from app.core.database import engine

        async with engine.begin() as conn:
            table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
            if "complaints" not in table_names:
                return
            existing_cols = await conn.run_sync(
                lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("complaints")}
            )
            is_sqlite = engine.url.get_backend_name() == "sqlite"
            uuid_type = "CHAR(36)" if is_sqlite else "UUID"
            if "target_user_id" not in existing_cols:
                await conn.execute(text(f"ALTER TABLE complaints ADD COLUMN target_user_id {uuid_type}"))
                logger.info("Added missing column complaints.target_user_id")
            if "target_label" not in existing_cols:
                await conn.execute(text("ALTER TABLE complaints ADD COLUMN target_label VARCHAR(200)"))
                logger.info("Added missing column complaints.target_label")
    except Exception:
        logger.exception("Auto-migrating the complaints table failed (non-fatal, app will still start)")


async def _seed_starting_org_hierarchy():
    """Auto-seeds the starting Directors/Team Leaders on first boot, so the
    registration dropdowns are never empty — this used to require someone to
    remember to run `python3 -m scripts.seed_org` by hand, which was easy to
    miss. Failure here should never take the app down, so it's caught and
    logged rather than raised."""
    try:
        from app.core.database import AsyncSessionLocal
        from scripts.seed_org import seed_org_hierarchy

        async with AsyncSessionLocal() as session:
            await seed_org_hierarchy(session, log=logger.info)
    except Exception:
        logger.exception("Auto-seeding the starting org hierarchy failed (non-fatal, app will still start)")


@app.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.ENV}


app.include_router(api_router, prefix=settings.API_V1_PREFIX)
