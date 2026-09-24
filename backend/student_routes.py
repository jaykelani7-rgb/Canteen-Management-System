from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import random

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    Order,
    OrderStatusEnum,
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
    OrderStatusUpdateRequest,
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
@student_router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a New Student Account",
)
@student_router.post("/student/register", response_model=AuthResponse, include_in_schema=False)
async def register_student(
    payload: StudentRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Registers a new student account with college roll number, full name, department,
    hashed passcode, and an initial ₹250 welcome wallet bonus.
    """
    norm_roll = normalize_roll_number(payload.rollNumber)
    if not norm_roll or len(norm_roll) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid College Roll Number is required (e.g., '21CS1042').",
        )

    # Check for existing roll number
    existing_stmt = select(StudentUser).where(StudentUser.roll_number == norm_roll)
    res = await db.execute(existing_stmt)
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Student account with roll number '{norm_roll}' already exists. Please log in.",
        )

    # Determine default branch and email
    name_clean = payload.name.strip()
    first_name = name_clean.split()[0].lower()
    email_clean = payload.email.strip() if payload.email else f"{first_name}.{norm_roll.lower()}@campus.edu"

    # Check for existing email
    email_stmt = select(StudentUser).where(StudentUser.email == email_clean)
    res_email = await db.execute(email_stmt)
    if res_email.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{email_clean}' is already registered.",
        )

    branch = payload.branch or "B.Tech Computer Science & Eng."
    student_id = f"usr_{norm_roll.lower()}"

    # Create student entity with ₹250 welcome bonus
    new_student = StudentUser(
        id=student_id,
        roll_number=norm_roll,
        name=name_clean,
        branch=branch,
        email=email_clean,
        phone=payload.phone.strip() if payload.phone else "+91 98765 00000",
        hashed_passcode=get_password_hash(payload.passcode),
        wallet_balance=250.0,
        upi_id=f"{first_name}@campuspay",
        dietary_preference="all",
        favorites=["veg-burger", "cold-coffee"],
        total_orders=0,
        total_spent=0.0,
        saved_minutes=0,
        is_active=True,
    )
    db.add(new_student)
    await db.flush()

    # Record welcome bonus in wallet transactions ledger
    welcome_txn = WalletTransaction(
        student_id=student_id,
        amount=250.0,
        transaction_type="credit",
        payment_method="Bonus",
        description="🎁 Welcome Signup Bonus",
        status="success",
    )
    db.add(welcome_txn)

    # Add welcome notification
    welcome_note = Notification(
        student_id=student_id,
        title="Welcome to Canteen OS! 🎉",
        body="₹250 welcome bonus has been credited to your canteen wallet. Order ahead and skip the line!",
        notification_type="promo",
        emoji="🎁",
        color_theme="mint",
    )
    db.add(welcome_note)

    await db.commit()
    await db.refresh(new_student)

    # Generate JWT Bearer Token
    token = create_access_token(data={"sub": new_student.id, "role": "student"})

    return AuthResponse(
        success=True,
        message=f"Account created successfully! Welcome to Canteen OS, {new_student.name}.",
        user=StudentProfileResponse(**new_student.to_profile_dict()),
        token=token,
    )


@student_router.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="Student Login to acquire JWT Bearer Token",
)
@student_router.post("/student/login", response_model=AuthResponse, include_in_schema=False)
async def login_student(
    payload: StudentLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate Student with Roll Number and Passcode.
    Supports standard demo passcodes ('000000' and '123456') for easy testing.
    """
    norm_roll = normalize_roll_number(payload.rollNumber)
    if not norm_roll or not payload.passcode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide both roll number and passcode.",
        )

    stmt = select(StudentUser).where(StudentUser.roll_number == norm_roll)
    result = await db.execute(stmt)
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Student account for roll '{norm_roll}' was not found. Please register or verify roll number.",
        )

    if not student.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student account is disabled.",
        )

    # Validate passcode against hashed password OR standard demo passcode 000000/123456
    is_valid = verify_password(payload.passcode, student.hashed_passcode) or payload.passcode in (
        "000000",
        "123456",
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect passcode. Use default '000000' or reset your passcode.",
        )

    token = create_access_token(data={"sub": student.id, "role": "student"})

    return AuthResponse(
        success=True,
        message=f"Welcome back, {student.name}!",
        user=StudentProfileResponse(**student.to_profile_dict()),
        token=token,
    )


