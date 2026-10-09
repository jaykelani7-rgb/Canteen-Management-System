from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import random

from fastapi import Request, APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    create_access_token,
    get_current_student,
    get_optional_student,
    get_password_hash,
    normalize_roll_number,
    verify_password,
)
from config import settings
from database import cache_get, cache_invalidate_prefix, cache_set, get_db
from models import (
    DayOfWeek,
    FeedbackReview,
    FoodItem,
    MealType,
    Notification,
    NotificationRead,
    Order,
    PasswordResetOtp,
    PaymentStatusEnum,
    StudentUser,
    WalletTransaction,
)
from schemas import (
    AuthResponse,
    CanteenQueueStatusResponse,
    CreateOrderRequest,
    FavoritesToggleResponse,
    FeedbackResponse,
    FoodItemResponse,
    ForgotPasscodeRequest,
    MessMealFeedbackCreate,
    NotificationResponse,
    OrderResponse,
    OrderReviewCreate,
    OrderTrackingResponse,
    OtpResponse,
    ResetPasscodeRequest,
    StudentLoginRequest,
    StudentProfileResponse,
    StudentProfileUpdate,
    StudentRegisterRequest,
    TimelineStep,
    WalletBalanceResponse,
    WalletRechargeRequest,
    WalletTransactionResponse,
)

student_router = APIRouter(tags=["Student Services"])


# =========================================================================
# 1. STUDENT AUTHENTICATION & PROFILE
# =========================================================================






