import enum
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import JSON, TypeDecorator
from database import Base


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
    price = Column(Float, nullable=False)
    timing_window = Column(String(50), nullable=False)  # e.g., '08:00-11:00', '12:00-15:00', 'all_day'
    is_available = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
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
    price = Column(Float, nullable=False)
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

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.desc or "",
            "price": self.price,
            "category": self.category,
            "veg": self.veg,
            "available": self.is_available,
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
    wallet_balance = Column(Float, default=250.0, nullable=False)  # ₹250 welcome bonus
    upi_id = Column(String(100), nullable=True)
    dietary_preference = Column(String(30), default="all", nullable=False)  # all, veg, non-veg, vegan
    favorites = Column(JSON, default=list)  # array of favorite food item IDs
    total_orders = Column(Integer, default=0, nullable=False)
    total_spent = Column(Float, default=0.0, nullable=False)
    saved_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
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
    item_total = Column(Float, nullable=False)
    packaging_fee = Column(Float, default=8.0, nullable=False)
    gst_amount = Column(Float, default=0.0, nullable=False)
    total_amount = Column(Float, nullable=False)

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

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    ready_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

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
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(20), nullable=False)  # 'credit', 'debit'
    payment_method = Column(String(30), default="UPI", nullable=False)  # 'UPI', 'Card', 'Wallet', 'Bonus'
    description = Column(String(255), nullable=False)
    order_id = Column(Integer, nullable=True)
    reference_id = Column(String(100), nullable=True)
    status = Column(String(20), default="success", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
    order_id = Column(Integer, nullable=True)
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
