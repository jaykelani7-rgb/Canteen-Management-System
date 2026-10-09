"""No test sends an actual email or changes existing application data."""
import asyncio
from datetime import timedelta
import ssl
import pytest
from sqlalchemy import select
from auth import verify_password
from config import Settings, settings
from models import StudentUser
from recovery_models import RecoveryChallenge
from test_mess import mess_client
from test_auth_hardening import make_student
import mail_delivery
import rate_limit
import recovery_service


@pytest.fixture(autouse=True)
def configured_recovery(monkeypatch):
    monkeypatch.setattr(settings, "PASSCODE_RECOVERY_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "support@example.invalid")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)


@pytest.fixture
def delivery(monkeypatch):
    sent = []
    async def send(recipient, code, ttl):
        sent.append({"recipient": recipient, "code": code, "ttl": ttl})
    monkeypatch.setattr(recovery_service, "send_recovery_code", send)
    return sent


async def request(client, roll="AUTH1042", **extra):
    return await client.post("/api/auth/forgot-passcode", json={"rollNumber": roll, **extra})


async def reset(client, code, roll="AUTH1042", new="654321"):
    return await client.post("/api/auth/reset-passcode", json={"rollNumber": roll, "otp": code, "newPasscode": new})


async def history(sessions):
    async with sessions() as db:
        return (await db.execute(select(RecoveryChallenge).order_by(RecoveryChallenge.created_at))).scalars().all()


async def test_delivery_uses_only_existing_contact_and_generic_response(mess_client, delivery):
    client, sessions, _ = mess_client
    await make_student(sessions)
    known = await request(client, email="attacker@example.invalid")
    unknown = await request(client, "MISSING999")
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"success": True, "message": recovery_service.GENERIC_REQUEST_MESSAGE}
    assert len(delivery) == 1 and delivery[0]["recipient"] == "auth-test@example.invalid"
    assert "otp" not in known.json() and delivery[0]["code"] not in known.text
    rows = await history(sessions)
    assert len(rows) == 1 and rows[0].status == "Pending"
    assert len(rows[0].code_hash) == 64 and rows[0].code_hash != delivery[0]["code"]
    assert len(rows[0].contact_fingerprint) == 64
    assert delivery[0]["ttl"] == settings.RECOVERY_CODE_TTL_SECONDS
    assert rows[0].delivered_at is not None


async def test_reset_is_single_use_and_invalidates_prior_sessions(mess_client, delivery):
    client, sessions, _ = mess_client
    await make_student(sessions)
    login = await client.post("/api/auth/login", json={"rollNumber": "AUTH1042", "passcode": "765432"})
    old_headers = {"Authorization": "Bearer " + login.json()["token"]}
    assert (await client.get("/api/auth/me", headers=old_headers)).status_code == 200
    assert (await request(client)).status_code == 200
    changed = await reset(client, delivery[0]["code"])
    assert changed.status_code == 200
    assert changed.json() == {"success": True, "message": "Passcode updated. Sign in again."}
    assert "token" not in changed.json() and "user" not in changed.json()
    assert (await client.get("/api/auth/me", headers=old_headers)).status_code == 401
    assert (await reset(client, delivery[0]["code"])).status_code == 400
    rows = await history(sessions)
    assert rows[0].status == "Consumed" and rows[0].attempts == 1 and rows[0].finalized_at is not None
    async with sessions() as db:
        student = await db.get(StudentUser, "auth-hardening-student")
        assert verify_password("654321", student.hashed_passcode)
        assert not verify_password("765432", student.hashed_passcode)
    assert (await client.post("/api/auth/login", json={"rollNumber": "AUTH1042", "passcode": "654321"})).status_code == 200


async def test_expired_code_is_rejected_and_preserves_history(mess_client, delivery, monkeypatch):
    client, sessions, _ = mess_client
    await make_student(sessions)
    await request(client)
    now = recovery_service.utc_now()
    monkeypatch.setattr(recovery_service, "utc_now", lambda: now + timedelta(seconds=settings.RECOVERY_CODE_TTL_SECONDS + 1))
    rejected = await reset(client, delivery[0]["code"])
    assert rejected.status_code == 400 and rejected.json()["detail"] == recovery_service.INVALID_CODE_MESSAGE
    assert (await history(sessions))[0].status == "Expired"


