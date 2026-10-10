from datetime import datetime, timezone
import os
import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from starlette.requests import Request

from auth import create_access_token, credential_fingerprint, decode_access_token, get_password_hash, verify_password
from config import Settings, settings
from models import StudentUser
from test_mess import mess_client
import rate_limit


@pytest.fixture(autouse=True)
def disable_admission_for_auth_tests(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)


@pytest.fixture
def production_configuration():
    # Constructor values take precedence over CI's demo-enabled test environment.
    # Each test receives a fresh mapping; no process environment is modified.
    return {"ENVIRONMENT": "production", "DATABASE_URL": "postgresql+asyncpg://test@localhost/test",
            "SECRET_KEY": "only-for-configuration-unit-tests-" + "x" * 32,
            "ENABLE_DEMO_DATA": False, "AUTO_CREATE_SCHEMA": False,
            "PAYMENT_PROVIDER": "disabled", "PASSCODE_RECOVERY_ENABLED": False,
            "SESSION_COOKIE_MODE_ENABLED": True, "STAGING_QA_WALLET_ENABLED": False,
            "DEPLOYMENT_TIER": "production", "PUBLIC_API_ORIGIN": "https://api.example.invalid",
            "CORS_ORIGINS": ["https://student.example.invalid", "https://admin.example.invalid"],
            "STUDENT_CORS_ORIGINS": ["https://student.example.invalid"],
            "ADMIN_CORS_ORIGINS": ["https://admin.example.invalid"],
            "TRUSTED_HOSTS": ["student.example.invalid", "admin.example.invalid"]}


async def make_student(sessions):
    async with sessions() as session:
        row = StudentUser(id="auth-hardening-student", roll_number="AUTH1042", name="Auth Test",
                          branch="Testing", email="auth-test@example.invalid", phone="",
                          hashed_passcode=get_password_hash("765432"), wallet_balance=0,
                          upi_id="", dietary_preference="all", favorites=[], total_orders=0,
                          total_spent=0, saved_minutes=0, is_active=True)
        session.add(row)
        await session.commit()


@pytest.mark.parametrize("wrong", ["000000", "123456", "999999"])
async def test_no_universal_student_passcode(mess_client, wrong):
    client, sessions, _ = mess_client
    await make_student(sessions)
    response = await client.post("/api/auth/login", json={"rollNumber": "AUTH1042", "passcode": wrong})
    assert response.status_code == 401
    assert "default" not in response.text.lower()


async def test_signup_has_zero_balance_and_no_welcome_money(mess_client):
    client, _, _ = mess_client
    response = await client.post("/api/auth/register", json={"name": "New Student", "rollNumber": "AUTH2000", "passcode": "765432", "branch": "Testing"})
    assert response.status_code == 201
    assert response.json()["user"]["walletBalance"] == 0
    assert response.json()["token"]


async def test_recovery_is_disabled_without_account_enumeration(mess_client):
    client, _, _ = mess_client
    for roll in ("MISSING999", "AUTH1042"):
        response = await client.post("/api/auth/forgot-passcode", json={"rollNumber": roll})
        assert response.status_code == 503
        assert "otp" not in response.json()
    response = await client.post("/api/auth/reset-passcode", json={"rollNumber": "MISSING999", "otp": "123456", "newPasscode": "765432"})
    assert response.status_code == 503
    assert (await client.get("/api/auth/demo-users")).status_code == 404


