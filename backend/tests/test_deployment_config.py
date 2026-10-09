"""Deployment checks use synthetic configuration and isolated ASGI apps; no database I/O."""
import pytest
import ssl
import certifi
from asyncpg.connect_utils import _parse_connect_arguments
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.middleware.cors import CORSMiddleware

from config import Settings
from start_server import bounded_integer


def configuration(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://fixture:fixture@db.canteen.test/canteen?ssl=verify-full",
        "REDIS_URL": "rediss://fixture:fixture@cache.canteen.test:6379/0",
        "SECRET_KEY": "synthetic-deployment-unit-test-only-" + "x" * 32,
        "CORS_ORIGINS": ["https://student.canteen.test", "https://admin.canteen.test", "https://localhost"],
        "STUDENT_CORS_ORIGINS": ["https://student.canteen.test"],
        "ADMIN_CORS_ORIGINS": ["https://admin.canteen.test"],
        "TRUSTED_HOSTS": ["api.canteen.test"],
        "SESSION_COOKIE_MODE_ENABLED": True,
        "AUTO_CREATE_SCHEMA": False,
        "ENABLE_DEMO_DATA": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_free_staging_connection_budget_is_configurable():
    settings = configuration(DATABASE_POOL_SIZE=2, DATABASE_MAX_OVERFLOW=3,
                             SESSION_COOKIE_MODE_ENABLED=False)
    assert settings.DATABASE_POOL_SIZE + settings.DATABASE_MAX_OVERFLOW == 5
    assert not settings.AUTO_CREATE_SCHEMA and not settings.ENABLE_DEMO_DATA


@pytest.mark.parametrize("field,value", [("DATABASE_POOL_SIZE", 0), ("DATABASE_POOL_SIZE", 51),
                                       ("DATABASE_MAX_OVERFLOW", -1), ("DATABASE_MAX_OVERFLOW", 51)])
def test_invalid_pool_budget_is_rejected(field, value):
    with pytest.raises(ValidationError):
        configuration(**{field: value})


async def test_hosted_sqlalchemy_url_passes_verified_ssl_to_asyncpg():
    settings = configuration()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        _, arguments = engine.dialect.create_connect_args(engine.url)
        assert arguments["ssl"] == "verify-full"
        assert "sslmode" not in arguments and "channel_binding" not in arguments
        assert arguments["host"] == "db.canteen.test"
    finally:
        await engine.dispose()


def test_installed_asyncpg_verifies_host_and_certificate_with_explicit_ca(monkeypatch):
    monkeypatch.setenv("PGSSLROOTCERT", certifi.where())
    _, parameters, _ = _parse_connect_arguments(
        dsn=None, host="db.canteen.test", port=5432, user="fixture", password="fixture",
        passfile=None, database="canteen", command_timeout=10, statement_cache_size=0,
        max_cached_statement_lifetime=300, max_cacheable_statement_size=15360,
        ssl="verify-full", direct_tls=False, server_settings=None,
        target_session_attrs=None, krbsrvname=None, gsslib=None, service=None, servicefile=None,
    )
    assert parameters.ssl.verify_mode == ssl.CERT_REQUIRED
    assert parameters.ssl.check_hostname is True


@pytest.mark.parametrize("origin,expected", [("https://localhost", 200),
                                            ("https://student.canteen.test", 200),
                                            ("https://unknown.canteen.test", 400),
                                            ("http://localhost", 400)])
async def test_native_https_origin_is_explicitly_allowed(origin, expected):
    settings = configuration(SESSION_COOKIE_MODE_ENABLED=False)
    assert "https://localhost" not in settings.STUDENT_CORS_ORIGINS
    assert "https://localhost" not in settings.ADMIN_CORS_ORIGINS
    application = FastAPI()
    application.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                               allow_credentials=False, allow_methods=["GET", "POST"],
                               allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
    async with AsyncClient(transport=ASGITransport(app=application), base_url="https://api.canteen.test") as client:
        response = await client.options("/api/student/orders", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        })
    assert response.status_code == expected
    assert "access-control-allow-credentials" not in response.headers
    if expected == 200:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers


def test_entrypoint_uses_hosting_port_and_one_worker(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    assert bounded_integer("PORT", "8000", 1, 65535) == 10000
    assert bounded_integer("WEB_CONCURRENCY", "1", 1, 8) == 1


@pytest.mark.parametrize("value", ["0", "65536", "not-a-number"])
def test_entrypoint_rejects_invalid_hosting_port(monkeypatch, value):
    monkeypatch.setenv("PORT", value)
    with pytest.raises(RuntimeError):
        bounded_integer("PORT", "8000", 1, 65535)