async def test_bruteforce_locks_challenge_after_bounded_attempts(mess_client, delivery):
    client, sessions, _ = mess_client
    await make_student(sessions)
    await request(client)
    wrong = "000000" if delivery[0]["code"] != "000000" else "999999"
    for _ in range(settings.RECOVERY_MAX_ATTEMPTS):
        assert (await reset(client, wrong)).status_code == 400
    assert (await reset(client, delivery[0]["code"])).status_code == 400
    rows = await history(sessions)
    assert rows[0].attempts == settings.RECOVERY_MAX_ATTEMPTS and rows[0].status == "Locked"
    async with sessions() as db:
        assert verify_password("765432", (await db.get(StudentUser, "auth-hardening-student")).hashed_passcode)


async def test_resend_supersedes_old_code_and_preserves_both_records(mess_client, delivery, monkeypatch):
    client, sessions, _ = mess_client
    await make_student(sessions)
    numbers = iter([123456, 654321])
    monkeypatch.setattr(recovery_service.secrets, "randbelow", lambda _: next(numbers))
    await request(client)
    # A quick resend is a generic success but cannot spam another email.
    await request(client)
    assert len(delivery) == 1
    now = recovery_service.utc_now()
    monkeypatch.setattr(recovery_service, "utc_now", lambda: now + timedelta(seconds=settings.RECOVERY_RESEND_COOLDOWN_SECONDS + 1))
    await request(client)
    assert len(delivery) == 2
    assert (await reset(client, delivery[0]["code"])).status_code == 400
    assert (await reset(client, delivery[1]["code"])).status_code == 200
    rows = await history(sessions)
    assert [row.status for row in rows] == ["Superseded", "Consumed"]


@pytest.mark.parametrize("change", ["email", "email_case", "hashed_passcode"])
async def test_contact_or_credential_change_invalidates_outstanding_code(mess_client, delivery, change):
    client, sessions, _ = mess_client
    await make_student(sessions)
    await request(client)
    async with sessions() as db:
        student = await db.get(StudentUser, "auth-hardening-student")
        if change == "email": student.email = "changed@example.invalid"
        elif change == "email_case": student.email = student.email.upper()
        else:
            from auth import get_password_hash
            student.hashed_passcode = get_password_hash("112233")
        await db.commit()
    assert (await reset(client, delivery[0]["code"])).status_code == 400
    assert (await history(sessions))[0].status == "Superseded"


async def test_failed_delivery_is_generic_and_never_creates_usable_code(mess_client, monkeypatch, caplog):
    client, sessions, _ = mess_client
    await make_student(sessions)
    codes = []
    async def fail(recipient, code, ttl):
        codes.append(code)
        raise RuntimeError("SMTP provider internal secret")
    monkeypatch.setattr(recovery_service, "send_recovery_code", fail)
    known = await request(client)
    unknown = await request(client, "MISSING999")
    assert known.json() == unknown.json()
    assert codes[0] not in known.text and "SMTP provider internal secret" not in known.text
    assert (await history(sessions))[0].status == "DeliveryFailed"
    assert (await reset(client, codes[0])).status_code == 400
    assert codes[0] not in caplog.text and "SMTP provider internal secret" not in caplog.text


async def test_disabled_recovery_returns503_and_never_attempts_delivery(mess_client, delivery, monkeypatch):
    client, sessions, _ = mess_client
    await make_student(sessions)
    monkeypatch.setattr(settings, "PASSCODE_RECOVERY_ENABLED", False)
    assert (await request(client)).status_code == 503
    assert (await reset(client, "123456")).status_code == 503
    assert not delivery and not await history(sessions)