async def test_cookie_session_and_csrf_origin(mess_client):
    client, sessions, _ = mess_client
    await make_student(sessions)
    payload = {"rollNumber": "AUTH1042", "passcode": "765432"}
    denied = await client.post("/api/auth/login", json=payload, headers={"X-Session-Mode": "cookie"})
    assert denied.status_code == 403
    response = await client.post("/api/auth/login", json=payload, headers={"X-Session-Mode": "cookie", "Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.json()["token"] is None
    cookie = response.headers["set-cookie"].lower()
    assert "canteen_student=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    client.headers.pop("Authorization", None)
    assert (await client.get("/api/auth/me", headers={"Origin": "http://localhost:5173"})).status_code == 200
    assert (await client.put("/api/student/profile", json={"phone": "9800000000"})).status_code == 403
    valid = await client.put("/api/student/profile", json={"phone": "9800000000"}, headers={"Origin": "http://localhost:5173"})
    assert valid.status_code == 200
    assert (await client.get("/api/admin/me")).status_code == 401
    assert (await client.post("/api/auth/logout", headers={"Origin": "http://localhost:5173"})).status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_password_change_invalidates_previously_issued_session(mess_client):
    client, sessions, _ = mess_client
    await make_student(sessions)
    login = await client.post("/api/auth/login", json={"rollNumber": "AUTH1042", "passcode": "765432"})
    token = login.json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    assert (await client.get("/api/auth/me")).status_code == 200
    async with sessions() as session:
        student = (await session.execute(select(StudentUser).where(StudentUser.id == "auth-hardening-student"))).scalar_one()
        student.hashed_passcode = get_password_hash("654321")
        await session.commit()
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.parametrize("missing", ["sub", "role", "exp", "iat"])
def test_jwt_requires_standard_session_claims(missing):
    claims = {"sub": "student", "role": "student", "exp": int(datetime.now(timezone.utc).timestamp()) + 60, "iat": int(datetime.now(timezone.utc).timestamp())}
    del claims[missing]
    with pytest.raises(HTTPException) as error:
        decode_access_token(jwt.encode(claims, settings.SECRET_KEY, algorithm="HS256"))
    assert error.value.status_code == 401


def test_bcrypt_never_truncates_long_credentials():
    hashed = get_password_hash("correct-value")
    assert verify_password("correct-value", hashed)
    assert not verify_password("x" * 73, hashed)
    with pytest.raises(ValueError):
        get_password_hash("x" * 73)


@pytest.mark.parametrize("overrides", [
    {"SECRET_KEY": "weak"}, {"CORS_ORIGINS": ["*"]}, {"TRUSTED_HOSTS": ["*"]},
    {"AUTO_CREATE_SCHEMA": True}, {"PAYMENT_PROVIDER": "razorpay"},
])
def test_production_rejects_unsafe_configuration(overrides, production_configuration):
    values = production_configuration
    assert Settings(_env_file=None, **values).ENVIRONMENT == "production"
    values.update(overrides)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


async def test_distributed_rate_limit_and_production_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    request = Request({"type": "http", "method": "POST", "path": "/api/auth/login",
                       "headers": [], "client": ("127.0.0.1", 123)})
    class Redis:
        counts = {}
        async def eval(self, script, count, key, seconds):
            assert "AUTH1042" not in key
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]
    redis = Redis()
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    await rate_limit.enforce_rate_limit(request, "login", "AUTH1042", limit=2)
    await rate_limit.enforce_rate_limit(request, "login", "AUTH1042", limit=2)
    with pytest.raises(HTTPException) as error:
        await rate_limit.enforce_rate_limit(request, "login", "AUTH1042", limit=2)
    assert error.value.status_code == 429
    async def fail(*args): raise RuntimeError("internal connection detail")
    monkeypatch.setattr(redis, "eval", fail)
    with pytest.raises(HTTPException) as error:
        await rate_limit.enforce_rate_limit(request, "login", "OTHER", limit=2)
    assert error.value.status_code == 503
    assert "internal" not in error.value.detail


async def test_cookie_origins_separate_admin_and_student_applications(mess_client):
    client, sessions, _ = mess_client
    await make_student(sessions)
    student_payload = {"rollNumber": "AUTH1042", "passcode": "765432"}
    admin_payload = {"username": "test-admin", "password": "test-password"}
    student_origin = "http://localhost:5173"
    admin_origin = "http://localhost:8443"
    assert (await client.post("/api/auth/login", json=student_payload,
        headers={"X-Session-Mode": "cookie", "Origin": admin_origin})).status_code == 403
    assert (await client.post("/api/auth/login", json=student_payload,
        headers={"X-Session-Mode": "cookie", "Origin": student_origin})).status_code == 200
    assert (await client.post("/api/admin/login", json=admin_payload,
        headers={"X-Session-Mode": "cookie", "Origin": student_origin})).status_code == 403
    assert (await client.post("/api/admin/login", json=admin_payload,
        headers={"X-Session-Mode": "cookie", "Origin": admin_origin})).status_code == 200
    client.headers.pop("Authorization", None)
    assert (await client.get("/api/admin/me", headers={"Origin": student_origin})).status_code == 403
    assert (await client.get("/api/auth/me", headers={"Origin": admin_origin})).status_code == 403
    assert (await client.get("/api/admin/me", headers={"Origin": admin_origin})).status_code == 200
    assert (await client.get("/api/auth/me", headers={"Origin": student_origin})).status_code == 200
    assert (await client.get("/api/admin/me", headers={"Referer": admin_origin + "/members"})).status_code == 200
    assert (await client.get("/api/auth/me", headers={"Referer": student_origin + "/orders"})).status_code == 200
    assert (await client.get("/api/admin/me", headers={"Referer": student_origin + "/orders"})).status_code == 403
    assert (await client.get("/api/admin/me")).status_code == 403
    assert (await client.get("/api/admin/me", headers={"Origin": "null"})).status_code == 403
    assert (await client.get("/api/admin/me", headers={"Origin": "http://localhost:8443/path"})).status_code == 403
    assert (await client.post("/api/admin/logout", headers={"Origin": student_origin})).status_code == 403
    assert (await client.post("/api/auth/logout", headers={"Origin": admin_origin})).status_code == 403
    assert (await client.post("/api/admin/logout", headers={"Origin": admin_origin})).status_code == 200
    assert (await client.get("/api/admin/me", headers={"Origin": admin_origin})).status_code == 401


@pytest.mark.parametrize("changes", [
    {"ADMIN_CORS_ORIGINS": []},
    {"ADMIN_CORS_ORIGINS": ["https://student.example.invalid"]},
    {"ADMIN_CORS_ORIGINS": ["https://other.example.invalid"]},
    {"STUDENT_CORS_ORIGINS": ["http://student.example.invalid"]},
])
def test_production_rejects_unsafe_cookie_role_origins(changes, production_configuration):
    values = production_configuration
    assert Settings(_env_file=None, **values).ENVIRONMENT == "production"
    values.update(changes)
    with pytest.raises(ValidationError, match="cookie sessions|cookie origins|Role origins"):
        Settings(_env_file=None, **values)


def test_production_demo_override_is_isolated_and_guard_remains(monkeypatch, production_configuration):
    original_environment = os.environ.get("ENABLE_DEMO_DATA")
    original_setting = settings.ENABLE_DEMO_DATA
    with monkeypatch.context() as environment:
        environment.setenv("ENABLE_DEMO_DATA", "true")
        assert Settings(_env_file=None, **production_configuration).ENABLE_DEMO_DATA is False
        with pytest.raises(ValidationError, match="Production cannot enable demo data"):
            Settings(_env_file=None, **{**production_configuration, "ENABLE_DEMO_DATA": True})
        assert os.environ["ENABLE_DEMO_DATA"] == "true"
    assert os.environ.get("ENABLE_DEMO_DATA") == original_environment
    assert settings.ENABLE_DEMO_DATA == original_setting
