"""One-time staging signup credits; isolated databases and no real payments."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from auth import clear_session, issue_session
from config import Settings, settings
from image_fixtures import attach_test_image
from models import FoodItem, StudentUser, WalletTransaction
from signup_bonus import (AMOUNT, STAGING_API_ORIGIN, STAGING_DATABASE_HOST,
                          STAGING_DATABASE_NAME, STAGING_DATABASE_USER,
                          _verified_testing_database, initialize_testing_signup_credit)
from test_deployment_config import configuration
from test_mess import mess_client


@pytest.fixture
def testing_signup(mess_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "DEPLOYMENT_TIER", "staging")
    monkeypatch.setattr(settings, "PUBLIC_API_ORIGIN", STAGING_API_ORIGIN)
    monkeypatch.setattr(settings, "TEST_SIGNUP_WALLET_CREDIT_ENABLED", True)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "disabled")
    monkeypatch.setattr(settings, "PACKAGING_FEE_PAISE", 0)
    monkeypatch.setattr(settings, "ORDER_GST_BASIS_POINTS", 0)
    return mess_client


def registration(**changes):
    return {"name": "Isolated Signup Test", "rollNumber": "SIGNUP2000", "passcode": "765432", **changes}


async def ledger(sessions, student_id):
    async with sessions() as db:
        student = await db.get(StudentUser, student_id)
        rows = (await db.execute(select(WalletTransaction).where(
            WalletTransaction.student_id == student_id).order_by(WalletTransaction.id))).scalars().all()
        return student.wallet_balance, rows


async def test_new_signup_has_exactly_one_auditable_testing_credit(testing_signup):
    client, sessions, _ = testing_signup
    # Client fields neither choose the amount nor activate the server feature.
    response = await client.post("/api/auth/register", json=registration(walletBalance=99999, bonusAmount=99999))
    assert response.status_code == 201, response.text
    assert response.json()["user"]["walletBalance"] == 200
    student_id = response.json()["user"]["id"]
    balance, rows = await ledger(sessions, student_id)
    assert balance == AMOUNT and len(rows) == 1
    assert rows[0].amount == AMOUNT and rows[0].transaction_type == "credit"
    assert rows[0].reference_id == "testing-signup:" + student_id
    assert rows[0].payment_method == "Bonus" and "testing-phase" in rows[0].description.lower()


async def test_retries_login_refresh_never_credit_again(testing_signup):
    client, sessions, _ = testing_signup
    first = await client.post("/api/auth/register", json=registration())
    student_id = first.json()["user"]["id"]
    for _ in range(2):
        assert (await client.post("/api/auth/register", json=registration(rollNumber=" signup2000 "))).status_code == 409
        login = await client.post("/api/auth/login", json={"rollNumber": "SIGNUP2000", "passcode": "765432"})
        assert login.status_code == 200
        me = await client.get("/api/auth/me", headers={"Authorization": "Bearer " + login.json()["token"]})
        assert Decimal(str(me.json()["user"]["walletBalance"])) == AMOUNT
    balance, rows = await ledger(sessions, student_id)
    assert balance == AMOUNT and len(rows) == 1


async def test_existing_zero_balance_account_is_never_retroactively_credited(testing_signup, monkeypatch):
    client, sessions, _ = testing_signup
    monkeypatch.setattr(settings, "TEST_SIGNUP_WALLET_CREDIT_ENABLED", False)
    first = await client.post("/api/auth/register", json=registration())
    student_id = first.json()["user"]["id"]
    monkeypatch.setattr(settings, "TEST_SIGNUP_WALLET_CREDIT_ENABLED", True)
    assert (await client.post("/api/auth/login", json={"rollNumber": "SIGNUP2000", "passcode": "765432"})).json()["user"]["walletBalance"] == 0
    async with sessions() as db:
        assert not await initialize_testing_signup_credit(db, await db.get(StudentUser, student_id))
        await db.commit()
    balance, rows = await ledger(sessions, student_id)
    assert balance == 0 and not rows


@pytest.mark.parametrize("changes", [
    {"TEST_SIGNUP_WALLET_CREDIT_ENABLED": False}, {"ENVIRONMENT": "production"},
    {"ENVIRONMENT": "development"}, {"DEPLOYMENT_TIER": "production"},
    {"DEPLOYMENT_TIER": "development"}, {"PUBLIC_API_ORIGIN": "https://other.invalid"},
    {"PUBLIC_API_ORIGIN": ""}, {"PAYMENT_PROVIDER": "razorpay"},
    # A staging label cannot authorize the fixture's unrelated DB target.
    {"ENVIRONMENT": "staging"},
])
async def test_credit_fails_closed_for_ambiguous_or_production_identity(testing_signup, monkeypatch, changes):
    client, sessions, _ = testing_signup
    for key, value in changes.items():
        monkeypatch.setattr(settings, key, value)
    response = await client.post("/api/auth/register", json=registration())
    assert response.status_code == 201, response.text
    balance, rows = await ledger(sessions, response.json()["user"]["id"])
    assert balance == 0 and not rows


async def test_invalid_registration_leaves_no_partial_account_or_ledger(testing_signup):
    client, sessions, _ = testing_signup
    assert (await client.post("/api/auth/register", json=registration(passcode="1"))).status_code == 422
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(StudentUser).where(StudentUser.roll_number == "SIGNUP2000"))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0


async def test_credit_failure_rolls_back_new_account_and_ledger(testing_signup, monkeypatch):
    client, sessions, _ = testing_signup
    original = AsyncSession.flush
    async def fail_credit_flush(db, *args, **kwargs):
        if any(isinstance(row, WalletTransaction) for row in db.new):
            await original(db, *args, **kwargs)
            raise RuntimeError("isolated simulated credit persistence failure")
        await original(db, *args, **kwargs)
    monkeypatch.setattr(AsyncSession, "flush", fail_credit_flush)
    with pytest.raises(RuntimeError, match="isolated simulated"):
        await client.post("/api/auth/register", json=registration())
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(StudentUser).where(StudentUser.roll_number == "SIGNUP2000"))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0


async def test_signup_order_200_to_180_idempotent_debit_and_refund(testing_signup):
    client, sessions, _ = testing_signup
    response = await client.post("/api/auth/register", json=registration())
    student_id = response.json()["user"]["id"]
    headers = {"Authorization": "Bearer " + response.json()["token"], "Idempotency-Key": "signup-twenty-rupee-test"}
    async with sessions() as db:
        item = FoodItem(id="signup-test-food", name="Isolated Twenty Rupee Food", price=20,
                        category="Snacks", is_available=True, timing_window="all_day")
        db.add(item)
        await attach_test_image(db, item)
        await db.commit()
    body = {"items": [{"id": "signup-test-food", "qty": 1}], "paymentMethod": "wallet"}
    first = await client.post("/api/student/orders", headers=headers, json=body)
    assert first.status_code == 201, first.text
    repeated = await client.post("/api/student/orders", headers=headers, json=body)
    assert repeated.status_code == 201 and repeated.json()["orderId"] == first.json()["orderId"]
    balance, rows = await ledger(sessions, student_id)
    assert balance == Decimal("180.00")
    debits = [row for row in rows if row.transaction_type == "debit"]
    assert len(debits) == 1 and debits[0].amount == Decimal("20.00")
    for _ in range(2):
        assert (await client.post(f'/api/student/orders/{first.json()["orderId"]}/cancel', headers=headers)).status_code == 200
    balance, rows = await ledger(sessions, student_id)
    assert balance == AMOUNT and len(rows) == 3
    assert len([row for row in rows if row.reference_id == "testing-signup:" + student_id]) == 1


async def test_concurrent_registration_cannot_duplicate_signup_credit(testing_signup):
    client, sessions, postgres = testing_signup
    if not postgres:
        pytest.skip("Concurrent unique-index verification requires isolated PostgreSQL")
    responses = await asyncio.gather(*(client.post("/api/auth/register", json=registration()) for _ in range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    created = next(response for response in responses if response.status_code == 201)
    balance, rows = await ledger(sessions, created.json()["user"]["id"])
    assert balance == AMOUNT and len(rows) == 1


def test_bonus_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TEST_SIGNUP_WALLET_CREDIT_ENABLED", raising=False)
    assert Settings(_env_file=None, ENVIRONMENT="test", DATABASE_URL="sqlite+aiosqlite:///:memory:",
                    SECRET_KEY="isolated-configuration-test").TEST_SIGNUP_WALLET_CREDIT_ENABLED is False


@pytest.mark.parametrize("unsafe", [{"ENABLE_DEMO_DATA": True}, {"AUTO_CREATE_SCHEMA": True},
    {"SECRET_KEY": "weak"}, {"CORS_ORIGINS": ["*"]}, {"PUBLIC_API_ORIGIN": "http://api.invalid"},
    {"ADMIN_CORS_ORIGINS": ["https://student.canteen.test"]}])
def test_staging_preserves_production_security_guards(unsafe):
    assert configuration(ENVIRONMENT="staging").ENVIRONMENT == "staging"
    with pytest.raises(ValidationError):
        configuration(ENVIRONMENT="staging", **unsafe)


@pytest.mark.parametrize("changed,field,value,allowed,queries", [
    (None, None, None, True, 1),
    ("actual", "database", "unrelated", False, 1),
    ("actual", "user", "unrelated_owner", False, 1),
    ("configured", "host", "unrelated.invalid", False, 0),
    ("configured", "database", "unrelated", False, 0),
    ("configured", "username", "unrelated_owner", False, 0),
    ("bound", "host", "unrelated.invalid", False, 0),
    ("bound", "database", "unrelated", False, 0),
    ("bound", "username", "unrelated_owner", False, 0),
    ("environment", None, "production", False, 0),
])
async def test_signup_credit_verifies_configured_bound_and_actual_staging_identity(
        monkeypatch, changed, field, value, allowed, queries):
    # No engine or network connection: public target identity is checked against
    # independently controlled configured, bound and actual-database responses.
    expected = make_url(f"postgresql+asyncpg://{STAGING_DATABASE_USER}@{STAGING_DATABASE_HOST}/{STAGING_DATABASE_NAME}")
    configured = bound = expected
    actual = [STAGING_DATABASE_NAME, STAGING_DATABASE_USER]
    if changed == "configured":
        configured = configured.set(**{field: value})
    elif changed == "bound":
        bound = bound.set(**{field: value})
    elif changed == "actual":
        actual[0 if field == "database" else 1] = value
    for name, setting in {
        "ENVIRONMENT": value if changed == "environment" else "staging",
        "DEPLOYMENT_TIER": "staging", "PUBLIC_API_ORIGIN": STAGING_API_ORIGIN,
        "PAYMENT_PROVIDER": "disabled", "TEST_SIGNUP_WALLET_CREDIT_ENABLED": True,
        "DATABASE_URL": str(configured),
    }.items():
        monkeypatch.setattr(settings, name, setting)
    statements = []

    async def execute(statement):
        statements.append(str(statement))
        return SimpleNamespace(one=lambda: tuple(actual))

    session = SimpleNamespace(get_bind=lambda: SimpleNamespace(url=bound), execute=execute)
    assert await _verified_testing_database(session) is allowed
    assert len(statements) == queries
    assert all(statement == "SELECT current_database(), current_user" for statement in statements)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_hosted_session_cookies_and_logout_remain_secure(monkeypatch, environment):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "SESSION_COOKIE_MODE_ENABLED", True)
    monkeypatch.setattr(settings, "STUDENT_CORS_ORIGINS", ["https://student.canteen.test"])
    request = Request({"type": "http", "method": "POST", "path": "/api/auth/login",
                       "headers": [(b"x-session-mode", b"cookie"),
                                   (b"origin", b"https://student.canteen.test")]})
    response = Response()
    assert issue_session(response, request, "synthetic-test-token", "student")
    assert "secure" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()
    logout = Response()
    clear_session(logout, "student")
    assert "secure" in logout.headers["set-cookie"].lower()


@pytest.mark.parametrize("environment", ["staging", "production"])
async def test_hosted_rate_limiting_fails_closed_without_redis(monkeypatch, environment):
    import rate_limit
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)

    async def unavailable(*args):
        raise RuntimeError("synthetic internal connection details")

    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: SimpleNamespace(eval=unavailable))
    request = Request({"type": "http", "method": "POST", "path": "/api/auth/register",
                       "headers": [], "client": ("127.0.0.1", 123)})
    with pytest.raises(HTTPException) as error:
        await rate_limit.enforce_rate_limit(request, "register", limit=5, window=300)
    assert error.value.status_code == 503
    assert "internal" not in error.value.detail


@pytest.mark.parametrize("environment", ["staging", "production"])
async def test_hosted_schema_creation_and_demo_seeding_are_blocked(monkeypatch, environment):
    from database import init_db
    from seed_data import seed
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    # Even accidental flags cannot authorize destructive initialization paths.
    monkeypatch.setattr(settings, "AUTO_CREATE_SCHEMA", True)
    monkeypatch.setattr(settings, "ENABLE_DEMO_DATA", True)
    with pytest.raises(RuntimeError, match="reviewed Alembic migrations"):
        await init_db()
    with pytest.raises(RuntimeError, match="Demo seeding is disabled"):
        await seed()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_hosted_public_image_delivery_rejects_http(monkeypatch, environment):
    from image_service import image_url
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "PUBLIC_API_ORIGIN", "http://api.canteen.test")
    with pytest.raises(HTTPException) as error:
        image_url("a" * 32)
    assert error.value.status_code == 503
