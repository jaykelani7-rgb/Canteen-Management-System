import enum
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Numeric,
    CheckConstraint,
    Index,
    text,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import JSON, TypeDecorator
from database import Base

# Reserve order numbers independently of database primary keys and legacy seeds.
order_number_sequence = Sequence("canteen_order_number_seq", start=1001, metadata=Base.metadata)


class DayOfWeek(str, enum.Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


class MealType(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    SNACKS = "snacks"
    DINNER = "dinner"


class OrderStatusEnum(str, enum.Enum):
    PAYMENT_PENDING = "Payment Pending"
    QUEUED = "Queued"
    PREPARING = "Preparing"
    READY = "Ready"
    PICKED_UP = "Picked Up"
    COMPLETED = "Completed"
    DELAYED = "Delayed"
    CANCELLED = "Cancelled"


class PaymentStatusEnum(str, enum.Enum):
    PAID = "Paid"
    FAILED = "Failed"
    REFUNDED = "Refunded"
    PENDING = "Pending"


# Cross-database compatible Array/JSON type for items column
class StringListType(TypeDecorator):
    """PostgreSQL ARRAY(String) with JSON fallback for seamless portability."""
    impl = ARRAY(String)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        else:
            return dialect.type_descriptor(JSON)


# =========================================================================
# 1. MESS & CANTEEN CORE MENU TABLES
# =========================================================================
class WeeklyMenu(Base):
    """
    Weekly Menu Table:
    Stores the scheduled rotating mess/canteen menu by day, meal type, and item array.
    """
    __tablename__ = "weekly_menu"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    day = Column(String(20), nullable=False, index=True)  # e.g., 'Monday', 'Tuesday'
    meal_type = Column(String(20), nullable=False, index=True)  # e.g., 'breakfast', 'lunch'
    items = Column(StringListType, nullable=False, default=list)  # Array of string items

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("day", "meal_type", name="uq_weekly_menu_day_meal"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "day": self.day,
            "meal_type": self.meal_type,
            "items": self.items or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlaCarte(Base):
    """
    A La Carte Table:
    Stores on-demand food items, their unit prices, timing windows, and availability.
    """
    __tablename__ = "ala_carte"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_name = Column(String(100), unique=True, nullable=False, index=True)
    price = Column(Numeric(12, 2), nullable=False)
    timing_window = Column(String(50), nullable=False)  # e.g., '08:00-11:00', '12:00-15:00', 'all_day'
    is_available = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("price >= 0 AND price < 10000000000", name="ck_ala_carte_price"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "item_name": self.item_name,
            "price": self.price,
            "timing_window": self.timing_window,
            "is_available": self.is_available,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class FoodItem(Base):
    """
    Food Item Table:
    Rich food catalogue item for student browsing, cart operations, customization, and ordering.
    """
    __tablename__ = "food_items"

    id = Column(String(50), primary_key=True, index=True)  # e.g., 'veg-burger'
    name = Column(String(100), unique=True, nullable=False, index=True)
    desc = Column(String(255), nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    category = Column(String(30), nullable=False, default="Snacks", index=True)  # Snacks, Meals, Beverages
    veg = Column(Boolean, default=True, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    prep_mins = Column(Integer, default=7, nullable=False)
    rating = Column(Float, default=4.5, nullable=False)
    rating_count = Column(Integer, default=1, nullable=False)
    tag = Column(String(50), nullable=True)  # 'Bestseller', "Chef's pick", 'Student fav'
    emoji = Column(String(10), default="🍔", nullable=False)
    photo = Column(String(500), nullable=True)
    calories = Column(Integer, default=300, nullable=False)
    customizations = Column(JSON, default=list)  # [{"name": "Extra cheese", "price": 15}]
    timing_window = Column(String(50), default="all_day", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("price >= 0 AND price < 10000000000", name="ck_food_items_price"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.desc or "",
            "price": self.price,
            "category": self.category,
            "veg": self.veg,
            "available": self.is_available,
            "timingWindow": self.timing_window,
            "prepMins": self.prep_mins,
            "rating": self.rating,
            "ratingCount": self.rating_count,
            "tag": self.tag,
            "emoji": self.emoji,
            "photo": self.photo or "",
            "calories": self.calories,
            "customizations": self.customizations or [],
            "timingWindow": self.timing_window,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================================
# 2. USER TABLES (ADMIN & STUDENTS)
# =========================================================================
class AdminUser(Base):
    """
    Admin User Table:
    Stores canteen administrators authorized to upload and modify menu schedules.
    """
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="admin", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StudentUser(Base):
    """
    Student User Table:
    Stores registered students with college roll numbers, passcodes, wallet balances, and preferences.
    """
    __tablename__ = "students"

    id = Column(String(50), primary_key=True, index=True)  # e.g., 'usr_aarav' or UUID
    roll_number = Column(String(30), unique=True, nullable=False, index=True)  # e.g., '21CS1042'
    name = Column(String(100), nullable=False)
    branch = Column(String(100), nullable=False, default="B.Tech Student")
    email = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    hashed_passcode = Column(String(255), nullable=False)
    wallet_balance = Column(Numeric(12, 2), default=0, server_default=text("0"), nullable=False)  # No unverified signup credit
    upi_id = Column(String(100), nullable=True)
    dietary_preference = Column(String(30), default="all", nullable=False)  # all, veg, non-veg, vegan
    favorites = Column(JSON, default=list)  # array of favorite food item IDs
    total_orders = Column(Integer, default=0, nullable=False)
    total_spent = Column(Numeric(12, 2), default=0, nullable=False)
    saved_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("wallet_balance >= 0 AND wallet_balance < 10000000000 AND total_spent >= 0 AND total_spent < 10000000000", name="ck_students_money"),
    )

    def to_profile_dict(self):
        return {
            "id": self.id,
            "rollNumber": self.roll_number,
            "name": self.name,
            "branch": self.branch,
            "email": self.email,
            "phone": self.phone or "",
            "walletBalance": self.wallet_balance,
            "upiId": self.upi_id or f"{self.roll_number.lower()}@campuspay",
            "dietaryPreference": self.dietary_preference,
            "favorites": self.favorites or [],
            "totalOrders": self.total_orders,
            "totalSpent": self.total_spent,
            "savedMinutes": self.saved_minutes,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================================
# 3. ORDERS & LIVE TRACKING TABLE
# =========================================================================
class Order(Base):
    """
    Order Table:
    Stores customer orders, item breakdown, monetary details, payment info,
    live queue position, ETA calculation, and status progression.
    """
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_number = Column(String(20), unique=True, nullable=False, index=True)  # e.g., '#1042'
    student_id = Column(String(50), ForeignKey("students.id"), nullable=False, index=True)

    items_json = Column(JSON, nullable=False, default=list)  # [{id, name, qty, price, customizations, photo}]
    item_total = Column(Numeric(12, 2), nullable=False)
    packaging_fee = Column(Numeric(12, 2), default=8, nullable=False)
    gst_amount = Column(Numeric(12, 2), default=0, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)

    payment_method = Column(String(30), default="wallet", nullable=False)  # 'wallet', 'upi', 'card', 'cash'
    payment_status = Column(String(20), default="Paid", nullable=False)  # 'Paid', 'Failed', 'Refunded'
    order_status = Column(String(20), default="Queued", nullable=False, index=True)  # 'Queued', 'Preparing', 'Ready', 'Picked Up', 'Completed', 'Cancelled'

    pickup_counter = Column(String(50), default="Counter 2", nullable=False)
    pickup_token = Column(String(20), nullable=True)  # e.g., '1042'
    queue_position = Column(Integer, default=1, nullable=False)
    prep_time_minutes = Column(Integer, default=5, nullable=False)
    estimated_ready_at = Column(DateTime(timezone=True), nullable=True)
    qr_code_data = Column(String(255), nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    special_instructions = Column(String(255), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    request_fingerprint = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    ready_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("item_total >= 0 AND packaging_fee >= 0 AND gst_amount >= 0 AND total_amount >= 0 AND total_amount < 10000000000", name="ck_orders_money"),
        UniqueConstraint("student_id", "idempotency_key", name="uq_orders_student_idempotency"),
    )

    def to_dict(self):
        return {
            "id": f"ord_{self.id}",
            "orderId": self.id,
            "number": self.order_number,
            "studentId": self.student_id,
            "items": self.items_json or [],
            "itemTotal": self.item_total,
            "packagingFee": self.packaging_fee,
            "gst": self.gst_amount,
            "total": self.total_amount,
            "paymentMethod": self.payment_method,
            "payment": self.payment_status,
            "status": self.order_status,
            "pickupCounter": self.pickup_counter,
            "pickupToken": self.pickup_token or self.order_number.replace("#", ""),
            "queuePosition": self.queue_position,
            "prepTimeMinutes": self.prep_time_minutes,
            "estimatedReadyAt": self.estimated_ready_at.isoformat() if self.estimated_ready_at else None,
            "qrCodeData": self.qr_code_data or f"SCO-ORDER-{self.order_number}",
            "cancellationReason": self.cancellation_reason,
            "specialInstructions": self.special_instructions,
            "date": self.created_at.strftime("%d %b · %I:%M %p") if self.created_at else "Just now",
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "readyAt": self.ready_at.isoformat() if self.ready_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }


# =========================================================================
# 4. WALLET TRANSACTIONS LEDGER
# =========================================================================
class WalletTransaction(Base):
    """
    Wallet Transaction Table:
    Double-entry style financial ledger recording credits, debits, recharges, and refunds.
    """
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    transaction_type = Column(String(20), nullable=False)  # 'credit', 'debit'
    payment_method = Column(String(30), default="UPI", nullable=False)  # 'UPI', 'Card', 'Wallet', 'Bonus'
    description = Column(String(255), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    reference_id = Column(String(100), nullable=True)
    payment_intent_id = Column(Integer, ForeignKey("payment_intents.id"), nullable=True)
    status = Column(String(20), default="success", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount >= 0 AND amount < 10000000000", name="ck_wallet_transactions_amount"),
        Index("uq_wallet_payment_success", "student_id", "payment_intent_id", "transaction_type", unique=True,
              postgresql_where=text("payment_intent_id IS NOT NULL AND status = 'success'"),
              sqlite_where=text("payment_intent_id IS NOT NULL AND status = 'success'")),
        Index("uq_wallet_order_success", "student_id", "order_id", "transaction_type", unique=True,
              postgresql_where=text("order_id IS NOT NULL AND status = 'success'"),
              sqlite_where=text("order_id IS NOT NULL AND status = 'success'")),
    )

    def to_dict(self):
        return {
            "id": f"txn_{self.id}",
            "studentId": self.student_id,
            "amount": self.amount,
            "type": self.transaction_type,
            "paymentMethod": self.payment_method,
            "description": self.description,
            "orderId": self.order_id,
            "referenceId": self.reference_id,
            "status": self.status,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "dateFormatted": self.created_at.strftime("%d %b · %I:%M %p") if self.created_at else "",
        }


# =========================================================================
# 5. NOTIFICATIONS TABLE
# =========================================================================
class Notification(Base):
    """
    Notification Table:
    Stores targeted student notifications (order ready, in-prep, promos, stock updates)
    as well as general canteen announcements.
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=True, index=True)  # None = broadcast to all
    title = Column(String(100), nullable=False)
    body = Column(String(255), nullable=False)
    notification_type = Column(String(30), default="order_update", nullable=False)  # 'order_update', 'promo', 'stock_alert', 'system'
    emoji = Column(String(10), default="🔔", nullable=False)
    color_theme = Column(String(20), default="mint", nullable=False)  # mint, tangerine, slate, amber, berry
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "studentId": self.student_id,
            "title": self.title,
            "subtitle": self.body,
            "type": self.notification_type,
            "emoji": self.emoji,
            "color": self.color_theme,
            "orderId": self.order_id,
            "unread": not self.is_read,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "time": self.created_at.strftime("%I:%M %p") if self.created_at else "Just now",
        }


# =========================================================================
# 6. FEEDBACK & REVIEWS TABLE
# =========================================================================
class FeedbackReview(Base):
    """
    Feedback Review Table:
    Allows students to submit star ratings and qualitative reviews for specific orders
    as well as daily scheduled mess meals.
    """
    __tablename__ = "feedback_reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    feedback_type = Column(String(20), default="order", nullable=False)  # 'order', 'mess_meal'
    item_id = Column(String(50), nullable=True)
    meal_day = Column(String(20), nullable=True)
    meal_type = Column(String(20), nullable=True)
    rating = Column(Integer, nullable=False)  # 1 to 5
    comment = Column(Text, nullable=True)
    tags = Column(JSON, default=list)  # ["Delicious", "Hot", "Quick"]

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "studentId": self.student_id,
            "orderId": self.order_id,
            "feedbackType": self.feedback_type,
            "itemId": self.item_id,
            "mealDay": self.meal_day,
            "mealType": self.meal_type,
            "rating": self.rating,
            "comment": self.comment or "",
            "tags": self.tags or [],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================================
# 7. PASSCODE RESET OTP TABLE
# =========================================================================
class PasswordResetOtp(Base):
    """
    Password Reset OTP Table:
    Stores time-sensitive OTP security tokens for password/passcode recovery.
    """
    __tablename__ = "password_reset_otps"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    roll_number = Column(String(30), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Monthly mess membership and immutable meal audit records.
from sqlalchemy import Date


class MessPlan(Base):
    __tablename__ = "mess_plans"
    id = Column(String(30), primary_key=True)
    name = Column(String(60), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    tokens = Column(Integer, nullable=False)
    duration_days = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, nullable=False, default=True)
    __table_args__ = (
        CheckConstraint("amount >= 0 AND tokens > 0 AND duration_days > 0", name="ck_mess_plan_values"),
    )


class MessSubscription(Base):
    __tablename__ = "mess_subscriptions"
    id = Column(Integer, primary_key=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=True, index=True)
    student_name = Column(String(100), nullable=False)
    roll_number = Column(String(30), nullable=False, index=True)
    year = Column(String(30), nullable=False)
    branch = Column(String(100), nullable=False)
    mobile_number = Column(String(30), nullable=False)
    plan_type = Column(String(30), ForeignKey("mess_plans.id"), nullable=False)
    amount_paid = Column(Numeric(10, 2), nullable=False)
    total_tokens = Column(Integer, nullable=False)
    remaining_tokens = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="Active", index=True)
    payment_method = Column(String(30), nullable=False)
    payment_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("total_tokens > 0 AND remaining_tokens >= 0 AND remaining_tokens <= total_tokens", name="ck_mess_tokens"),
        CheckConstraint("end_date >= start_date AND amount_paid >= 0", name="ck_mess_subscription_values"),
        CheckConstraint("status IN ('Active','Expired','Exhausted','Cancelled')", name="ck_mess_subscription_status"),
    )


class MessMealAttendance(Base):
    __tablename__ = "mess_meal_attendance"
    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey("mess_subscriptions.id"), nullable=False, index=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=True, index=True)
    meal_date = Column(Date, nullable=False, index=True)
    meal_type = Column(String(20), nullable=False)
    marked_by_admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    status = Column(String(20), nullable=False, default="Taken")
    token_before = Column(Integer, nullable=False)
    token_after = Column(Integer, nullable=False)
    marked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    undo_reason = Column(Text, nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    reversed_by_admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    reversal_token_before = Column(Integer, nullable=True)
    reversal_token_after = Column(Integer, nullable=True)
    __table_args__ = (
        # Reversed rows remain intact; re-marking creates a new audit row.
        Index("uq_mess_taken_meal", "subscription_id", "meal_date", "meal_type", unique=True,
              postgresql_where=text("status = 'Taken'"), sqlite_where=text("status = 'Taken'")),
        CheckConstraint("meal_type IN ('Breakfast','Lunch','Snacks','Dinner')", name="ck_mess_meal_type"),
        CheckConstraint("status IN ('Taken','Reversed')", name="ck_mess_attendance_status"),
        CheckConstraint("token_before > 0 AND token_after = token_before - 1", name="ck_mess_ledger_deduction"),
    )


class NotificationRead(Base):
    """Per-student receipt; reading a broadcast never changes another student."""
    __tablename__ = "notification_reads"
    id = Column(Integer, primary_key=True)
    student_id = Column(String(50), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("student_id", "notification_id", name="uq_notification_reads_student_notification"),)
