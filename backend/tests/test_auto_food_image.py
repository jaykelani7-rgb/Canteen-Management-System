"""Offline tests for automatic licensed food-photo matching and catalogue integration."""
import pytest
from sqlalchemy import select

from config import settings
from food_image_models import FoodImage
from image_fixtures import attach_test_image
from models import FoodItem
from test_mess import mess_client
import admin_operations
from auto_food_image import (
    is_reusable_license, _relevance, _openverse_license_name,
    _openverse_search_query, _openverse_relevance,
)


@pytest.fixture(autouse=True)
def test_config(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_API_ORIGIN", "http://test")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    async def no_cache(*args, **kwargs):
        return None
    monkeypatch.setattr(admin_operations, "cache_invalidate_prefix", no_cache)


def test_only_commercial_reusable_licenses_are_accepted():
    for value in ("CC BY 4.0", "CC BY-SA 4.0", "CC0 1.0", "Public domain", "PDM 1.0"):
        assert is_reusable_license(value)
    for value in ("CC BY-NC 4.0", "CC BY-NC-SA 4.0", "CC BY-ND 4.0", "CC BY-NC-ND 4.0", "Unknown"):
        assert not is_reusable_license(value)


def test_search_results_need_matching_dish_terms():
    assert _relevance("Paneer Tikka Roll", "Paneer tikka roll.jpg", {}) == 3
    assert _relevance("Paneer Tikka Roll", "A bowl of pasta.jpg", {}) == 0


async def test_dish_is_saved_with_automatic_photo_without_upload(mess_client, monkeypatch):
    client, sessions, _ = mess_client
    async def fake_match(db, dish_name, admin_id):
        return await attach_test_image(db, FoodItem(name=dish_name), admin_id=admin_id)
    monkeypatch.setattr(admin_operations, "find_and_store_food_image", fake_match)
    response = await client.post("/api/admin/catalogue", json={
        "name": "Samosa", "price": 25, "category": "Snacks", "available": True, "timingWindow": "all_day",
    })
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["available"] is True and item["imageId"] and item["imageConfirmed"] is True
    assert item["photo"].startswith("http://test/api/food-images/")
    async with sessions() as db:
        photo = (await db.execute(select(FoodImage).where(FoodImage.id == item["imageId"]))).scalar_one()
        assert photo.dish_name == "Samosa" and photo.rights_confirmed and photo.byte_size > 0


async def test_unmatched_dish_can_be_saved_and_made_available_without_a_photo(mess_client, monkeypatch):
    client, _, _ = mess_client
    async def no_match(*args, **kwargs):
        return None
    monkeypatch.setattr(admin_operations, "find_and_store_food_image", no_match)
    response = await client.post("/api/admin/catalogue", json={"name": "No match", "price": 20, "available": True})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["available"] is True and not item["imageId"] and item["photo"] is None
    toggle = await client.patch(f"/api/admin/catalogue/{item['id']}/availability", json={"available": False})
    assert toggle.status_code == 200 and toggle.json()["available"] is False
    toggle_on = await client.patch(f"/api/admin/catalogue/{item['id']}/availability", json={"available": True})
    assert toggle_on.status_code == 200 and toggle_on.json()["available"] is True

def test_openverse_license_mapping_only_allows_commercially_reusable_images():
    assert _openverse_license_name("by", "4.0") == "CC BY 4.0"
    assert _openverse_license_name("by-sa", "4.0") == "CC BY-SA 4.0"
    assert _openverse_license_name("cc0", "1.0") == "CC0 1.0"
    assert _openverse_license_name("pdm", "1.0") == "Public Domain Mark 1.0"
    for code in ("by-nc", "by-nc-sa", "by-nd", "by-nc-nd", "unknown", ""):
        assert not _openverse_license_name(code, "4.0")


def test_openverse_search_expands_every_dish_and_common_regional_spellings():
    # Generic exact + food + Indian food queries are created for every name, not one dish.
    for dish in ("Sabudana Khichdi", "Paneer Tikka", "Chocolate Brownie", "Veg Sandwich"):
        query = _openverse_search_query(dish)
        assert dish.lower() in query.lower()
        assert "food" in query.lower()
        assert len(query) <= 200
    assert "sago" in _openverse_search_query("Sabudana Khichdi").lower()
    assert "poha" in _openverse_search_query("Pohe").lower()


def test_openverse_match_checks_titles_tags_and_ingredient_aliases():
    assert _openverse_relevance("Sabudana Khichdi", {
        "title": "Sabudana Khichdi served on a plate",
        "tags": [],
    }) > 0
    assert _openverse_relevance("Sabudana Khichdi", {
        "title": "Tapioca pearls served on a plate",
        "tags": [{"name": "Indian cuisine"}],
    }) > 0
    assert _openverse_relevance("Sabudana Khichdi", {
        "title": "Tapioca plant in a green field",
        "tags": [{"name": "botany"}],
    }) == 0
    assert _openverse_relevance("Paneer Tikka", {
        "title": "A dog running in a park",
        "tags": [],
    }) == 0

