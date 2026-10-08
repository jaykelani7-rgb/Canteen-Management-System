"""API tests default to a transient SQLite test database.

Set MESS_TEST_DATABASE_URL to the existing PostgreSQL URL to run these tests
including true row-lock concurrency in disposable schemas of that database.
No application data is dropped or modified.
"""
import asyncio
import os
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from auth import create_access_token, get_password_hash
from database import Base, get_db
from main import app
from models import AdminUser, StudentUser, MessSubscription, MessMealAttendance
import mess_routes
from mess_seed import seed_mess

DAY = date(2026, 10, 8)
PREFIX = "/api/admin/mess"


@pytest_asyncio.fixture
async def mess_client(monkeypatch):
    url = os.getenv("MESS_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    schema = "mess_test_" + uuid.uuid4().hex
    postgres = url.startswith("postgresql")
    admin_engine = create_async_engine(url)
    if postgres:
        async with admin_engine.begin() as conn:
            await conn.execute(CreateSchema(schema))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}, "statement_cache_size": 0})
    else:
        engine = admin_engine
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(mess_routes, "mess_today", lambda: DAY)
    async def no_cache(*args, **kwargs):
        return None
    for name in ["cache_get", "cache_set", "cache_invalidate_prefix"]:
        monkeypatch.setattr(mess_routes, name, no_cache)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        db.add(AdminUser(username="test-admin", hashed_password=get_password_hash("test-password"), role="admin", is_active=True))
        db.add(StudentUser(id="linked-student", roll_number="21CS1042", name="Aarav Sharma", email="aarav@test.invalid", hashed_passcode="unused", branch="CS"))
        await mess_routes.ensure_mess_plans(db)
        await db.commit()
    async def override_db():
        async with sessions() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise
    app.dependency_overrides[get_db] = override_db
    token = create_access_token({"sub": "test-admin", "role": "admin"})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer " + token}) as client:
            yield client, sessions, postgres
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
        if postgres:
            async with admin_engine.begin() as conn:
                await conn.execute(DropSchema(schema, cascade=True))
            await admin_engine.dispose()


def payload(plan="double", roll="24CS9999", **changes):
    return {"student_name": "Krishna Israni", "roll_number": roll, "year": "2nd Year", "branch": "CS",
        "mobile_number": "9876543210", "plan_type": plan, "start_date": str(DAY), "payment_method": "Cash", **changes}