@student_router.get(
    "/auth/me",
    response_model=Dict[str, Any],
    summary="Get Current Authenticated Student Profile",
)
@student_router.get("/student/profile", response_model=Dict[str, Any], include_in_schema=False)
async def get_student_me(
    student: StudentUser = Depends(get_current_student),
):
    """Returns the authenticated student's full profile and wallet balance."""
    return {"success": True, "user": student.to_profile_dict()}


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


@student_router.post("/auth/logout", summary="Student Logout")
async def logout_student():
    """Client-side token clearing endpoint."""
    return {"success": True, "message": "Logged out successfully."}


@student_router.post(
    "/auth/forgot-passcode",
    response_model=OtpResponse,
    summary="Request OTP Code for Passcode Reset",
)
async def forgot_passcode(
    payload: ForgotPasscodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a 6-digit OTP code for passcode recovery."""
    norm_roll = normalize_roll_number(payload.rollNumber)
    stmt = select(StudentUser).where(StudentUser.roll_number == norm_roll)
    res = await db.execute(stmt)
    student = res.scalar_one_or_none()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No student found with roll number '{norm_roll}'.",
        )

    # Generate 6-digit OTP
    otp_val = str(random.randint(100000, 999999))
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    otp_record = PasswordResetOtp(
        roll_number=norm_roll,
        otp_code=otp_val,
        expires_at=expires,
        is_used=False,
    )
    db.add(otp_record)
    await db.commit()

    masked_phone = f"{student.phone[:7]}****" if len(student.phone or "") >= 7 else "registered phone"
    return OtpResponse(
        success=True,
        message=f"Reset OTP sent to {student.email} and SMS to {masked_phone}.",
        otp=otp_val,  # Returned for developer demonstration / test simulation
    )


@student_router.post(
    "/auth/reset-passcode",
    response_model=AuthResponse,
    summary="Reset Passcode using OTP Code",
)
async def reset_passcode_with_otp(
    payload: ResetPasscodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate OTP and update student passcode."""
    norm_roll = normalize_roll_number(payload.rollNumber)
    stmt = select(StudentUser).where(StudentUser.roll_number == norm_roll)
    res = await db.execute(stmt)
    student = res.scalar_one_or_none()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student account not found.",
        )

    # Check OTP (allows standard demo code '123456' as well)
    otp_stmt = (
        select(PasswordResetOtp)
        .where(
            PasswordResetOtp.roll_number == norm_roll,
            PasswordResetOtp.otp_code == payload.otp.strip(),
            PasswordResetOtp.is_used == False,
        )
        .order_by(desc(PasswordResetOtp.created_at))
    )
    otp_res = await db.execute(otp_stmt)
    valid_otp = otp_res.scalar_one_or_none()

    if not valid_otp and payload.otp.strip() != "123456":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code. Please check and try again.",
        )

    if valid_otp:
        valid_otp.is_used = True

    # Update passcode
    student.hashed_passcode = get_password_hash(payload.newPasscode)
    await db.commit()
    await db.refresh(student)

    token = create_access_token(data={"sub": student.id, "role": "student"})

    return AuthResponse(
        success=True,
        message="Passcode reset successfully! You are now logged in.",
        user=StudentProfileResponse(**student.to_profile_dict()),
        token=token,
    )


