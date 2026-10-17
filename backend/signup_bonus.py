"""Opt-in testing credit for new accounts in the positively verified staging DB."""
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import StudentUser, WalletTransaction

AMOUNT = Decimal("200.00")
STAGING_API_ORIGIN = "https://canteen-staging-api.onrender.com"
# Public identities verified read-only against the staging runtime connection.
STAGING_DATABASE_HOST = "ep-late-base-b32xj4ll.c-4.ap-southeast-1.aws.neon.tech"
STAGING_DATABASE_NAME = "canteen_staging"
STAGING_DATABASE_USER = "canteen_staging_runtime"


async def _verified_testing_database(db: AsyncSession) -> bool:
    if (not settings.TEST_SIGNUP_WALLET_CREDIT_ENABLED
            or settings.ENVIRONMENT not in {"staging", "test"}
            or settings.DEPLOYMENT_TIER != "staging"
            or settings.PUBLIC_API_ORIGIN != STAGING_API_ORIGIN
            or settings.PAYMENT_PROVIDER != "disabled"):
        return False
    bound = db.get_bind().url
    configured = make_url(settings.DATABASE_URL)
    if settings.ENVIRONMENT == "test":
        # Local tests must also use an isolated database, never a deployed DB.
        if bound.get_backend_name() == "sqlite":
            return bound.database == ":memory:"
        if bound.get_backend_name() != "postgresql" or bound.host not in {"127.0.0.1", "localhost"}:
            return False
        schema = (await db.execute(text("SELECT current_schema()"))).scalar_one()
        return schema.startswith("mess_test_")
    expected = (STAGING_DATABASE_HOST, STAGING_DATABASE_NAME, STAGING_DATABASE_USER)
    if (bound.get_backend_name() != "postgresql" or configured.get_backend_name() != "postgresql"
            or (bound.host, bound.database, bound.username) != expected
            or (configured.host, configured.database, configured.username) != expected):
        return False
    actual = (await db.execute(text("SELECT current_database(), current_user"))).one()
    return tuple(actual) == (STAGING_DATABASE_NAME, STAGING_DATABASE_USER)


async def initialize_testing_signup_credit(db: AsyncSession, student: StudentUser) -> bool:
    """Join registration's transaction; never commit or credit an existing row.

    The unique roll/email insert precedes the credit. Concurrent registration
    cannot create two accounts. Failure rolls account, balance and ledger back.
    """
    if not inspect(student).pending or Decimal(str(student.wallet_balance or 0)) != 0:
        return False
    if not await _verified_testing_database(db):
        return False
    await db.flush()
    student.wallet_balance = AMOUNT
    db.add(WalletTransaction(
        student_id=student.id, amount=AMOUNT, transaction_type="credit",
        payment_method="Bonus", description="Testing-phase signup bonus (staging only)",
        reference_id="testing-signup:" + student.id, status="success",
    ))
    await db.flush()
    return True