async def test_recovery_cookie_mode_requires_student_origin(mess_client, delivery):
    client, sessions, _ = mess_client
    await make_student(sessions)
    for origin in (None, "http://localhost:8443"):
        headers = {"X-Session-Mode": "cookie"}
        if origin: headers["Origin"] = origin
        denied = await client.post("/api/auth/forgot-passcode", json={"rollNumber": "AUTH1042"}, headers=headers)
        assert denied.status_code == 403
    assert not delivery
    allowed = await client.post("/api/auth/forgot-passcode", json={"rollNumber": "AUTH1042"},
        headers={"X-Session-Mode": "cookie", "Origin": "http://localhost:5173"})
    assert allowed.status_code == 200 and len(delivery) == 1


async def test_account_and_ip_limits_prevent_recovery_spam(mess_client, delivery, monkeypatch):
    client, sessions, _ = mess_client
    await make_student(sessions)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RECOVERY_REQUEST_LIMIT", 1)
    monkeypatch.setattr(settings, "RECOVERY_RESET_LIMIT", 1)
    class Redis:
        counts = {}
        async def eval(self, script, count, key, seconds):
            assert "AUTH1042" not in key
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]
    redis = Redis()
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    assert (await request(client)).status_code == 200
    assert (await request(client)).status_code == 429
    wrong = "000000" if delivery[0]["code"] != "000000" else "999999"
    assert (await reset(client, wrong)).status_code == 400
    assert (await reset(client, wrong)).status_code == 429
    assert (await history(sessions))[0].attempts == 1
    # Different identities share a separate aggregate source-IP budget.
    for number in range(3):
        assert (await request(client, "UNKNOWN" + str(number))).status_code == 200
    assert (await request(client, "UNKNOWN99")).status_code == 429


@pytest.mark.parametrize("mode", ["starttls", "ssl"])
async def test_smtp_requires_verified_tls_and_never_debug_output(monkeypatch, mode):
    monkeypatch.setattr(settings, "SMTP_SECURITY", mode)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "provider-account")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "test-only-provider-password")
    calls = []
    class SMTP:
        def __init__(self, host, port, timeout, context=None):
            if mode == "ssl":
                assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            calls.append("connect")
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def ehlo(self): calls.append("ehlo")
        def starttls(self, context):
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            calls.append("tls")
        def login(self, user, password):
            assert mode == "ssl" or "tls" in calls
            calls.append("login")
        def send_message(self, message):
            assert message["To"] == "recipient@example.invalid"
            assert "654321" in message.get_content()
            calls.append("send")
    monkeypatch.setattr(mail_delivery.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(mail_delivery.smtplib, "SMTP_SSL", SMTP)
    await mail_delivery.send_recovery_code("recipient@example.invalid", "654321", 300)
    assert calls[-2:] == ["login", "send"]


async def test_concurrent_reset_consumes_code_exactly_once(mess_client, delivery):
    client, sessions, postgres = mess_client
    if not postgres: pytest.skip("Row lock concurrency requires PostgreSQL")
    await make_student(sessions)
    await request(client)
    responses = await asyncio.gather(reset(client, delivery[0]["code"]), reset(client, delivery[0]["code"]))
    assert sorted(response.status_code for response in responses) == [200, 400]
    rows = await history(sessions)
    assert len(rows) == 1 and rows[0].status == "Consumed" and rows[0].attempts == 1


@pytest.mark.parametrize("changes", [
    {"SMTP_HOST": ""}, {"SMTP_FROM_EMAIL": "invalid-address"},
    {"SMTP_USERNAME": "provider", "SMTP_PASSWORD": ""}, {"SMTP_SECURITY": "plaintext"},
])
def test_enabled_recovery_requires_safe_provider_configuration(changes):
    from pydantic import ValidationError
    values = {"DATABASE_URL": "postgresql+asyncpg://test@localhost/test",
              "SECRET_KEY": "only-for-configuration-unit-tests-" + "x" * 32,
              "PASSCODE_RECOVERY_ENABLED": True, "SMTP_HOST": "smtp.example.invalid",
              "SMTP_FROM_EMAIL": "support@example.invalid"}
    assert Settings(_env_file=None, **values).PASSCODE_RECOVERY_ENABLED
    values.update(changes)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
