"""Idempotent demo mess subscriptions; never reset existing token balances."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from models import MessSubscription, MessMealAttendance, StudentUser, MessPlan
from mess_routes import ensure_mess_plans, mess_today, lock_roll, validate_overlap


async def seed_mess(db):
    await ensure_mess_plans(db)
    day = mess_today()
    demos = [
        ("21CS1042", "Aarav Sharma", "double", 6, "2nd Year", "Computer Science", "9876543210"),
        ("21IT2015", "Priya Patel", "single", 1, "2nd Year", "Information Technology", "9876511223"),
        ("22EC3088", "Rohan Verma", "double", 3, "3rd Year", "Electronics", "9876599887"),
        ("23ME5001", "Ananya Iyer", "single", 0, "2nd Year", "Mechanical", "9876566554"),
        ("23CS5099", "Kabir Shah", "double", 0, "2nd Year", "Computer Science", "9876545678"),
    ]
    for roll, name, plan_id, used, year, branch, mobile in demos:
        await lock_roll(db, roll)
        existing = (await db.execute(select(MessSubscription.id).where(
            MessSubscription.roll_number == roll, MessSubscription.status != "Cancelled",
            MessSubscription.start_date <= day, MessSubscription.end_date >= day,
        ))).first()
        if existing:
            continue
        plan = await db.get(MessPlan, plan_id)
        if not plan.is_active:
            continue
        start = day - timedelta(days=3)
        end = start + timedelta(days=plan.duration_days)
        await validate_overlap(db, roll, start, end)
        student = (await db.execute(select(StudentUser).where(StudentUser.roll_number == roll))).scalar_one_or_none()
        used = min(used, plan.tokens)
        sub = MessSubscription(student_id=student.id if student else None, student_name=name,
            roll_number=roll, year=year, branch=branch, mobile_number=mobile, plan_type=plan_id,
            amount_paid=plan.amount, total_tokens=plan.tokens, remaining_tokens=plan.tokens - used,
            start_date=start, end_date=end, payment_method="Cash", payment_reference="DEMO-" + roll,
            notes="Demo mess subscription", status="Exhausted" if used == plan.tokens else "Active")
        db.add(sub)
        await db.flush()
        # Most recent rows are today's lunch and dinner; every used token has a row.
        for i in range(used):
            offset = (used - 1 - i) // 2
            meal = "Lunch" if (used - 1 - i) % 2 else "Dinner"
            before = plan.tokens - i
            db.add(MessMealAttendance(subscription_id=sub.id, student_id=sub.student_id,
                meal_date=day - timedelta(days=offset), meal_type=meal, status="Taken",
                token_before=before, token_after=before - 1,
                marked_at=datetime.now(timezone.utc) - timedelta(days=offset)))
    await db.commit()
