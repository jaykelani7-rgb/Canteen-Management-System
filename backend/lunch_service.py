"""Current IST lunch configuration and server-authoritative bundle snapshots."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from models import FoodItem, MealType, WeeklyMenu

LUNCH_OPTIONS = (
    {"id": "lunch-chapati-bhaji", "name": "Chapati Bhaji", "price": 45},
    {"id": "lunch-thali", "name": "Thali", "price": 80},
)
LUNCH_IDS = frozenset(option["id"] for option in LUNCH_OPTIONS)


def lunch_now():
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def validate_lunch_configuration(items, sabji_options, enabled):
    """Validate the merged configuration, including fields older clients omit."""
    if not enabled:
        return
    if not items or any(not isinstance(item, str) or not item.strip() for item in items):
        raise HTTPException(422, "Enabled lunch requires the complete meal contents")
    if (len(sabji_options) != 2 or any(not isinstance(item, str) or not item.strip() for item in sabji_options)
            or len({item.casefold() for item in sabji_options}) != 2
            or any(item not in items for item in sabji_options)):
        raise HTTPException(422, "Enabled lunch requires exactly two distinct sabji options from the complete meal contents")


def lunch_state(row, now, availability=None):
    from routes import MEAL_WINDOWS
    configured_contents = list(row.items or []) if row else []
    configured_sabjis = list(row.sabji_options or []) if row else []
    # A weekly dish need not have its own a-la-carte catalogue entry. An exact
    # normalized match that is explicitly unavailable does apply to both menus.
    unavailable = {name.strip().casefold() for name, available in (availability or {}).items() if not available}
    contents = [item for item in configured_contents if item.strip().casefold() not in unavailable]
    sabji_options = [item for item in configured_sabjis if item.strip().casefold() not in unavailable]
    chapati_base_available = not ({"3 chapatis", "salad"} & unavailable)
    enabled = bool(row and row.ordering_enabled)
    revision = None
    if row:
        canonical = {"date": now.date().isoformat(), "day": now.strftime("%A"), "mealType": "lunch",
                     "contents": contents, "sabjiOptions": sabji_options, "orderingEnabled": enabled,
                     "configuredContents": configured_contents, "configuredSabjis": configured_sabjis,
                     "chapatiBaseAvailable": chapati_base_available}
        revision = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    reason = None
    if not row or not enabled:
        reason = "Lunch ordering is not configured or is disabled for today"
    else:
        try:
            # The configuration still contains two choices when staff temporarily
            # turn one off. Do not confuse availability with an OCR replacement.
            validate_lunch_configuration(configured_contents, configured_sabjis, enabled)
        except HTTPException:
            reason = "Today's lunch configuration is incomplete"
        if reason is None and (not contents or not sabji_options):
            reason = "Today's lunch sabjis are currently unavailable"
    window = MEAL_WINDOWS[MealType.LUNCH]
    if reason is None and not window["service_start"] <= now.time().replace(tzinfo=None) < window["cutoff"]:
        reason = "Lunch is available during " + window["window_str"] + " IST"
    options = []
    for option in LUNCH_OPTIONS:
        option_reason = reason
        if option_reason is None and option["id"] == "lunch-chapati-bhaji" and not chapati_base_available:
            option_reason = "Chapati Bhaji requires available chapatis and salad"
        options.append({**option, "available": option_reason is None, "unavailableReason": option_reason})
    return {"date": now.date().isoformat(), "day": now.strftime("%A"), "mealType": "lunch",
            "available": reason is None, "unavailableReason": reason, "mealRevision": revision,
            "contents": contents, "sabjiOptions": sabji_options, "options": options}


async def current_lunch(db, *, lock=False):
    now = lunch_now().astimezone(ZoneInfo("Asia/Kolkata"))
    catalogue_query = select(FoodItem).order_by(FoodItem.id)
    if lock:
        # Lock catalogue availability before WeeklyMenu, consistently with the
        # mixed a-la-carte checkout path. Admin toggles take an exclusive lock.
        catalogue_query = catalogue_query.with_for_update(read=True).execution_options(populate_existing=True)
    catalogue = (await db.execute(catalogue_query)).scalars().all()
    availability = {}
    for item in catalogue:
        name = item.name.strip().casefold()
        # Case/space variants must not let an unavailable matching dish through.
        availability[name] = availability.get(name, True) and bool(item.is_available)
    statement = select(WeeklyMenu).where(WeeklyMenu.day == now.strftime("%A"), WeeklyMenu.meal_type == "lunch")
    if lock:
        # Admin menu edits use the same row lock. Snapshot and wallet debit commit together.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = (await db.execute(statement)).scalar_one_or_none()
    # A request can wait on an admin edit; enforce the clock after acquiring its lock.
    now = lunch_now().astimezone(ZoneInfo("Asia/Kolkata"))
    if row and row.day != now.strftime("%A"):
        row = None
    return lunch_state(row, now, availability)


def lunch_order_snapshot(request, state):
    if not state["available"]:
        raise HTTPException(409, state["unavailableReason"])
    if not request.mealRevision or request.mealRevision != state["mealRevision"]:
        raise HTTPException(409, "The lunch menu changed; refresh the menu and choose your meal again")
    option_state = next((option for option in state["options"] if option["id"] == request.id), None)
    if option_state and not option_state["available"]:
        raise HTTPException(409, option_state["unavailableReason"])
    if request.customizations:
        raise HTTPException(422, "Lunch bundles do not accept paid customizations")
    option = next(option for option in LUNCH_OPTIONS if option["id"] == request.id)
    if request.price is not None and Decimal(str(request.price)) != Decimal(option["price"]):
        raise HTTPException(422, "The lunch bundle price is fixed by the canteen")
    if request.id == "lunch-chapati-bhaji":
        if request.sabjiChoice not in state["sabjiOptions"]:
            raise HTTPException(422, "Choose exactly one currently available sabji")
        contents = ["3 chapatis", "Salad", request.sabjiChoice]
    else:
        if request.sabjiChoice is not None:
            raise HTTPException(422, "Thali includes the complete meal and does not accept a sabji choice")
        contents = list(state["contents"])
    return {"id": option["id"], "name": option["name"], "qty": request.qty, "price": option["price"],
            "customizations": [], "contents": contents, "mealDate": state["date"], "mealType": "lunch",
            "sabjiChoice": request.sabjiChoice, "mealRevision": state["mealRevision"]}
