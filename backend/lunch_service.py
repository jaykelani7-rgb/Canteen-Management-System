"""Current IST meal configuration and server-authoritative bundle snapshots.

The lunch module/imports remain compatible; dinner uses the same implementation.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from models import FoodItem, MealType, WeeklyMenu

BUNDLE_MEALS = ("lunch", "dinner")
MEAL_OPTIONS = {
    meal: (
        {"id": f"{meal}-chapati-bhaji", "name": "Chapati Bhaji", "price": 45},
        {"id": f"{meal}-thali", "name": "Thali", "price": 80},
    ) for meal in BUNDLE_MEALS
}
LUNCH_OPTIONS = MEAL_OPTIONS["lunch"]
LUNCH_IDS = frozenset(option["id"] for option in LUNCH_OPTIONS)
DINNER_OPTIONS = MEAL_OPTIONS["dinner"]
DINNER_IDS = frozenset(option["id"] for option in DINNER_OPTIONS)
BUNDLE_IDS = LUNCH_IDS | DINNER_IDS
BUNDLE_MEAL_BY_ID = {option["id"]: meal for meal, options in MEAL_OPTIONS.items() for option in options}


def lunch_now():
    # Preserve the existing clock hook for callers/tests of the lunch service.
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def validate_meal_configuration(items, sabji_options, enabled, meal_type="lunch"):
    """Validate saved choices, independently of temporary catalogue availability."""
    if not enabled:
        return
    if not items or any(not isinstance(item, str) or not item.strip() for item in items):
        raise HTTPException(422, f"Enabled {meal_type} requires the complete meal contents")
    if (len(sabji_options) != 2 or any(not isinstance(item, str) or not item.strip() for item in sabji_options)
            or len({item.casefold() for item in sabji_options}) != 2
            or any(item not in items for item in sabji_options)):
        raise HTTPException(422, f"Enabled {meal_type} requires exactly two distinct sabji options from the complete meal contents")


def validate_lunch_configuration(items, sabji_options, enabled):
    return validate_meal_configuration(items, sabji_options, enabled, "lunch")


def meal_state(row, now, availability=None, meal_type="lunch"):
    from routes import MEAL_WINDOWS, determine_current_or_upcoming_meal
    if meal_type not in BUNDLE_MEALS:
        raise ValueError("Unsupported bundle meal period")
    title = meal_type.capitalize()
    configured_contents = list(row.items or []) if row else []
    configured_sabjis = list(row.sabji_options or []) if row else []
    # Weekly dishes need not have a-la-carte entries. Exact normalized catalogue
    # matches apply availability; never infer new choices or substitute dishes.
    unavailable = {name.strip().casefold() for name, available in (availability or {}).items() if not available}
    contents = [item for item in configured_contents if item.strip().casefold() not in unavailable]
    sabji_options = [item for item in configured_sabjis if item.strip().casefold() not in unavailable]
    chapati_base_available = not ({"3 chapatis", "salad"} & unavailable)
    enabled = bool(row and row.ordering_enabled)
    revision = None
    if row:
        canonical = {"date": now.date().isoformat(), "day": now.strftime("%A"), "mealType": meal_type,
                     "contents": contents, "sabjiOptions": sabji_options, "orderingEnabled": enabled,
                     "configuredContents": configured_contents, "configuredSabjis": configured_sabjis,
                     "chapatiBaseAvailable": chapati_base_available}
        revision = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    reason = None
    configured = False
    if not row or not enabled:
        reason = f"{title} ordering is not configured or is disabled for today"
    else:
        try:
            validate_meal_configuration(configured_contents, configured_sabjis, enabled, meal_type)
        except HTTPException:
            reason = f"Today's {meal_type} configuration is incomplete"
        else:
            configured = True
        if reason is None and not contents:
            reason = f"Today's {meal_type} contents are currently unavailable"
    window = MEAL_WINDOWS[MealType(meal_type)]
    local_time = now.time().replace(tzinfo=None)
    # Menu discovery is independent from ordering permission: students can see
    # today's valid upcoming meals, but cannot order them before service starts.
    # Finished service periods disappear rather than advertising past meals.
    visible = reason is None and local_time < window["cutoff"]
    if reason is None and not window["service_start"] <= local_time < window["cutoff"]:
        reason = title + " is available during " + window["window_str"] + " IST"
    options = []
    for option in MEAL_OPTIONS[meal_type]:
        option_reason = reason
        option_visible = visible
        if option["id"] == f"{meal_type}-chapati-bhaji":
            if not sabji_options:
                option_visible = False
                if option_reason is None:
                    option_reason = f"Today's {meal_type} sabjis are currently unavailable"
            elif not chapati_base_available:
                option_visible = False
                if option_reason is None:
                    option_reason = "Chapati Bhaji requires available chapatis and salad"
        options.append({**option, "visible": option_visible,
                        "available": option_reason is None, "unavailableReason": option_reason})
    return {"date": now.date().isoformat(), "day": now.strftime("%A"), "mealType": meal_type,
            "configured": configured, "visible": any(option["visible"] for option in options),
            "available": any(option["available"] for option in options), "unavailableReason": reason,
            "mealRevision": revision, "contents": contents, "sabjiOptions": sabji_options, "options": options,
            "serviceWindow": window["window_str"],
            "serviceStart": window["service_start"].strftime("%H:%M"),
            "serviceEnd": window["cutoff"].strftime("%H:%M"),
            "currentMealType": determine_current_or_upcoming_meal(local_time)[0].value}


def lunch_state(row, now, availability=None):
    return meal_state(row, now, availability, "lunch")


async def current_meals(db, meal_types, *, lock=False, catalogue=None):
    """Acquire catalogue locks once, then weekly slots in a stable shared order."""
    meal_types = tuple(sorted(set(meal_types)))
    if any(meal not in BUNDLE_MEALS for meal in meal_types):
        raise ValueError("Unsupported bundle meal period")
    now = lunch_now().astimezone(ZoneInfo("Asia/Kolkata"))
    if catalogue is None:
        catalogue_query = select(FoodItem).order_by(FoodItem.id)
        if lock:
            catalogue_query = catalogue_query.with_for_update(read=True).execution_options(populate_existing=True)
        catalogue = (await db.execute(catalogue_query)).scalars().all()
    availability = {}
    for item in catalogue:
        name = item.name.strip().casefold()
        availability[name] = availability.get(name, True) and bool(item.is_available)
    statement = select(WeeklyMenu).where(
        WeeklyMenu.day == now.strftime("%A"), WeeklyMenu.meal_type.in_(meal_types)
    ).order_by(WeeklyMenu.day, WeeklyMenu.meal_type)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    rows = (await db.execute(statement)).scalars().all()
    # Locks may wait across a date/window boundary. Validate against the clock
    # after acquiring them, and do not use yesterday's row for a new day.
    now = lunch_now().astimezone(ZoneInfo("Asia/Kolkata"))
    by_meal = {row.meal_type: row for row in rows if row.day == now.strftime("%A")}
    return {meal: meal_state(by_meal.get(meal), now, availability, meal) for meal in meal_types}


async def current_meal(db, meal_type, *, lock=False):
    return (await current_meals(db, [meal_type], lock=lock))[meal_type]


async def current_lunch(db, *, lock=False):
    return await current_meal(db, "lunch", lock=lock)


async def current_dinner(db, *, lock=False):
    return await current_meal(db, "dinner", lock=lock)


def meal_order_snapshot(request, state):
    meal_type = state["mealType"]
    if not state["available"]:
        raise HTTPException(409, state["unavailableReason"])
    if not request.mealRevision or request.mealRevision != state["mealRevision"]:
        raise HTTPException(409, f"The {meal_type} menu changed; refresh the menu and choose your meal again")
    option_state = next((option for option in state["options"] if option["id"] == request.id), None)
    if option_state is None:
        raise HTTPException(422, "The bundle does not belong to this meal period")
    if not option_state["available"]:
        raise HTTPException(409, option_state["unavailableReason"])
    if request.customizations:
        raise HTTPException(422, f"{meal_type.capitalize()} bundles do not accept paid customizations")
    option = next(option for option in MEAL_OPTIONS[meal_type] if option["id"] == request.id)
    if request.price is not None and Decimal(str(request.price)) != Decimal(option["price"]):
        raise HTTPException(422, f"The {meal_type} bundle price is fixed by the canteen")
    if request.id == f"{meal_type}-chapati-bhaji":
        if request.sabjiChoice not in state["sabjiOptions"]:
            raise HTTPException(422, "Choose exactly one currently available sabji")
        contents = ["3 chapatis", "Salad", request.sabjiChoice]
    else:
        if request.sabjiChoice is not None:
            raise HTTPException(422, "Thali includes the complete meal and does not accept a sabji choice")
        contents = list(state["contents"])
    return {"id": option["id"], "name": option["name"], "qty": request.qty, "price": option["price"],
            "customizations": [], "contents": contents, "mealDate": state["date"], "mealType": meal_type,
            "sabjiChoice": request.sabjiChoice, "mealRevision": state["mealRevision"]}


def lunch_order_snapshot(request, state):
    return meal_order_snapshot(request, state)
