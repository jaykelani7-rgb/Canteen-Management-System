"""Public menu eligibility must agree with authoritative checkout and admin inventory."""
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import func, select

from auth import create_access_token, credential_fingerprint, get_password_hash
from config import settings
from models import FoodItem, Order, StudentUser, WalletTransaction
import student_routes
from test_mess import mess_client
from image_fixtures import attach_test_image


@pytest.fixture(autouse=True)
def prevent_external_cache_and_rate_limits(monkeypatch):
    monkeypatch.setattr(settings,"PUBLIC_API_ORIGIN","http://test")
    async def no_cache(*args, **kwargs):
        return None
    monkeypatch.setattr(student_routes, "cache_get", no_cache)
    monkeypatch.setattr(student_routes, "cache_set", no_cache)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)


async def configure_menu(sessions):
    async with sessions() as db:
        rows=[
            FoodItem(id="public-dosa", name="Dosa", price=40, category="Meals", desc="South Dish", is_available=True),
            FoodItem(id="public-pohe", name="Pohe", price=25, category="Snacks", is_available=True),
            FoodItem(id="disabled-test-item", name="STAGING QA disabled", price=10, category="Snacks", is_available=False),
        ]
        for item in rows[:2]:
            await attach_test_image(db,item)
        db.add_all(rows)
        await db.commit()


async def test_public_menu_excludes_inactive_even_when_legacy_flag_false(mess_client):
    client, sessions, _ = mess_client
    await configure_menu(sessions)
    for suffix in ("", "?available_only=false", "?available_only=true"):
        response = await client.get("/api/menu/items" + suffix)
        assert response.status_code == 200
        assert {row["id"] for row in response.json()} == {"public-dosa", "public-pohe"}
        assert all(row["available"] for row in response.json())
    inventory = await client.get("/api/admin/catalogue")
    assert inventory.status_code == 200
    assert {row["id"] for row in inventory.json()} == {"public-dosa", "public-pohe", "disabled-test-item"}


async def test_public_search_category_and_fields_use_authoritative_values(mess_client):
    client, sessions, _ = mess_client
    await configure_menu(sessions)
    meals = await client.get("/api/menu/items?category=Meals&query=dos")
    assert meals.status_code == 200 and len(meals.json()) == 1
    item = meals.json()[0]
    assert item["name"] == "Dosa" and item["category"] == "Meals" and item["desc"] == "South Dish"
    assert item["price"] == 40 and isinstance(item["price"], (int, float))
    assert item["photo"].startswith("http://test/api/food-images/") and item["imageConfirmed"] is True
    snacks = await client.get("/api/menu/items?category=Snacks")
    assert [row["name"] for row in snacks.json()] == ["Pohe"]


async def test_inactive_public_detail_is_unavailable_without_erasing_inventory(mess_client):
    client, sessions, _ = mess_client
    await configure_menu(sessions)
    assert (await client.get("/api/menu/items/disabled-test-item")).status_code == 404
    assert (await client.get("/api/menu/items/public-dosa")).status_code == 200
    async with sessions() as db:
        assert await db.get(FoodItem, "disabled-test-item") is not None


async def test_available_menu_uses_new_cache_namespace(mess_client, monkeypatch):
    client, sessions, _ = mess_client
    await configure_menu(sessions)
    keys = []
    async def cache_read(key):
        keys.append(key)
        return None
    async def cache_write(key, value, **kwargs):
        assert all(row["available"] for row in value)
    monkeypatch.setattr(student_routes, "cache_get", cache_read)
    monkeypatch.setattr(student_routes, "cache_set", cache_write)
    response = await client.get("/api/menu/items?available_only=false")
    assert response.status_code == 200
    assert keys and all(key.startswith("canteen:food_items:public_photographed_v2:") for key in keys)


@pytest.mark.parametrize("item_id", ["disabled-test-item", "missing-item"])
async def test_unavailable_order_does_not_create_order_or_debit_wallet(mess_client, item_id):
    client, sessions, _ = mess_client
    await configure_menu(sessions)
    async with sessions() as db:
        student = await db.get(StudentUser, "linked-student")
        student.wallet_balance = Decimal("100.00")
        student.hashed_passcode = get_password_hash("765432")
        await db.commit()
        token = create_access_token({"sub": student.id, "role": "student",
                                     "credential_version": credential_fingerprint(student.hashed_passcode)})
    response = await client.post("/api/student/orders", headers={"Authorization": "Bearer " + token,
        "Idempotency-Key": uuid.uuid4().hex}, json={"items": [{"id": item_id, "qty": 1}], "paymentMethod": "wallet"})
    assert response.status_code == 409
    async with sessions() as db:
        assert (await db.get(StudentUser, "linked-student")).wallet_balance == Decimal("100.00")
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0


async def test_active_photo_missing_or_unconfirmed_is_not_published(mess_client):
    client,sessions,_=mess_client
    await configure_menu(sessions)
    async with sessions() as db:
        db.add(FoodItem(id="missing-photo",name="Unphotographed dish",price=25,is_available=True))
        existing=await db.get(FoodItem,"public-pohe"); existing.image_confirmed=False
        await db.commit()
    assert {item["id"] for item in (await client.get("/api/menu/items")).json()}=={"public-dosa"}
    assert (await client.get("/api/menu/items/missing-photo")).status_code==404
    assert (await client.get("/api/menu/items/public-pohe")).status_code==404