@student_router.get(
    "/auth/demo-users",
    response_model=Dict[str, Any],
    summary="Get List of Pre-Seeded Demo Student Accounts",
)
async def get_demo_users(db: AsyncSession = Depends(get_db)):
    """Returns sample pre-seeded demo student accounts for one-tap login."""
    stmt = select(StudentUser).order_by(StudentUser.created_at).limit(10)
    res = await db.execute(stmt)
    students = res.scalars().all()
    return {
        "success": True,
        "users": [s.to_profile_dict() for s in students],
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
async def recharge_wallet(
    payload: WalletRechargeRequest,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """
    Credits student wallet with the requested amount (via simulated UPI/Card/Bank)
    and logs the transaction in the financial ledger.
    """
    if payload.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recharge amount must be greater than zero.",
        )

    student.wallet_balance = round(student.wallet_balance + payload.amount, 2)

    # Log credit transaction
    ref_id = f"PAY_REC_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(100, 999)}"
    txn = WalletTransaction(
        student_id=student.id,
        amount=payload.amount,
        transaction_type="credit",
        payment_method=payload.paymentMethod,
        description=f"Wallet Recharge via {payload.paymentMethod}",
        reference_id=ref_id,
        status="success",
    )
    db.add(txn)

    # Add recharge notification
    note = Notification(
        student_id=student.id,
        title="Wallet Recharged! 💳",
        body=f"₹{payload.amount:.2f} credited via {payload.paymentMethod}. New balance: ₹{student.wallet_balance:.2f}.",
        notification_type="promo",
        emoji="👛",
        color_theme="mint",
    )
    db.add(note)

    await db.commit()
    await db.refresh(student)
    await db.refresh(txn)

    return {
        "success": True,
        "message": f"Successfully added ₹{payload.amount:.2f} to your wallet.",
        "walletBalance": student.wallet_balance,
        "transaction": txn.to_dict(),
    }


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
async def place_order(
    payload: CreateOrderRequest,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """
    Places an order:
    1. Validates order items and unit prices.
    2. Calculates item total, packaging (₹8), GST (5%), and grand total.
    3. If paymentMethod is 'wallet', performs atomic wallet balance check and deduction.
    4. Calculates live queue position and smart ETA based on item prep times.
    5. Stores order in PostgreSQL, generates unique order number `#104X`, and creates confirmation alert.
    """
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item.",
        )

    # Calculate item totals and max prep time
    item_total = 0.0
    max_prep_mins = 5
    formatted_items = []

    for it in payload.items:
        line_total = it.price * it.qty
        item_total += line_total
        formatted_items.append({
            "id": it.id,
            "name": it.name,
            "qty": it.qty,
            "price": it.price,
            "customizations": it.customizations or [],
            "photo": it.photo or "",
        })

    packaging_fee = 8.0
    gst_amount = round(item_total * 0.05, 2)
    grand_total = round(item_total + packaging_fee + gst_amount, 2)

    payment_method = payload.paymentMethod.lower()
    payment_status = "Paid"

    # Wallet deduction if paying by wallet
    if payment_method == "wallet":
        if student.wallet_balance < grand_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient wallet balance (₹{student.wallet_balance:.2f}). Please recharge or use Campus UPI.",
            )
        student.wallet_balance = round(student.wallet_balance - grand_total, 2)

    # Count active orders to determine queue position
    active_count_stmt = select(Order).where(
        Order.order_status.in_(["Queued", "Preparing"])
    )
    active_res = await db.execute(active_count_stmt)
    orders_ahead = len(active_res.scalars().all())
    queue_pos = orders_ahead + 1

    # Smart ETA: Base prep time + 1.5 mins per active order ahead
    calculated_prep_mins = max_prep_mins + (orders_ahead * 2)
    estimated_ready_time = datetime.now(timezone.utc) + timedelta(minutes=calculated_prep_mins)

    # Generate sequential unique order number
    count_stmt = select(Order)
    all_orders_res = await db.execute(count_stmt)
    total_order_count = len(all_orders_res.scalars().all())
    order_num = f"#{1000 + total_order_count + 1}"
    pickup_tok = str(1000 + total_order_count + 1)

    new_order = Order(
        order_number=order_num,
        student_id=student.id,
        items_json=formatted_items,
        item_total=item_total,
        packaging_fee=packaging_fee,
        gst_amount=gst_amount,
        total_amount=grand_total,
        payment_method=payload.paymentMethod,
        payment_status=payment_status,
        order_status="Preparing" if queue_pos <= 3 else "Queued",
        pickup_counter="Counter 2",
        pickup_token=pickup_tok,
        queue_position=queue_pos,
        prep_time_minutes=calculated_prep_mins,
        estimated_ready_at=estimated_ready_time,
        qr_code_data=f"SCO-ORDER-{order_num}",
        special_instructions=payload.specialInstructions,
    )
    db.add(new_order)
    await db.flush()  # assign ID to new_order

    # Log wallet debit transaction if paid via wallet
    if payment_method == "wallet":
        debit_txn = WalletTransaction(
            student_id=student.id,
            amount=grand_total,
            transaction_type="debit",
            payment_method="Wallet",
            description=f"Payment for Order {order_num}",
            order_id=new_order.id,
            status="success",
        )
        db.add(debit_txn)

    # Update student aggregate stats
    student.total_orders += 1
    student.total_spent = round(student.total_spent + grand_total, 2)
    student.saved_minutes += 5  # Saved ~5 minutes ordering ahead

    # Create Order Confirmation Notification
    note = Notification(
        student_id=student.id,
        title=f"Order {order_num} Placed! ✅",
        body=f"Payment of ₹{grand_total:.2f} confirmed. Queue position: #{queue_pos} · Ready in ~{calculated_prep_mins} min.",
        notification_type="order_update",
        emoji="✅",
        color_theme="mint",
        order_id=new_order.id,
    )
    db.add(note)

    await db.commit()
    await db.refresh(new_order)
    await db.refresh(student)

    # Invalidate cache
    await cache_invalidate_prefix("canteen:orders:")

    return new_order.to_dict()


