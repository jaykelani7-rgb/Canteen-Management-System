"""Single-use recovery serialized on the student row in the existing database."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from auth import credential_fingerprint, get_password_hash, normalize_roll_number
from config import settings
from mail_delivery import recovery_delivery_configured, send_recovery_code, valid_contact_email
from models import StudentUser
from observability import log_event
from recovery_models import RecoveryChallenge

GENERIC_REQUEST_MESSAGE = "If an eligible account exists, a recovery code will be sent to its registered email."
INVALID_CODE_MESSAGE = "Invalid or expired recovery code. Request a new code and try again"
_ACTIVE = {"DeliveryPending", "Pending"}


def utc_now():
    return datetime.now(timezone.utc)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _digest(purpose: str, value: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), ("canteen-recovery:" + purpose + ":" + value).encode(), hashlib.sha256).hexdigest()


def _contact_fingerprint(student: StudentUser) -> str:
    return _digest("contact", student.id + ":" + student.email.strip())


def _code_hash(challenge_id: str, code: str) -> str:
    return _digest("code", challenge_id + ":" + code)


def require_recovery_delivery() -> None:
    if not recovery_delivery_configured():
        raise HTTPException(503, "Passcode recovery is not configured. Contact canteen administration")


def _matches_student(challenge, student) -> bool:
    return (student.is_active and valid_contact_email(student.email)
            and hmac.compare_digest(challenge.contact_fingerprint, _contact_fingerprint(student))
            and hmac.compare_digest(challenge.credential_fingerprint, credential_fingerprint(student.hashed_passcode)))


async def _deliver(sessions, challenge_id: str, recipient: str, code: str) -> None:
    # Plaintext exists only in this short-lived in-memory task and the email.
    # There is no debug transport, persisted plaintext, or automatic fake delivery.
    try:
        async with sessions() as db:
            challenge = await db.get(RecoveryChallenge, challenge_id)
            student = await db.get(StudentUser, challenge.student_id) if challenge else None
            if (not challenge or challenge.status != "DeliveryPending" or not student
                    or not _matches_student(challenge, student) or _aware(challenge.expires_at) <= utc_now()):
                return
        delivered = True
        try:
            await send_recovery_code(recipient, code, settings.RECOVERY_CODE_TTL_SECONDS)
        except Exception:
            delivered = False
            log_event("recovery_delivery_failed")
        async with sessions() as db:
            # All challenge state changes use the same lock order as reset.
            student = (await db.execute(select(StudentUser).where(StudentUser.id == student.id).with_for_update())).scalar_one_or_none()
            challenge = (await db.execute(select(RecoveryChallenge).where(RecoveryChallenge.id == challenge_id).with_for_update())).scalar_one_or_none()
            if challenge and challenge.status == "DeliveryPending":
                now = utc_now()
                if not student or not _matches_student(challenge, student):
                    challenge.status, challenge.finalized_at = "Superseded", now
                elif _aware(challenge.expires_at) <= now:
                    challenge.status, challenge.finalized_at = "Expired", now
                elif delivered:
                    challenge.status, challenge.delivered_at = "Pending", now
                else:
                    challenge.status, challenge.finalized_at = "DeliveryFailed", now
                await db.commit()
    except Exception:
        # A process/database failure leaves a non-usable DeliveryPending challenge
        # that expires and can be superseded by another request; no code is logged.
        log_event("recovery_delivery_unavailable")


async def request_recovery(db: AsyncSession, roll: str, background: BackgroundTasks) -> None:
    require_recovery_delivery()
    roll = normalize_roll_number(roll)
    student = (await db.execute(select(StudentUser).where(StudentUser.roll_number == roll).with_for_update())).scalar_one_or_none()
    if not student or not student.is_active or not valid_contact_email(student.email):
        await db.commit()
        return
    now = utc_now()
    active = (await db.execute(select(RecoveryChallenge).where(
        RecoveryChallenge.student_id == student.id, RecoveryChallenge.status.in_(_ACTIVE)
    ).with_for_update())).scalars().all()
    if any((now - _aware(row.created_at)).total_seconds() < settings.RECOVERY_RESEND_COOLDOWN_SECONDS
           and _aware(row.expires_at) > now for row in active):
        await db.commit()
        return
    for row in active:
        row.status = "Expired" if _aware(row.expires_at) <= now else "Superseded"
        row.finalized_at = now
    await db.flush()
    challenge_id = secrets.token_hex(16)
    code = str(secrets.randbelow(1_000_000)).zfill(6)
    row = RecoveryChallenge(id=challenge_id, student_id=student.id,
        code_hash=_code_hash(challenge_id, code), contact_fingerprint=_contact_fingerprint(student),
        credential_fingerprint=credential_fingerprint(student.hashed_passcode),
        status="DeliveryPending", attempts=0, max_attempts=settings.RECOVERY_MAX_ATTEMPTS,
        created_at=now, expires_at=now + timedelta(seconds=settings.RECOVERY_CODE_TTL_SECONDS))
    recipient = student.email
    db.add(row)
    await db.commit()
    # Sending occurs after the generic response, avoiding SMTP-latency account
    # enumeration. A restart can lose delivery; callers safely request another code.
    background.add_task(_deliver, async_sessionmaker(db.bind, expire_on_commit=False), challenge_id, recipient, code)


async def reset_passcode(db: AsyncSession, roll: str, code: str, new_passcode: str) -> bool:
    require_recovery_delivery()
    try:
        new_hash = await asyncio.to_thread(get_password_hash, new_passcode)
    except ValueError:
        raise HTTPException(422, "Passcode length is unsupported")
    student = (await db.execute(select(StudentUser).where(
        StudentUser.roll_number == normalize_roll_number(roll)
    ).with_for_update())).scalar_one_or_none()
    if not student:
        await db.commit()
        return False
    challenge = (await db.execute(select(RecoveryChallenge).where(
        RecoveryChallenge.student_id == student.id
    ).order_by(RecoveryChallenge.created_at.desc(), RecoveryChallenge.id.desc()).limit(1).with_for_update())).scalar_one_or_none()
    now = utc_now()
    if not challenge or challenge.status != "Pending":
        await db.commit()
        return False
    if _aware(challenge.expires_at) <= now:
        challenge.status, challenge.finalized_at = "Expired", now
        await db.commit()
        return False
    if not _matches_student(challenge, student):
        challenge.status, challenge.finalized_at = "Superseded", now
        await db.commit()
        return False
    if challenge.attempts >= challenge.max_attempts:
        challenge.status, challenge.finalized_at = "Locked", now
        await db.commit()
        return False
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _code_hash(challenge.id, code)):
        if challenge.attempts >= challenge.max_attempts:
            challenge.status, challenge.finalized_at = "Locked", now
        await db.commit()
        return False
    student.hashed_passcode = new_hash
    challenge.status, challenge.finalized_at = "Consumed", now
    # Updating the bcrypt hash invalidates every prior credential-bound JWT.
    await db.commit()
    return True
