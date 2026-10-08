"""PostgreSQL-backed mess operations. No balance is accepted from clients."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_admin
from database import AsyncSessionLocal, cache_get, cache_set, cache_invalidate_prefix, get_db
from models import AdminUser, StudentUser, MessPlan, MessSubscription, MessMealAttendance
from schemas import MessSubscriptionInput, MessSubscriptionUpdate, MessMarkInput, MessUndoInput, MessPlanUpdate

IST = timezone(timedelta(hours=5, minutes=30))
Meal = Literal["Breakfast", "Lunch", "Snacks", "Dinner"]
mess_router = APIRouter(prefix="/admin/mess", tags=["Admin Mess Management"])


def mess_today():
    return datetime.now(IST).date()


def effective_status(subscription, day=None):
    if subscription.status == "Cancelled":
        return "Cancelled"
    if subscription.end_date < (day or mess_today()):
        return "Expired"
    if subscription.remaining_tokens == 0:
        return "Exhausted"
    return "Active"


def serialize(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, (datetime, date)):
            # SQLite tests omit timezone; PostgreSQL stores timezone-aware timestamps.
            if isinstance(value, datetime) and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            value = value.isoformat()
        result[column.name] = value
    if isinstance(row, MessSubscription):
        result["status"] = effective_status(row)
        result["tokens_used"] = row.total_tokens - row.remaining_tokens
    return result


async def ensure_mess_plans(db):
    # Startup and seed use a transaction-scoped lock to avoid competing defaults.
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(7263821)"))
    defaults = [("single", "Single Meal", 1800, 28), ("double", "Double Meal", 3600, 55)]
    for plan_id, name, amount, tokens in defaults:
        if not await db.get(MessPlan, plan_id):
            db.add(MessPlan(id=plan_id, name=name, amount=amount, tokens=tokens, duration_days=30))
    await db.flush()


async def initialize_mess_plans():
    async with AsyncSessionLocal() as db:
        await ensure_mess_plans(db)
        await db.commit()


async def lock_roll(db, roll):
    # Prevent overlapping subscriptions even when two staff create the same roll at once.
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:roll))"), {"roll": "mess:" + roll})


async def validate_overlap(db, roll, start, end, exclude_id=None):
    query = select(MessSubscription.id).where(
        MessSubscription.roll_number == roll,
        MessSubscription.status != "Cancelled",
        MessSubscription.start_date <= end,
        MessSubscription.end_date >= start,
    )
    if exclude_id:
        query = query.where(MessSubscription.id != exclude_id)
    if (await db.execute(query.limit(1))).first():
        raise HTTPException(409, "This student already has a subscription covering these dates.")


async def subscription_values(payload, db, existing=None):
    plan = await db.get(MessPlan, payload.plan_type)
    if not plan:
        raise HTTPException(400, "Plan is not configured. Run database initialization.")
    same_plan = existing is not None and payload.plan_type == existing.plan_type
    if not plan.is_active and not same_plan:
        raise HTTPException(409, "This plan is inactive. Select an active plan.")
    values = payload.model_dump(exclude={"status"})
    # Editing contact details must not silently adopt newly edited plan defaults.
    # A deliberate plan change uses that plan's defaults; explicit values remain
    # available to staff for the agreed subscription snapshot.
    values["amount_paid"] = payload.amount_paid if payload.amount_paid is not None else (existing.amount_paid if same_plan else plan.amount)
    values["total_tokens"] = payload.total_tokens if payload.total_tokens is not None else (existing.total_tokens if same_plan else plan.tokens)
    values["end_date"] = payload.end_date or (existing.end_date if same_plan else payload.start_date + timedelta(days=plan.duration_days))
    if values["end_date"] < payload.start_date:
        raise HTTPException(400, "End date must be on or after start date.")
    student = (await db.execute(select(StudentUser).where(StudentUser.roll_number == payload.roll_number))).scalar_one_or_none()
    values["student_id"] = student.id if student else None
    return values


@mess_router.post("/subscriptions", status_code=201)
async def create_subscription(payload: MessSubscriptionInput, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    await lock_roll(db, payload.roll_number)
    values = await subscription_values(payload, db)
    await validate_overlap(db, payload.roll_number, values["start_date"], values["end_date"])
    row = MessSubscription(**values, remaining_tokens=values["total_tokens"], status="Active")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return serialize(row)


def search_query(query, search):
    if search:
        # Literal substring, not client-supplied SQL LIKE wildcards.
        query = query.where(or_(
            MessSubscription.student_name.icontains(search, autoescape=True),
            MessSubscription.roll_number.icontains(search, autoescape=True),
            MessSubscription.mobile_number.icontains(search, autoescape=True),
        ))
    return query


@mess_router.get("/subscriptions")
async def subscriptions(search: str = Query("", max_length=100), plan_type: Optional[Literal["single", "double"]] = None,
                        status: Optional[Literal["Active", "Expired", "Exhausted", "Cancelled"]] = None,
                        db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    query = search_query(select(MessSubscription).order_by(MessSubscription.student_name, MessSubscription.id), search)
    if plan_type:
        query = query.where(MessSubscription.plan_type == plan_type)
    rows = [serialize(s) for s in (await db.execute(query)).scalars()]
    return [r for r in rows if not status or r["status"] == status]


async def history(db, subscription_id):
    rows = (await db.execute(select(MessMealAttendance, AdminUser.username).outerjoin(
        AdminUser, AdminUser.id == MessMealAttendance.marked_by_admin_id
    ).where(MessMealAttendance.subscription_id == subscription_id).order_by(
        MessMealAttendance.meal_date.desc(), MessMealAttendance.id.desc()
    ))).all()
    return [{**serialize(row), "marked_by": username} for row, username in rows]


@mess_router.get("/subscriptions/{subscription_id}")
async def subscription_detail(subscription_id: int, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    row = await db.get(MessSubscription, subscription_id)
    if not row:
        raise HTTPException(404, "Mess subscription not found")
    records = await history(db, row.id)
    return {**serialize(row), "attendance": records, "meals_taken": sum(r["status"] == "Taken" for r in records)}


@mess_router.put("/subscriptions/{subscription_id}")
async def update_subscription(subscription_id: int, payload: MessSubscriptionUpdate, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    await lock_roll(db, payload.roll_number)
    row = (await db.execute(select(MessSubscription).where(MessSubscription.id == subscription_id).with_for_update())).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Mess subscription not found")
    values = await subscription_values(payload, db, row)
    records = await history(db, row.id)
    if records and (values["roll_number"] != row.roll_number or values["student_id"] != row.student_id):
        raise HTTPException(409, "Student identity cannot change after attendance exists.")
    if any(not values["start_date"] <= date.fromisoformat(r["meal_date"]) <= values["end_date"] for r in records):
        raise HTTPException(409, "Subscription dates must preserve all attendance history.")
    used = row.total_tokens - row.remaining_tokens
    if values["total_tokens"] < used:
        raise HTTPException(409, "Total tokens cannot be less than tokens already used.")
    if payload.status != "Cancelled":
        await validate_overlap(db, payload.roll_number, values["start_date"], values["end_date"], row.id)
    for key, value in values.items():
        setattr(row, key, value)
    row.remaining_tokens = values["total_tokens"] - used
    row.status = payload.status
    row.status = effective_status(row)
    await db.commit()
    await db.refresh(row)
    return serialize(row)


async def mark_meal(db, payload, admin_id):
    if payload.meal_date != mess_today():
        raise HTTPException(400, "Only today's meals can be marked. Previous dates are read-only.")
    subscription = (await db.execute(select(MessSubscription).where(
        MessSubscription.id == payload.subscription_id
    ).with_for_update())).scalar_one_or_none()
    if not subscription:
        raise HTTPException(404, "Mess subscription not found")
    existing = (await db.execute(select(MessMealAttendance.id).where(
        MessMealAttendance.subscription_id == subscription.id,
        MessMealAttendance.meal_date == payload.meal_date,
        MessMealAttendance.meal_type == payload.meal_type,
        MessMealAttendance.status == "Taken",
    ))).first()
    if existing:
        raise HTTPException(409, f"{payload.meal_type} already marked for this student today.")
    if effective_status(subscription) != "Active":
        raise HTTPException(409, f"Subscription is {effective_status(subscription)}.")
    if not subscription.start_date <= payload.meal_date <= subscription.end_date:
        raise HTTPException(400, "Date is outside the subscription period.")
    before = subscription.remaining_tokens
    subscription.remaining_tokens -= 1
    subscription.status = effective_status(subscription)
    row = MessMealAttendance(subscription_id=subscription.id, student_id=subscription.student_id,
        meal_date=payload.meal_date, meal_type=payload.meal_type, marked_by_admin_id=admin_id,
        status="Taken", token_before=before, token_after=subscription.remaining_tokens,
        marked_at=datetime.now(timezone.utc))
    db.add(row)
    await db.flush()
    await db.refresh(subscription)
    return row, subscription


@mess_router.post("/attendance/mark", status_code=201)
async def mark_attendance(payload: MessMarkInput, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    try:
        row, subscription = await mark_meal(db, payload, admin.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, f"{payload.meal_type} already marked for this student today.")
    return {"attendance": {**serialize(row), "marked_by": admin.username}, "subscription": serialize(subscription)}


async def undo_meal(db, attendance_id, reason, admin_id):
    original = await db.get(MessMealAttendance, attendance_id)
    if not original:
        raise HTTPException(404, "Attendance not found")
    # Always lock subscription first, matching mark's lock order.
    subscription = (await db.execute(select(MessSubscription).where(
        MessSubscription.id == original.subscription_id
    ).with_for_update())).scalar_one()
    row = (await db.execute(select(MessMealAttendance).where(MessMealAttendance.id == attendance_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if row.meal_date != mess_today():
        raise HTTPException(400, "Only today's attendance can be undone.")
    if row.status != "Taken":
        raise HTTPException(409, "Attendance already reversed.")
    row.status = "Reversed"
    row.undo_reason = reason
    row.reversed_at = datetime.now(timezone.utc)
    row.reversed_by_admin_id = admin_id
    row.reversal_token_before = subscription.remaining_tokens
    subscription.remaining_tokens += 1
    row.reversal_token_after = subscription.remaining_tokens
    subscription.status = effective_status(subscription)
    await db.flush()
    await db.refresh(subscription)
    return row, subscription


@mess_router.post("/attendance/{attendance_id}/undo")
async def undo_attendance(attendance_id: int, payload: MessUndoInput, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    row, subscription = await undo_meal(db, attendance_id, payload.reason, admin.id)
    await db.commit()
    return {"attendance": serialize(row), "subscription": serialize(subscription)}


async def daily_rows(db, day, meal, search="", plan_type=None):
    query = select(MessSubscription, MessMealAttendance, AdminUser.username).outerjoin(
        MessMealAttendance, and_(MessMealAttendance.subscription_id == MessSubscription.id,
            MessMealAttendance.meal_date == day, MessMealAttendance.meal_type == meal,
            MessMealAttendance.status == "Taken")
    ).outerjoin(AdminUser, AdminUser.id == MessMealAttendance.marked_by_admin_id).where(or_(
        and_(MessSubscription.start_date <= day, MessSubscription.end_date >= day),
        MessMealAttendance.id.is_not(None),
    )).order_by(MessSubscription.student_name, MessSubscription.id)
    query = search_query(query, search)
    if plan_type:
        query = query.where(MessSubscription.plan_type == plan_type)
    results = []
    for s, a, username in (await db.execute(query)).all():
        eligible = effective_status(s, day) == "Active" and s.start_date <= day <= s.end_date
        results.append({"subscription": serialize(s),
            "attendance": {**serialize(a), "marked_by": username} if a else None,
            "eligible": eligible or (a is not None and s.status != "Cancelled"),
            "can_mark": eligible and a is None and day == mess_today() and meal in ("Lunch", "Dinner")})
    return results


@mess_router.get("/attendance")
async def attendance(meal_date: Optional[date] = None, meal_type: Meal = "Lunch", search: str = Query("", max_length=100),
                     filter: Literal["All", "Taken", "Not Taken", "Low Tokens", "No Tokens"] = "All",
                     plan_type: Optional[Literal["single", "double"]] = None,
                     db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    rows = await daily_rows(db, meal_date or mess_today(), meal_type, search, plan_type)
    return [r for r in rows if filter == "All" or
        (filter == "Taken" and r["attendance"]) or (filter == "Not Taken" and not r["attendance"]) or
        (filter == "Low Tokens" and 0 < r["subscription"]["remaining_tokens"] <= 5) or
        (filter == "No Tokens" and r["subscription"]["remaining_tokens"] == 0)]


@mess_router.get("/stats")
async def stats(meal_date: Optional[date] = None, meal_type: Meal = "Lunch",
                db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    day = meal_date or mess_today()
    rows = await daily_rows(db, day, meal_type)
    taken = sum(r["attendance"] is not None for r in rows)
    eligible = sum(r["eligible"] for r in rows)
    members = (await db.execute(select(MessSubscription))).scalars().all()
    consumed_today = (await db.execute(select(func.count()).select_from(MessMealAttendance).where(
        MessMealAttendance.meal_date == day, MessMealAttendance.status == "Taken"))).scalar_one()
    return {"meal_date": day, "meal_type": meal_type,
        "total_active_members": sum(effective_status(s, day) == "Active" and s.start_date <= day for s in members),
        "eligible_members": eligible, "meals_taken": taken,
        "meals_remaining": sum(r["eligible"] and r["attendance"] is None for r in rows),
        "tokens_consumed": taken, "tokens_consumed_today": consumed_today,
        "low_token_members": sum(0 < r["subscription"]["remaining_tokens"] <= 5 for r in rows),
        "zero_token_members": sum(r["subscription"]["remaining_tokens"] == 0 for r in rows),
        "expired_memberships": sum(effective_status(s, day) == "Expired" for s in members)}


@mess_router.get("/plans")
async def plans(db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    cached = await cache_get("canteen:mess:plans")
    if cached is not None:
        return cached
    rows = [serialize(p) for p in (await db.execute(select(MessPlan).order_by(MessPlan.id))).scalars()]
    # Only plan defaults are cached; live token balances always come from PostgreSQL.
    await cache_set("canteen:mess:plans", [{**r, "amount": float(r["amount"])} for r in rows])
    return rows


@mess_router.put("/plans/{plan_id}")
async def update_plan(plan_id: str, payload: MessPlanUpdate, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    row = (await db.execute(select(MessPlan).where(MessPlan.id == plan_id).with_for_update())).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Plan not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    await db.commit()
    await cache_invalidate_prefix("canteen:mess:")
    return serialize(row)