async def create(client, **changes):
    response = await client.post(PREFIX + "/subscriptions", json=payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


async def mark(client, sub, meal="Lunch", day=DAY):
    return await client.post(PREFIX + "/attendance/mark", json={"subscription_id": sub["id"], "meal_date": str(day), "meal_type": meal})


@pytest.mark.parametrize("plan,amount,tokens", [("single", 1800, 28), ("double", 3600, 55)])
async def test_plan_initialization(mess_client, plan, amount, tokens):
    client, _, _ = mess_client
    sub = await create(client, plan=plan)
    assert sub["amount_paid"] == amount
    assert sub["total_tokens"] == sub["remaining_tokens"] == tokens
    assert sub["end_date"] == str(DAY + timedelta(days=30))
    assert sub["status"] == "Active"


async def test_acceptance_duplicate_dinner_history(mess_client):
    client, _, _ = mess_client
    sub = await create(client)
    lunch = await mark(client, sub)
    assert lunch.status_code == 201
    assert lunch.json()["subscription"]["remaining_tokens"] == 54
    duplicate = await mark(client, sub)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Lunch already marked for this student today."
    dinner = await mark(client, sub, "Dinner")
    assert dinner.status_code == 201
    assert dinner.json()["subscription"]["remaining_tokens"] == 53
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["tokens_used"] == detail["meals_taken"] == 2
    assert detail["remaining_tokens"] == 53
    assert {(r["meal_type"], r["token_before"], r["token_after"]) for r in detail["attendance"]} == {("Lunch", 55, 54), ("Dinner", 54, 53)}
    assert all(r["marked_by"] == "test-admin" for r in detail["attendance"])


async def test_undo_and_remark_preserves_audit(mess_client):
    client, _, _ = mess_client
    sub = await create(client)
    row = (await mark(client, sub)).json()["attendance"]
    empty_reason = await client.post(f'{PREFIX}/attendance/{row["id"]}/undo', json={"reason": " "})
    assert empty_reason.status_code == 422
    undo = await client.post(f'{PREFIX}/attendance/{row["id"]}/undo', json={"reason": "Marked wrong student"})
    assert undo.status_code == 200
    assert undo.json()["subscription"]["remaining_tokens"] == 55
    assert undo.json()["attendance"]["reversal_token_before"] == 54
    assert undo.json()["attendance"]["reversal_token_after"] == 55
    assert undo.json()["attendance"]["undo_reason"] == "Marked wrong student"
    assert undo.json()["attendance"]["reversed_by_admin_id"] is not None
    assert undo.json()["attendance"]["reversed_at"] is not None
    assert (await client.post(f'{PREFIX}/attendance/{row["id"]}/undo', json={"reason": "Again"})).status_code == 409
    assert (await mark(client, sub)).status_code == 201
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert len(detail["attendance"]) == 2
    assert {a["status"] for a in detail["attendance"]} == {"Taken", "Reversed"}
    assert detail["tokens_used"] == detail["meals_taken"] == 1


@pytest.mark.parametrize("case", ["expired", "future", "cancelled"])
async def test_invalid_subscription_cannot_consume(mess_client, case):
    client, _, _ = mess_client
    changes = {"start_date": str(DAY - timedelta(days=40)), "end_date": str(DAY - timedelta(days=1))} if case == "expired" else {"start_date": str(DAY + timedelta(days=1))} if case == "future" else {}
    sub = await create(client, **changes)
    if case == "cancelled":
        response = await client.put(f'{PREFIX}/subscriptions/{sub["id"]}', json={**payload(), "status": "Cancelled"})
        assert response.status_code == 200
    response = await mark(client, sub)
    assert response.status_code in (400, 409)
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 55
    assert not detail["attendance"]
    if case == "expired":
        assert detail["status"] == "Expired"


async def test_exhausted_last_token_and_restore(mess_client):
    client, _, _ = mess_client
    sub = await create(client, total_tokens=1)
    lunch = await mark(client, sub)
    assert lunch.json()["subscription"]["remaining_tokens"] == 0
    assert lunch.json()["subscription"]["status"] == "Exhausted"
    assert (await mark(client, sub, "Dinner")).status_code == 409
    stats = (await client.get(PREFIX + "/stats")).json()
    assert stats["eligible_members"] == stats["meals_taken"] == 1
    assert stats["meals_remaining"] == 0
    undo = await client.post(f'{PREFIX}/attendance/{lunch.json()["attendance"]["id"]}/undo', json={"reason": "Wrong student"})
    assert undo.json()["subscription"]["status"] == "Active"


async def test_date_validation_and_past_read_only(mess_client):
    client, sessions, _ = mess_client
    assert (await client.post(PREFIX + "/subscriptions", json=payload(end_date=str(DAY - timedelta(days=1))))).status_code == 422
    sub = await create(client, start_date=str(DAY - timedelta(days=2)))
    assert (await mark(client, sub, day=DAY - timedelta(days=1))).status_code == 400
    assert (await mark(client, sub, day=DAY + timedelta(days=1))).status_code == 400
    async with sessions() as db:
        row = MessMealAttendance(subscription_id=sub["id"], meal_date=DAY - timedelta(days=1), meal_type="Lunch", status="Taken", token_before=55, token_after=54)
        db.add(row)
        s = await db.get(MessSubscription, sub["id"])
        s.remaining_tokens = 54
        await db.commit()
        row_id = row.id
    assert (await client.post(f'{PREFIX}/attendance/{row_id}/undo', json={"reason": "Wrong student"})).status_code == 400
    history = (await client.get(PREFIX + "/attendance", params={"meal_date": str(DAY - timedelta(days=1))})).json()
    assert history[0]["attendance"]["id"] == row_id
    assert history[0]["can_mark"] is False


async def test_student_link_and_overlap(mess_client):
    client, sessions, _ = mess_client
    sub = await create(client, roll="21cs 1042")
    assert sub["student_id"] == "linked-student"
    assert (await client.post(PREFIX + "/subscriptions", json=payload(roll="21CS1042"))).status_code == 409
    unlinked = await create(client, roll="25CS1234")
    assert unlinked["student_id"] is None
    async with sessions() as db:
        assert len((await db.execute(select(StudentUser))).scalars().all()) == 1


async def test_search_filters_and_stats(mess_client):
    client, _, _ = mess_client
    sub = await create(client, total_tokens=5)
    await create(client, plan="single", roll="25IT1234", student_name="Priya Patel", mobile_number="9999912345")
    assert len((await client.get(PREFIX + "/subscriptions", params={"search": "krishna"})).json()) == 1
    assert len((await client.get(PREFIX + "/attendance", params={"search": "24cs9999"})).json()) == 1
    assert len((await client.get(PREFIX + "/attendance", params={"search": "9999912345"})).json()) == 1
    assert len((await client.get(PREFIX + "/attendance", params={"filter": "Low Tokens"})).json()) == 1
    assert len((await client.get(PREFIX + "/attendance", params={"plan_type": "single"})).json()) == 1
    await mark(client, sub)
    assert len((await client.get(PREFIX + "/attendance", params={"filter": "Taken"})).json()) == 1
    assert len((await client.get(PREFIX + "/attendance", params={"filter": "Not Taken"})).json()) == 1
    assert len((await client.get(PREFIX + "/attendance", params={"filter": "No Tokens"})).json()) == 0
    stats = (await client.get(PREFIX + "/stats")).json()
    assert (stats["eligible_members"], stats["meals_taken"], stats["meals_remaining"], stats["tokens_consumed_today"]) == (2, 1, 1, 1)


async def test_admin_auth_and_untrusted_balance(mess_client):
    client, _, _ = mess_client
    token = create_access_token({"sub": "linked-student", "role": "student"})
    for method, route, data in [("GET", "/subscriptions", None), ("GET", "/subscriptions/1", None), ("GET", "/plans", None), ("GET", "/stats", None), ("GET", "/attendance", None), ("POST", "/subscriptions", payload()), ("POST", "/attendance/mark", {"subscription_id": 1, "meal_date": str(DAY), "meal_type": "Lunch"}), ("POST", "/attendance/1/undo", {"reason": "Mistake"}), ("PUT", "/plans/single", {"name": "Single", "amount": 1800, "tokens": 28, "duration_days": 30}), ("PUT", "/subscriptions/1", payload())]:
        response = await client.request(method, PREFIX + route, json=data, headers={"Authorization": "Bearer " + token})
        assert response.status_code in (401, 403), response.text
    assert (await client.get(PREFIX + "/subscriptions", headers={"Authorization": ""})).status_code == 401
    assert (await client.post(PREFIX + "/subscriptions", json=payload(remaining_tokens=500))).status_code == 422
    sub = await create(client)
    assert (await client.post(PREFIX + "/attendance/mark", json={"subscription_id": sub["id"], "meal_date": str(DAY), "meal_type": "Lunch", "remaining_tokens": 999})).status_code == 422
    login = await client.post("/api/admin/login", json={"username": "test-admin", "password": "test-password"})
    assert login.status_code == 200


async def test_plan_edits_activation_and_existing_agreement(mess_client):
    client, _, _ = mess_client
    old = await create(client)
    changed = {"name": "Double Plus", "amount": 4000, "tokens": 60, "duration_days": 28, "is_active": True}
    assert (await client.put(PREFIX + "/plans/double", json=changed)).status_code == 200
    new = await create(client, roll="25CS6789")
    assert new["total_tokens"] == 60 and new["amount_paid"] == 4000
    assert new["end_date"] == str(DAY + timedelta(days=28))
    old_detail = (await client.get(f'{PREFIX}/subscriptions/{old["id"]}')).json()
    assert old_detail["total_tokens"] == old_detail["remaining_tokens"] == 55
    assert old_detail["amount_paid"] == 3600
    assert old_detail["end_date"] == str(DAY + timedelta(days=30))
    # Optional snapshot fields on an ordinary member edit must also stay intact.
    edited = await client.put(f'{PREFIX}/subscriptions/{old["id"]}', json=payload(notes="Mobile confirmed"))
    assert edited.status_code == 200
    assert edited.json()["total_tokens"] == edited.json()["remaining_tokens"] == 55
    assert edited.json()["amount_paid"] == 3600
    assert edited.json()["end_date"] == str(DAY + timedelta(days=30))
    assert (await client.put(PREFIX + "/plans/double", json={**changed, "is_active": False})).status_code == 200
    assert (await client.post(PREFIX + "/subscriptions", json=payload(roll="26CS0001"))).status_code == 409
    assert (await mark(client, old)).status_code == 201


async def test_edit_preserves_consumption_and_history(mess_client):
    client, _, _ = mess_client
    sub = await create(client)
    await mark(client, sub)
    edited = await client.put(f'{PREFIX}/subscriptions/{sub["id"]}', json=payload(total_tokens=60))
    assert edited.status_code == 200
    assert edited.json()["remaining_tokens"] == 59
    assert (await client.put(f'{PREFIX}/subscriptions/{sub["id"]}', json=payload(roll="NEW123"))).status_code == 409
    assert (await client.put(f'{PREFIX}/subscriptions/{sub["id"]}', json=payload(start_date=str(DAY + timedelta(days=1))))).status_code == 409


async def test_database_unique_constraint(mess_client):
    client, sessions, _ = mess_client
    sub = await create(client)
    await mark(client, sub)
    async with sessions() as db:
        db.add(MessMealAttendance(subscription_id=sub["id"], meal_date=DAY, meal_type="Lunch", status="Taken", token_before=54, token_after=53))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 54 and len(detail["attendance"]) == 1


async def test_seed_idempotent_and_ledger(mess_client, monkeypatch):
    client, sessions, _ = mess_client
    import mess_seed
    monkeypatch.setattr(mess_seed, "mess_today", lambda: DAY)
    async with sessions() as db:
        await seed_mess(db)
        await seed_mess(db)
    members = (await client.get(PREFIX + "/subscriptions")).json()
    assert len(members) == 5
    assert all(s["status"] == "Active" for s in members)
    for s in members:
        detail = (await client.get(f'{PREFIX}/subscriptions/{s["id"]}')).json()
        assert detail["tokens_used"] == detail["meals_taken"]
    assert sum(s["remaining_tokens"] for s in members if s["roll_number"] == "21CS1042") == 49
    assert len((await client.get(PREFIX + "/attendance", params={"filter": "Taken"})).json()) == 2


async def test_postgresql_concurrent_deductions(mess_client):
    client, _, postgres = mess_client
    if not postgres:
        pytest.skip("Requires MESS_TEST_DATABASE_URL: SQLite cannot validate PostgreSQL row locks")
    sub = await create(client)
    responses = await asyncio.gather(mark(client, sub), mark(client, sub), mark(client, sub, "Dinner"))
    assert sorted(r.status_code for r in responses) == [201, 201, 409]
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 53
    assert sorted((r["token_before"], r["token_after"]) for r in detail["attendance"]) == [(54, 53), (55, 54)]


@pytest.mark.parametrize("meal", ["Breakfast", "Snacks", "Unsupported"])
async def test_only_lunch_and_dinner_can_be_marked(mess_client, meal):
    client, _, _ = mess_client
    sub = await create(client)
    assert (await mark(client, sub, meal)).status_code == 422
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 55
    assert detail["attendance"] == []


async def test_other_meal_history_is_preserved(mess_client):
    client, sessions, _ = mess_client
    sub = await create(client)
    await create(client, roll="24CSOTHER")
    async with sessions() as db:
        row = await db.get(MessSubscription, sub["id"])
        row.remaining_tokens = 54
        db.add(MessMealAttendance(subscription_id=sub["id"], meal_date=DAY, meal_type="Breakfast",
            status="Taken", token_before=55, token_after=54))
        await db.commit()
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["attendance"][0]["meal_type"] == "Breakfast"
    rows = (await client.get(PREFIX + "/attendance", params={"meal_type": "Breakfast"})).json()
    assert rows[0]["attendance"]["meal_type"] == "Breakfast"
    assert all(row["can_mark"] is False for row in rows)


async def test_postgresql_concurrent_last_token(mess_client):
    client, _, postgres = mess_client
    if not postgres:
        pytest.skip("Requires PostgreSQL row locks")
    sub = await create(client, total_tokens=1)
    responses = await asyncio.gather(mark(client, sub), mark(client, sub, "Dinner"))
    assert sorted(r.status_code for r in responses) == [201, 409]
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 0
    assert detail["status"] == "Exhausted"
    assert len(detail["attendance"]) == 1


async def test_postgresql_concurrent_undo_restores_once(mess_client):
    client, _, postgres = mess_client
    if not postgres:
        pytest.skip("Requires PostgreSQL row locks")
    sub = await create(client)
    marked = (await mark(client, sub)).json()["attendance"]
    endpoint = f'{PREFIX}/attendance/{marked["id"]}/undo'
    responses = await asyncio.gather(*[
        client.post(endpoint, json={"reason": "Duplicate staff correction"}) for _ in range(2)
    ])
    assert sorted(r.status_code for r in responses) == [200, 409]
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 55
    assert detail["tokens_used"] == detail["meals_taken"] == 0
    assert len(detail["attendance"]) == 1
    assert detail["attendance"][0]["status"] == "Reversed"


async def test_postgresql_mark_and_undo_serialize(mess_client):
    client, _, postgres = mess_client
    if not postgres:
        pytest.skip("Requires PostgreSQL row locks")
    sub = await create(client)
    lunch = (await mark(client, sub)).json()["attendance"]
    undo, dinner = await asyncio.gather(
        client.post(f'{PREFIX}/attendance/{lunch["id"]}/undo', json={"reason": "Wrong lunch student"}),
        mark(client, sub, "Dinner"),
    )
    assert undo.status_code == 200
    assert dinner.status_code == 201
    detail = (await client.get(f'{PREFIX}/subscriptions/{sub["id"]}')).json()
    assert detail["remaining_tokens"] == 54
    assert detail["tokens_used"] == detail["meals_taken"] == 1
    assert {(r["meal_type"], r["status"]) for r in detail["attendance"]} == {("Lunch", "Reversed"), ("Dinner", "Taken")}