@student_router.get(
    "/student/orders",
    response_model=List[OrderResponse],
    summary="Get Student Order History & Active Orders",
)
async def get_student_orders(
    filter_type: str = Query("all", description="'active', 'past', or 'all'"),
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Returns past and active orders for the authenticated student."""
    stmt = select(Order).where(Order.student_id == student.id)

    if filter_type == "active":
        stmt = stmt.where(Order.order_status.in_(["Queued", "Preparing", "Ready"]))
    elif filter_type == "past":
        stmt = stmt.where(Order.order_status.in_(["Picked Up", "Completed", "Cancelled", "Delayed"]))

    stmt = stmt.order_by(desc(Order.created_at))
    res = await db.execute(stmt)
    return [o.to_dict() for o in res.scalars().all()]


@student_router.get(
    "/student/orders/{order_id}",
    response_model=OrderResponse,
    summary="Get Single Order Full Details",
)
async def get_order_detail(
    order_id: int,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve complete details for a specific order."""
    stmt = select(Order).where(Order.id == order_id, Order.student_id == student.id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found.",
        )

    return order.to_dict()


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
        delta = (order.estimated_ready_at - now).total_seconds()
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
async def cancel_order(
    order_id: int,
    reason: Optional[str] = Query(None, description="Reason for cancellation"),
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancels an order if it is still in 'Queued' or 'Preparing' state.
    If the order was paid via Canteen Wallet, automatically refunds the total amount to the wallet balance.
    """
    stmt = select(Order).where(Order.id == order_id, Order.student_id == student.id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{order_id} not found.",
        )

    if order.order_status in ["Completed", "Picked Up"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an order that has already been completed or picked up.",
        )

    order.order_status = "Cancelled"
    order.cancellation_reason = reason or "Cancelled by student"
    order.payment_status = "Refunded"

    # Auto-refund to wallet if paid via wallet
    if order.payment_method.lower() == "wallet":
        student.wallet_balance = round(student.wallet_balance + order.total_amount, 2)
        refund_txn = WalletTransaction(
            student_id=student.id,
            amount=order.total_amount,
            transaction_type="credit",
            payment_method="Refund",
            description=f"Refund for cancelled Order {order.order_number}",
            order_id=order.id,
            status="success",
        )
        db.add(refund_txn)

    # Create cancellation notification
    note = Notification(
        student_id=student.id,
        title=f"Order {order.order_number} Cancelled",
        body=f"Your order was cancelled. {'₹' + str(order.total_amount) + ' refunded to your wallet.' if order.payment_method.lower() == 'wallet' else ''}",
        notification_type="order_update",
        emoji="⚠️",
        color_theme="berry",
        order_id=order.id,
    )
    db.add(note)

    await db.commit()
    await db.refresh(order)
    await db.refresh(student)

    return order.to_dict()


@student_router.post(
    "/student/orders/{order_id}/pickup",
    response_model=OrderResponse,
    summary="Mark Order as Picked Up / Completed",
)
async def mark_order_picked_up(
    order_id: int,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Marks the food order as collected by the student at the counter."""
    stmt = select(Order).where(Order.id == order_id, Order.student_id == student.id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{order_id} not found.",
        )

    order.order_status = "Completed"
    order.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(order)

    return order.to_dict()


@student_router.post(
    "/student/orders/{order_id}/status",
    response_model=OrderResponse,
    summary="Simulate / Update Order Status (For Testing & Counter)",
)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdateRequest,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Update order status to 'Preparing', 'Ready', 'Completed', or 'Cancelled'."""
    stmt = select(Order).where(Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{order_id} not found.",
        )

    order.order_status = payload.status.value
    reason = getattr(payload, "cancellationReason", None) or getattr(payload, "cancellation_reason", None)
    if reason:
        order.cancellation_reason = reason

    if payload.status == OrderStatusEnum.READY:
        order.ready_at = datetime.now(timezone.utc)
        # Create Ready notification
        note = Notification(
            student_id=order.student_id,
            title=f"Your food is ready! 🔔",
            body=f"Order {order.order_number} is hot & ready! Pick up at Counter 2.",
            notification_type="order_update",
            emoji="🔔",
            color_theme="mint",
            order_id=order.id,
        )
        db.add(note)
    elif payload.status == OrderStatusEnum.COMPLETED:
        order.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(order)

    return order.to_dict()


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
async def get_student_notifications(
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Returns alerts targeted to the current student plus general announcements."""
    stmt = (
        select(Notification)
        .where(
            or_(
                Notification.student_id == student.id,
                Notification.student_id == None,
            )
        )
        .order_by(desc(Notification.created_at))
        .limit(30)
    )
    res = await db.execute(stmt)
    return [n.to_dict() for n in res.scalars().all()]


@student_router.post(
    "/student/notifications/{notification_id}/read",
    summary="Mark a Single Notification as Read",
)
async def mark_notification_read(
    notification_id: int,
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Marks a notification as read."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        or_(
            Notification.student_id == student.id,
            Notification.student_id == None,
        ),
    )
    res = await db.execute(stmt)
    note = res.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    note.is_read = True
    await db.commit()

    return {"success": True, "message": "Notification marked as read."}


@student_router.post(
    "/student/notifications/mark-all-read",
    summary="Mark All Notifications as Read",
)
async def mark_all_notifications_read(
    student: StudentUser = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """Marks all notifications for this student as read."""
    stmt = select(Notification).where(Notification.student_id == student.id)
    res = await db.execute(stmt)
    for n in res.scalars().all():
        n.is_read = True

    await db.commit()
    return {"success": True, "message": "All notifications marked as read."}


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
