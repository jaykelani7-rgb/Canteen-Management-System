from datetime import datetime, time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    create_access_token,
    get_current_admin,
    get_password_hash,
    verify_password,
)
from config import settings
from database import (
    cache_get,
    cache_invalidate_prefix,
    cache_set,
    get_db,
)
from models import AdminUser, AlaCarte, DayOfWeek, MealType, WeeklyMenu
from schemas import (
    AdminLoginRequest,
    AdminUserResponse,
    AlaCarteCreate,
    AlaCarteResponse,
    AlaCarteUpdate,
    RelevantMealDetails,
    TodayMenuResponse,
    Token,
    WeeklyMenuBatchUpload,
    WeeklyMenuItemCreate,
    WeeklyMenuItemResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
menu_router = APIRouter(prefix="/menu", tags=["Student Menu (Cached)"])
admin_router = APIRouter(prefix="/admin", tags=["Admin Management (Protected)"])


# =========================================================================
# HELPER FUNCTIONS: Time Windows & Timing Evaluation
# =========================================================================
MEAL_WINDOWS = {
    MealType.BREAKFAST: {
        "start": time(7, 0),
        "service_start": time(7, 30),
        "cutoff": time(10, 30),
        "window_str": "07:30-10:30",
    },
    MealType.LUNCH: {
        "start": time(11, 30),
        "service_start": time(12, 0),
        "cutoff": time(15, 0),
        "window_str": "12:00-15:00",
    },
    MealType.SNACKS: {
        "start": time(16, 0),
        "service_start": time(16, 30),
        "cutoff": time(18, 30),
        "window_str": "16:30-18:30",
    },
    MealType.DINNER: {
        "start": time(19, 0),
        "service_start": time(19, 30),
        "cutoff": time(22, 30),
        "window_str": "19:30-22:30",
    },
}

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def determine_current_or_upcoming_meal(current_time: time) -> tuple[MealType, str, str, bool]:
    """
    Evaluates current time against meal service schedules.
    Returns: (meal_type, status, window_str, is_next_day)
    """
    if current_time < MEAL_WINDOWS[MealType.BREAKFAST]["cutoff"]:
        meal = MealType.BREAKFAST
        status = "active" if current_time >= MEAL_WINDOWS[meal]["service_start"] else "upcoming"
        return meal, status, MEAL_WINDOWS[meal]["window_str"], False

    elif current_time < MEAL_WINDOWS[MealType.LUNCH]["cutoff"]:
        meal = MealType.LUNCH
        status = "active" if current_time >= MEAL_WINDOWS[meal]["service_start"] else "upcoming"
        return meal, status, MEAL_WINDOWS[meal]["window_str"], False

    elif current_time < MEAL_WINDOWS[MealType.SNACKS]["cutoff"]:
        meal = MealType.SNACKS
        status = "active" if current_time >= MEAL_WINDOWS[meal]["service_start"] else "upcoming"
        return meal, status, MEAL_WINDOWS[meal]["window_str"], False

    elif current_time < MEAL_WINDOWS[MealType.DINNER]["cutoff"]:
        meal = MealType.DINNER
        status = "active" if current_time >= MEAL_WINDOWS[meal]["service_start"] else "upcoming"
        return meal, status, MEAL_WINDOWS[meal]["window_str"], False

    else:
        # After dinner service cutoff -> Target next day's breakfast
        meal = MealType.BREAKFAST
        return meal, "upcoming", MEAL_WINDOWS[meal]["window_str"], True


def is_time_in_window(current_time: time, window_str: str) -> bool:
    """Check if current time falls within a given timing window (e.g. '12:00-15:00' or 'all_day')."""
    if window_str.lower() in ("all_day", "any", "24x7"):
        return True
    try:
        start_str, end_str = window_str.split("-")
        sh, sm = map(int, start_str.strip().split(":"))
        eh, em = map(int, end_str.strip().split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
        return start_t <= current_time <= end_t
    except Exception:
        # If custom string format fails parsing, default to True
        return True


# =========================================================================
# 1. AUTHENTICATION ROUTES
# =========================================================================
@auth_router.post(
    "/login",
    response_model=Token,
    summary="Admin Login to acquire JWT Bearer Token",
)
async def login(
    login_data: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate Canteen Administrator and generate a signed JWT bearer token.
    """
    stmt = select(AdminUser).where(AdminUser.username == login_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is inactive",
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        role=user.role,
    )


# =========================================================================
# 2. STUDENT / PUBLIC MENU ROUTES (REDIS CACHED)
# =========================================================================
@menu_router.get(
    "/today",
    response_model=TodayMenuResponse,
    summary="Get Today's Relevant / Upcoming Meal Menu (High-Performance Cached)",
)
async def get_today_menu(
    simulated_time: Optional[str] = Query(
        None,
        description="Optional simulation override in 'HH:MM' 24h format (e.g. '12:30') for testing",
    ),
    simulated_day: Optional[DayOfWeek] = Query(
        None,
        description="Optional simulation override for day of the week (e.g. 'Monday')",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    **Dynamic Routing & Performance Caching Endpoint**:
    1. Evaluates current system day of the week and local clock time.
    2. Identifies the exact active or upcoming meal window (Breakfast, Lunch, Snacks, Dinner).
    3. Checks Redis cache to serve high-concurrency requests instantaneously.
    4. On cache miss, queries PostgreSQL, caches the result in Redis with a TTL, and returns.
    """
    now = datetime.now()

    # Determine evaluated day
    current_day = simulated_day.value if simulated_day else now.strftime("%A")

    # Determine evaluated time
    if simulated_time:
        try:
            sh, sm = map(int, simulated_time.split(":"))
            eval_time = time(sh, sm)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid simulated_time format. Use 'HH:MM' (24-hour).",
            )
    else:
        eval_time = now.time()

    meal_type, meal_status, timing_window, is_next_day = determine_current_or_upcoming_meal(
        eval_time
    )

    # If dinner ended, calculate target next day for breakfast
    target_day = current_day
    if is_next_day:
        curr_idx = DAY_ORDER.index(current_day) if current_day in DAY_ORDER else 0
        target_day = DAY_ORDER[(curr_idx + 1) % 7]

    # Generate deterministic Redis cache key
    time_slot_key = f"{eval_time.hour}:{eval_time.minute // 15 * 15:02d}"  # 15-minute time bucket for a la carte freshness
    cache_key = f"canteen:menu:today:{target_day}:{meal_type.value}:{time_slot_key}"

    # 1. Attempt Redis Cache Lookup (for super fast sub-millisecond response)
    cached_data = await cache_get(cache_key)
    if cached_data:
        cached_data["cached"] = True
        return cached_data

    # 2. Database Query on Cache Miss
    # Query specific target upcoming/active meal
    target_meal_stmt = select(WeeklyMenu).where(
        WeeklyMenu.day == target_day, WeeklyMenu.meal_type == meal_type.value
    )
    target_res = await db.execute(target_meal_stmt)
    target_menu_row = target_res.scalar_one_or_none()

    # Query all meals scheduled for today
    today_all_stmt = select(WeeklyMenu).where(WeeklyMenu.day == current_day)
    today_res = await db.execute(today_all_stmt)
    all_today_rows = today_res.scalars().all()

    # Query available A La Carte items
    ala_carte_stmt = select(AlaCarte).where(AlaCarte.is_available == True)
    ala_res = await db.execute(ala_carte_stmt)
    all_ala_carte = ala_res.scalars().all()

    # Filter a la carte items active for the current time
    filtered_ala_carte = [
        item.to_dict()
        for item in all_ala_carte
        if is_time_in_window(eval_time, item.timing_window)
    ]

    target_meal_info = None
    if target_menu_row:
        target_meal_info = {
            "meal_type": target_menu_row.meal_type,
            "status": meal_status,
            "timing_window": timing_window,
            "items": target_menu_row.items or [],
        }
    else:
        target_meal_info = {
            "meal_type": meal_type.value,
            "status": meal_status,
            "timing_window": timing_window,
            "items": ["Menu schedule not uploaded yet for this meal."],
        }

    formatted_all_meals = [row.to_dict() for row in all_today_rows]

    response_payload = {
        "system_day": current_day,
        "system_time": eval_time.strftime("%H:%M:%S"),
        "target_meal": target_meal_info,
        "all_today_meals": formatted_all_meals,
        "available_ala_carte": filtered_ala_carte,
        "cached": False,
        "message": f"Successfully retrieved {'next day ' if is_next_day else ''}{meal_type.value} menu ({meal_status}).",
    }

    # 3. Store result in Redis Cache with TTL
    await cache_set(cache_key, response_payload, ttl_seconds=settings.CACHE_TTL_SECONDS)

    return response_payload


@menu_router.get(
    "/weekly",
    response_model=List[WeeklyMenuItemResponse],
    summary="Get Full Weekly Menu Schedule (Cached)",
)
async def get_weekly_menu(db: AsyncSession = Depends(get_db)):
    """
    Retrieves the complete 7-day weekly menu schedule. Cached in Redis for maximum throughput.
    """
    cache_key = "canteen:menu:weekly"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    stmt = select(WeeklyMenu)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    data = [row.to_dict() for row in rows]

    await cache_set(cache_key, data, ttl_seconds=settings.CACHE_TTL_SECONDS)
    return data


@menu_router.get(
    "/ala-carte",
    response_model=List[AlaCarteResponse],
    summary="Get All Available A La Carte Items",
)
async def get_ala_carte_items(
    available_only: bool = Query(True, description="Filter only available items"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all A La Carte dishes with unit prices and availability.
    """
    cache_key = f"canteen:menu:ala_carte:{available_only}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    stmt = select(AlaCarte)
    if available_only:
        stmt = stmt.where(AlaCarte.is_available == True)

    result = await db.execute(stmt)
    items = [item.to_dict() for item in result.scalars().all()]

    await cache_set(cache_key, items, ttl_seconds=settings.CACHE_TTL_SECONDS)
    return items


# =========================================================================
# 3. ADMIN MANAGEMENT ROUTES (STRICTLY JWT PROTECTED)
# =========================================================================
@admin_router.post(
    "/menu/weekly",
    summary="Upload or Update Weekly Menu Schedule (Admin JWT Protected)",
    status_code=status.HTTP_200_OK,
)
async def upload_weekly_menu(
    payload: WeeklyMenuBatchUpload,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),  # Strict JWT Authentication Middleware
):
    """
    **Admin Protected Endpoint**:
    Strictly protected by JWT authentication middleware.
    Accepts bulk weekly menu schedule items, performs upsert (insert or update on day + meal_type collision),
    and invalidates all relevant Redis caches.
    """
    upserted_count = 0

    for item in payload.schedule:
        # Check if record already exists for this (day, meal_type)
        stmt = select(WeeklyMenu).where(
            WeeklyMenu.day == item.day.value,
            WeeklyMenu.meal_type == item.meal_type.value,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.items = item.items
        else:
            new_entry = WeeklyMenu(
                day=item.day.value,
                meal_type=item.meal_type.value,
                items=item.items,
            )
            db.add(new_entry)
        upserted_count += 1

    await db.commit()

    # Invalidate all daily and weekly menu Redis caches so changes reflect immediately
    cleared_keys = await cache_invalidate_prefix("canteen:menu:")

    return {
        "status": "success",
        "message": f"Successfully updated {upserted_count} weekly menu schedule items.",
        "admin_user": admin.username,
        "cache_invalidated_keys_count": cleared_keys,
    }


@admin_router.post(
    "/ala-carte",
    response_model=AlaCarteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New A La Carte Item (Admin Protected)",
)
async def create_ala_carte_item(
    item: AlaCarteCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Add a new item to the A La Carte menu with unit price and timing window."""
    # Check for duplicate item name
    existing_stmt = select(AlaCarte).where(AlaCarte.item_name == item.item_name)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item '{item.item_name}' already exists in A La Carte menu.",
        )

    new_item = AlaCarte(
        item_name=item.item_name,
        price=item.price,
        timing_window=item.timing_window,
        is_available=item.is_available,
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)

    # Invalidate Redis menu caches
    await cache_invalidate_prefix("canteen:menu:")

    return new_item.to_dict()


@admin_router.put(
    "/ala-carte/{item_id}",
    response_model=AlaCarteResponse,
    summary="Update A La Carte Item (Admin Protected)",
)
async def update_ala_carte_item(
    item_id: int,
    item_update: AlaCarteUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Modify price, timing window, or availability of an A La Carte dish."""
    stmt = select(AlaCarte).where(AlaCarte.id == item_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A La Carte item with ID {item_id} not found.",
        )

    if item_update.item_name is not None:
        item.item_name = item_update.item_name
    if item_update.price is not None:
        item.price = item_update.price
    if item_update.timing_window is not None:
        item.timing_window = item_update.timing_window
    if item_update.is_available is not None:
        item.is_available = item_update.is_available

    await db.commit()
    await db.refresh(item)

    # Invalidate Redis caches
    await cache_invalidate_prefix("canteen:menu:")

    return item.to_dict()


@admin_router.delete(
    "/ala-carte/{item_id}",
    summary="Delete A La Carte Item (Admin Protected)",
)
async def delete_ala_carte_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Remove an item permanently from the A La Carte menu."""
    stmt = select(AlaCarte).where(AlaCarte.id == item_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A La Carte item with ID {item_id} not found.",
        )

    await db.delete(item)
    await db.commit()

    # Invalidate Redis caches
    await cache_invalidate_prefix("canteen:menu:")

    return {"status": "success", "message": f"Item '{item.item_name}' removed."}
