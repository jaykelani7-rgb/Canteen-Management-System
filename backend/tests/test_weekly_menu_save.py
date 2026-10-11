"""Regression tests for the authenticated weekly-menu bulk save endpoint."""
import pytest
from sqlalchemy import event, select

import routes
from config import settings
from models import WeeklyMenu
from test_mess import mess_client


@pytest.fixture(autouse=True)
def avoid_external_side_effects(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    async def no_cache_invalidation(*args, **kwargs):
        return 0

    monkeypatch.setattr(routes, "cache_invalidate_prefix", no_cache_invalidation)


async def test_weekly_menu_saves_28_slots_in_one_database_statement_and_upserts(mess_client):
    client, sessions, _ = mess_client
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    meals = ["breakfast", "lunch", "snacks", "dinner"]
    schedule = [
        {"day": day, "meal_type": meal, "items": [f"{day} {meal}"]}
        for day in days
        for meal in meals
    ]

    engine = sessions.kw["bind"]
    insert_statements = []

    def count_weekly_menu_inserts(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO WEEKLY_MENU"):
            insert_statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count_weekly_menu_inserts)
    try:
        response = await client.post("/api/admin/menu/weekly", json={"schedule": schedule})
        assert response.status_code == 200, response.text
        assert len(insert_statements) == 1, "A complete weekly schedule should use one bulk upsert statement"

        replacement = [dict(item) for item in schedule]
        replacement[0]["items"] = ["Updated Monday breakfast"]
        insert_statements.clear()
        updated = await client.post("/api/admin/menu/weekly", json={"schedule": replacement})
        assert updated.status_code == 200, updated.text
        assert len(insert_statements) == 1, "Updating a schedule should still use one bulk upsert statement"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_weekly_menu_inserts)

    async with sessions() as db:
        rows = (await db.execute(select(WeeklyMenu))).scalars().all()

    assert len(rows) == 28, "Upserting the menu must not create duplicate day/meal rows"
    monday_breakfast = next(row for row in rows if row.day == "Monday" and row.meal_type == "breakfast")
    assert monday_breakfast.items == ["Updated Monday breakfast"]
