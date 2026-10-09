from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from config import settings
from database import engine, get_redis_client, init_db
from routes import admin_router, auth_router, menu_router
from student_auth_routes import student_auth_router
from student_routes import student_router
from mess_routes import mess_router
from ocr_router import ocr_router
from payment_routes import payment_router
from admin_operations import admin_operations_router
from observability import RequestLoggingMiddleware, log_event


async def verify_schema_revision() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(Path(__file__).parent / "alembic.ini"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    async with engine.connect() as connection:
        current = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    if current != [expected]:
        raise RuntimeError("Database migration revision is not current")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.startup_ready = False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        if settings.ENVIRONMENT == "production":
            await verify_schema_revision()
        elif settings.AUTO_CREATE_SCHEMA:
            await init_db()
        app.state.startup_ready = True
        log_event("startup_ready", environment=settings.ENVIRONMENT)
    except Exception as error:
        log_event("startup_failed", error_type=type(error).__name__)
        raise RuntimeError("Backend startup failed; verify database and migrations") from None
    try:
        yield
    finally:
        app.state.startup_ready = False
        try:
            await get_redis_client().aclose()
        finally:
            await engine.dispose()
        log_event("shutdown_complete")


app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan,
              docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
              redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
              openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                   allow_credentials=settings.SESSION_COOKIE_MODE_ENABLED,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "X-Session-Mode", "Idempotency-Key"],
                   expose_headers=["X-Request-ID"])
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    request_id = getattr(request.state, "request_id", "")
    log_event("request_failed", request_id=request_id, error_type=type(error).__name__)
    return JSONResponse(status_code=500, content={"detail": "Service temporarily unavailable", "request_id": request_id},
                        headers={"X-Request-ID": request_id, "Cache-Control": "no-store"})


app.include_router(student_auth_router, prefix=settings.API_V1_STR)
app.include_router(mess_router, prefix=settings.API_V1_STR)
app.include_router(student_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(menu_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(ocr_router, prefix=settings.API_V1_STR)
app.include_router(payment_router, prefix=settings.API_V1_STR)
app.include_router(admin_operations_router, prefix=settings.API_V1_STR)


@app.get("/api/health", tags=["System"])
async def health_check():
    return {"status": "alive"}


@app.get("/api/ready", tags=["System"])
async def readiness_check():
    checks = {"database": False, "redis": False}
    async def database_ready():
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    try:
        await asyncio.wait_for(database_ready(), timeout=2)
        checks["database"] = True
    except Exception:
        pass
    try:
        await asyncio.wait_for(get_redis_client().ping(), timeout=2)
        checks["redis"] = True
    except Exception:
        pass
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503, content={"status": "ready" if ready else "unavailable", **checks})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