@student_router.put(
    "/student/profile",
    response_model=Dict[str, Any],
    summary="Update Student Profile & Preferences",
)
async def update_student_profile(
    payload: StudentProfileUpdate,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Update profile attributes such as branch, phone, email, and dietary preferences."""
    if payload.name:
        student.name = payload.name.strip()
    if payload.branch:
        student.branch = payload.branch.strip()
    if payload.phone:
        student.phone = payload.phone.strip()
    if payload.email:
        student.email = payload.email.strip()
    if payload.dietaryPreference:
        student.dietary_preference = payload.dietaryPreference.lower()

    await db.commit()
    await db.refresh(student)

    return {
        "success": True,
        "message": "Profile updated successfully.",
        "user": student.to_profile_dict(),
    }










# =========================================================================
# 2. FOOD ITEMS CATALOGUE & FAVORITES
# =========================================================================
@student_router.get(
    "/menu/items",
    response_model=List[FoodItemResponse],
    summary="Browse Food Items Catalogue with Search & Category Filters",
)
async def get_food_items(
    category: Optional[str] = Query(None, description="Category filter (Snacks, Meals, Beverages, All)"),
    veg: Optional[bool] = Query(None, description="Filter only vegetarian items"),
    available_only: bool = Query(False, description="Filter only currently available items"),
    query: Optional[str] = Query(None, description="Search query string"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the rich menu catalogue with unit prices, photos, prep time, ratings,
    and customization options. Cached in Redis for high throughput.
    """
    cache_key = f"canteen:food_items:{category}:{veg}:{available_only}:{query}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    stmt = select(FoodItem)
    if category and category.lower() != "all":
        stmt = stmt.where(FoodItem.category.ilike(category.strip()))
    if veg is not None:
        stmt = stmt.where(FoodItem.veg == veg)
    if available_only:
        stmt = stmt.where(FoodItem.is_available == True)
    if query:
        stmt = stmt.where(
            or_(
                FoodItem.name.ilike(f"%{query.strip()}%"),
                FoodItem.desc.ilike(f"%{query.strip()}%"),
            )
        )

    stmt = stmt.order_by(desc(FoodItem.rating), FoodItem.name)
    result = await db.execute(stmt)
    items = [item.to_dict() for item in result.scalars().all()]

    await cache_set(cache_key, items, ttl_seconds=settings.CACHE_TTL_SECONDS)
    return items


@student_router.get(
    "/menu/items/{item_id}",
    response_model=FoodItemResponse,
    summary="Get Single Food Item Detail",
)
async def get_food_item_detail(
    item_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieves full information for a single food item including customization options."""
    stmt = select(FoodItem).where(FoodItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Food item with ID '{item_id}' not found.",
        )

    return item.to_dict()


@student_router.post(
    "/student/favorites/{item_id}",
    response_model=FavoritesToggleResponse,
    summary="Toggle Food Item in Student Favorites",
)
async def toggle_favorite(
    item_id: str,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Add or remove an item from the student's favorites list."""
    favs = list(student.favorites or [])
    is_fav = False
    if item_id in favs:
        favs.remove(item_id)
        is_fav = False
        msg = "Item removed from favorites."
    else:
        favs.append(item_id)
        is_fav = True
        msg = "Item added to favorites."

    student.favorites = favs
    await db.commit()
    await db.refresh(student)

    return FavoritesToggleResponse(
        success=True,
        itemId=item_id,
        isFavorite=is_fav,
        favorites=favs,
        message=msg,
    )


@student_router.get(
    "/student/favorites",
    response_model=List[FoodItemResponse],
    summary="Get Authenticated Student's Favorite Food Items",
)
async def get_student_favorites(
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Returns the food items saved in the student's favorites."""
    fav_ids = student.favorites or []
    if not fav_ids:
        return []

    stmt = select(FoodItem).where(FoodItem.id.in_(fav_ids))
    res = await db.execute(stmt)
    return [item.to_dict() for item in res.scalars().all()]


# =========================================================================
# 3. WALLET & RECHARGE SERVICES
# =========================================================================
@student_router.get(
    "/student/wallet",
    response_model=WalletBalanceResponse,
    summary="Get Student Canteen Wallet Balance & Total Spent",
)
async def get_wallet_balance(
    student: StudentUser = Depends(get_current_student),
):
    """Retrieves current wallet balance, UPI ID, and overall spending."""
    return WalletBalanceResponse(
        walletBalance=student.wallet_balance,
        upiId=student.upi_id or f"{student.roll_number.lower()}@campuspay",
        totalSpent=student.total_spent,
        totalOrders=student.total_orders,
    )


@student_router.post(
    "/student/wallet/recharge",
    response_model=Dict[str, Any],
    summary="Recharge Canteen Wallet with Funds",
)
async def recharge_wallet(payload: WalletRechargeRequest, request: Request, student: StudentUser = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    from financial_service import create_topup
    return await create_topup(db, student.id, payload.amount, request.headers.get("Idempotency-Key", ""))


@student_router.get(
    "/student/wallet/transactions",
    response_model=List[WalletTransactionResponse],
    summary="Get Student Wallet Financial Transaction Ledger",
)
async def get_wallet_transactions(
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Lists all credit and debit financial ledger records for this student."""
    stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.student_id == student.id)
        .order_by(desc(WalletTransaction.created_at))
        .limit(50)
    )
    res = await db.execute(stmt)
    return [t.to_dict() for t in res.scalars().all()]


# =========================================================================
# 4. ORDER PLACEMENT & LIVE ORDER TRACKING
# =========================================================================
@student_router.post(
    "/student/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place a New Canteen Food Order",
)
async def place_order(payload: CreateOrderRequest, idempotency_key: str = Header(..., alias="Idempotency-Key"), student: StudentUser = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    from order_service import create_order
    return await create_order(db, student.id, payload, idempotency_key)


@student_router.get(
    "/student/orders",
    response_model=List[OrderResponse],
    summary="Get Student Order History & Active Orders",
)
async def get_student_orders(filter_type: str = Query("all", pattern="^(active|past|all)$"), limit: int = Query(100, ge=1, le=200), student: StudentUser = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    from order_service import order_response
    stmt=select(Order).where(Order.student_id==student.id)
    if filter_type=="active":
        stmt=stmt.where(Order.order_status.notin_(["Completed","Cancelled"]))
    elif filter_type=="past":
        stmt=stmt.where(Order.order_status.in_(["Completed","Cancelled"]))
    orders=(await db.execute(stmt.order_by(Order.created_at.desc(),Order.id.desc()).limit(limit))).scalars().all()
    return [await order_response(db,order) for order in orders]


@student_router.get(
    "/student/orders/{order_id}",
    response_model=OrderResponse,
    summary="Get Single Order Full Details",
)
async def get_order_detail(order_id:int,student:StudentUser=Depends(get_current_student),db:AsyncSession=Depends(get_db)):
    from order_service import order_response
    order=(await db.execute(select(Order).where(Order.id==order_id,Order.student_id==student.id))).scalar_one_or_none()
    if not order: raise HTTPException(404,"Order not found")
    return await order_response(db,order)


@student_router.get(
    "/student/orders/{order_id}/tracking",
    response_model=OrderTrackingResponse,
    summary="Get Real-Time Live Order Tracking, Queue Position & Countdown",
)
async def get_order_tracking(
    order_id: int,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns real-time dynamic tracking info for an order:
    - Live countdown in seconds and MM:SS format
    - Queue position and orders ahead
    - 6-step timeline state progression (Placed -> Queued -> Preparing -> Ready -> Picked Up -> Completed)
    - Pickup counter and token code
    """
    stmt = select(Order).where(Order.id == order_id, Order.student_id == student.id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{order_id} not found.",
        )

    # Calculate remaining seconds
    now = datetime.now(timezone.utc)
    if order.estimated_ready_at and order.order_status in ["Queued", "Preparing"]:
        ready_at = order.estimated_ready_at
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        delta = (ready_at - now).total_seconds()
        countdown_secs = max(0, int(delta))
    elif order.order_status == "Ready":
        countdown_secs = 0
    else:
        countdown_secs = 0

    mm = str(countdown_secs // 60).zfill(2)
    ss = str(countdown_secs % 60).zfill(2)

    # Compute orders ahead in the queue
    ahead_stmt = select(Order).where(
        Order.order_status.in_(["Queued", "Preparing"]),
        Order.created_at < order.created_at,
    )
    ahead_res = await db.execute(ahead_stmt)
    orders_ahead = len(ahead_res.scalars().all())

    # Build timeline progression
    timeline_def = [
        {"key": "placed", "label": "Placed", "note": "Order received & confirmed"},
        {"key": "queued", "label": "Queued", "note": "You’re in the kitchen line"},
        {"key": "preparing", "label": "Preparing", "note": "Chef is cooking your food"},
        {"key": "ready", "label": "Ready", "note": "Pick up at Counter 2"},
        {"key": "picked", "label": "Picked Up", "note": "Order collected by student"},
        {"key": "completed", "label": "Completed", "note": "Meal enjoyed!"},
    ]

    status_to_idx = {
        "Queued": 1,
        "Preparing": 2,
        "Ready": 3,
        "Picked Up": 4,
        "Completed": 5,
        "Cancelled": -1,
    }
    active_idx = status_to_idx.get(order.order_status, 1)

    timeline_steps: List[TimelineStep] = []
    for i, step in enumerate(timeline_def):
        done = i < active_idx if active_idx >= 0 else False
        active = i == active_idx
        timeline_steps.append(
            TimelineStep(
                key=step["key"],
                label=step["label"],
                note=step["note"],
                done=done,
                active=active,
            )
        )

    # Compute progress percentage
    total_prep_sec = max(60, order.prep_time_minutes * 60)
    progress_pct = 100 if active_idx >= 3 else min(95, max(10, int(((total_prep_sec - countdown_secs) / total_prep_sec) * 100)))

    est_str = (
        order.estimated_ready_at.strftime("%I:%M %p")
        if order.estimated_ready_at
        else "Soon"
    )

    return OrderTrackingResponse(
        orderNumber=order.order_number,
        status=order.order_status,
        queuePosition=max(1, orders_ahead + 1),
        ordersAhead=orders_ahead,
        countdownSeconds=countdown_secs,
        countdownMinutesFormatted=f"{mm}:{ss}",
        estimatedReadyTime=est_str,
        progressPercent=progress_pct,
        pickupCounter=order.pickup_counter,
        pickupToken=order.pickup_token or order.order_number.replace("#", ""),
        timeline=timeline_steps,
        activeStepIndex=max(0, active_idx),
        items=order.items_json or [],
        totalAmount=order.total_amount,
        paymentStatus=order.payment_status,
    )


@student_router.post(
    "/student/orders/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel Order with Automatic Wallet Refund",
)
async def cancel_order(order_id: int, reason: str = Query("Student requested cancellation", max_length=255), student: StudentUser = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    from order_service import change_status
    return await change_status(db, order_id, "Cancelled", reason, student.id)


@student_router.post(
    "/student/orders/{order_id}/pickup",
    response_model=OrderResponse,
    summary="Mark Order as Picked Up / Completed",
)
async def mark_order_picked_up(order_id: int, student: StudentUser = Depends(get_current_student), db: AsyncSession = Depends(get_db)):
    from order_service import change_status
    return await change_status(db, order_id, "Picked Up", student_id=student.id)


@student_router.get(
    "/student/canteen/queue-status",
    response_model=CanteenQueueStatusResponse,
    summary="Get Real-Time Canteen Queue Load & Wait Time Estimate",
)
async def get_canteen_queue_status(db: AsyncSession = Depends(get_db)):
    """Returns active orders count, current rush level, and estimated wait time."""
    queued_stmt = select(Order).where(Order.order_status == "Queued")
    prep_stmt = select(Order).where(Order.order_status == "Preparing")

    res_q = await db.execute(queued_stmt)
    res_p = await db.execute(prep_stmt)

    q_count = len(res_q.scalars().all())
    p_count = len(res_p.scalars().all())
    active_count = q_count + p_count

    rush_level = "Low" if active_count <= 4 else ("Moderate" if active_count <= 10 else "High Rush")
    est_wait = max(4, 3 + active_count * 2)

    return CanteenQueueStatusResponse(
        activeOrdersCount=active_count,
        queuedOrdersCount=q_count,
        preparingOrdersCount=p_count,
        averagePrepMinutes=7,
        currentRushLevel=rush_level,
        estimatedWaitMinutes=est_wait,
        counterOpen=True,
        activeCounterName="Counter 2 (Main Block)",
    )


# =========================================================================
# 5. NOTIFICATIONS & ALERTS
# =========================================================================
@student_router.get(
    "/student/notifications",
    response_model=List[NotificationResponse],
    summary="Get Student Notifications & Canteen Announcements",
)
async def get_student_notifications(student:StudentUser=Depends(get_current_student),db:AsyncSession=Depends(get_db)):
    stmt=select(Notification,NotificationRead.id).outerjoin(NotificationRead,(NotificationRead.notification_id==Notification.id)&(NotificationRead.student_id==student.id)).where(or_(Notification.student_id==student.id,Notification.student_id.is_(None))).order_by(Notification.created_at.desc()).limit(50)
    rows=(await db.execute(stmt)).all()
    return [{**note.to_dict(),"unread":not bool(receipt or (note.student_id==student.id and note.is_read))} for note,receipt in rows]


@student_router.post(
    "/student/notifications/{notification_id}/read",
    summary="Mark a Single Notification as Read",
)
async def mark_notification_read(notification_id:int,student:StudentUser=Depends(get_current_student),db:AsyncSession=Depends(get_db)):
    note=(await db.execute(select(Notification).where(Notification.id==notification_id,or_(Notification.student_id==student.id,Notification.student_id.is_(None))))).scalar_one_or_none()
    if not note: raise HTTPException(404,"Notification not found")
    await save_notification_receipts(db,student.id,[notification_id])
    return {"success":True,"message":"Notification marked as read."}


@student_router.post(
    "/student/notifications/mark-all-read",
    summary="Mark All Notifications as Read",
)
async def mark_all_notifications_read(student:StudentUser=Depends(get_current_student),db:AsyncSession=Depends(get_db)):
    ids=(await db.execute(select(Notification.id).where(or_(Notification.student_id==student.id,Notification.student_id.is_(None))))).scalars().all()
    await save_notification_receipts(db,student.id,ids)
    return {"success":True,"message":"All notifications marked as read."}


# =========================================================================
# 6. REVIEWS & FEEDBACK
# =========================================================================
@student_router.post(
    "/student/orders/{order_id}/review",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Review & Star Rating for a Completed Order",
)
async def submit_order_review(
    order_id: int,
    payload: OrderReviewCreate,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Submits star rating (1-5), optional comments, and tags for a food order."""
    stmt = select(Order).where(Order.id == order_id, Order.student_id == student.id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{order_id} not found.",
        )

    if order.order_status not in {"Picked Up","Completed"}:
        raise HTTPException(409,"Only collected orders can be reviewed")
    review = FeedbackReview(
        student_id=student.id,
        order_id=order.id,
        feedback_type="order",
        rating=payload.rating,
        comment=payload.comment,
        tags=payload.tags or ["Hot & Fresh", "Fast Service"],
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    return review.to_dict()


@student_router.post(
    "/student/feedback/meal",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Daily Mess Meal Feedback",
)
async def submit_mess_meal_feedback(
    payload: MessMealFeedbackCreate,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Submits feedback for scheduled mess meals (breakfast, lunch, snacks, dinner)."""
    feedback = FeedbackReview(
        student_id=student.id,
        feedback_type="mess_meal",
        meal_day=payload.mealDay,
        meal_type=payload.mealType,
        rating=payload.rating,
        comment=payload.comment,
        tags=payload.tags or ["Tasty", "Well Cooked"],
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return feedback.to_dict()


@student_router.get(
    "/student/reviews",
    response_model=List[FeedbackResponse],
    summary="Get Authenticated Student's Submitted Reviews",
)
async def get_student_reviews(
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Lists all feedback and reviews submitted by this student."""
    stmt = (
        select(FeedbackReview)
        .where(FeedbackReview.student_id == student.id)
        .order_by(desc(FeedbackReview.created_at))
    )
    res = await db.execute(stmt)
    return [r.to_dict() for r in res.scalars().all()]


async def save_notification_receipts(db,student_id,ids):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if db.bind.dialect.name=="postgresql" else sqlite_insert
    for notification_id in ids:
        await db.execute(insert(NotificationRead).values(student_id=student_id,notification_id=notification_id).on_conflict_do_nothing(index_elements=["student_id","notification_id"]))
    await db.commit()
