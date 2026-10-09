"""Frozen pre-hardening schema. Never import runtime model metadata here."""
from sqlalchemy.orm import declarative_base
Base = declarative_base()
import enum
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import JSON, TypeDecorator

class DayOfWeek(str, enum.Enum):
    MONDAY = 'Monday'
    TUESDAY = 'Tuesday'
    WEDNESDAY = 'Wednesday'
    THURSDAY = 'Thursday'
    FRIDAY = 'Friday'
    SATURDAY = 'Saturday'
    SUNDAY = 'Sunday'

class MealType(str, enum.Enum):
    BREAKFAST = 'breakfast'
    LUNCH = 'lunch'
    SNACKS = 'snacks'
    DINNER = 'dinner'

class OrderStatusEnum(str, enum.Enum):
    QUEUED = 'Queued'
    PREPARING = 'Preparing'
    READY = 'Ready'
    PICKED_UP = 'Picked Up'
    COMPLETED = 'Completed'
    DELAYED = 'Delayed'
    CANCELLED = 'Cancelled'

class PaymentStatusEnum(str, enum.Enum):
    PAID = 'Paid'
    FAILED = 'Failed'
    REFUNDED = 'Refunded'
    PENDING = 'Pending'

class StringListType(TypeDecorator):
    """PostgreSQL ARRAY(String) with JSON fallback for seamless portability."""
    impl = ARRAY(String)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(ARRAY(String))
        else:
            return dialect.type_descriptor(JSON)

class WeeklyMenu(Base):
    """
    Weekly Menu Table:
    Stores the scheduled rotating mess/canteen menu by day, meal type, and item array.
    """
    __tablename__ = 'weekly_menu'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    day = Column(String(20), nullable=False, index=True)
    meal_type = Column(String(20), nullable=False, index=True)
    items = Column(StringListType, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint('day', 'meal_type', name='uq_weekly_menu_day_meal'),)

class AlaCarte(Base):
    """
    A La Carte Table:
    Stores on-demand food items, their unit prices, timing windows, and availability.
    """
    __tablename__ = 'ala_carte'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_name = Column(String(100), unique=True, nullable=False, index=True)
    price = Column(Float, nullable=False)
    timing_window = Column(String(50), nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class FoodItem(Base):
    """
    Food Item Table:
    Rich food catalogue item for student browsing, cart operations, customization, and ordering.
    """
    __tablename__ = 'food_items'
    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    desc = Column(String(255), nullable=True)
    price = Column(Float, nullable=False)
    category = Column(String(30), nullable=False, default='Snacks', index=True)
    veg = Column(Boolean, default=True, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    prep_mins = Column(Integer, default=7, nullable=False)
    rating = Column(Float, default=4.5, nullable=False)
    rating_count = Column(Integer, default=1, nullable=False)
    tag = Column(String(50), nullable=True)
    emoji = Column(String(10), default='🍔', nullable=False)
    photo = Column(String(500), nullable=True)
    calories = Column(Integer, default=300, nullable=False)
    customizations = Column(JSON, default=list)
    timing_window = Column(String(50), default='all_day', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AdminUser(Base):
    """
    Admin User Table:
    Stores canteen administrators authorized to upload and modify menu schedules.
    """
    __tablename__ = 'admin_users'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default='admin', nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class StudentUser(Base):
    """
    Student User Table:
    Stores registered students with college roll numbers, passcodes, wallet balances, and preferences.
    """
    __tablename__ = 'students'
    id = Column(String(50), primary_key=True, index=True)
    roll_number = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    branch = Column(String(100), nullable=False, default='B.Tech Student')
    email = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    hashed_passcode = Column(String(255), nullable=False)
    wallet_balance = Column(Float, default=250.0, nullable=False)
    upi_id = Column(String(100), nullable=True)
    dietary_preference = Column(String(30), default='all', nullable=False)
    favorites = Column(JSON, default=list)
    total_orders = Column(Integer, default=0, nullable=False)
    total_spent = Column(Float, default=0.0, nullable=False)
    saved_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Order(Base):
    """
    Order Table:
    Stores customer orders, item breakdown, monetary details, payment info,
    live queue position, ETA calculation, and status progression.
    """
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_number = Column(String(20), unique=True, nullable=False, index=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=False, index=True)
    items_json = Column(JSON, nullable=False, default=list)
    item_total = Column(Float, nullable=False)
    packaging_fee = Column(Float, default=8.0, nullable=False)
    gst_amount = Column(Float, default=0.0, nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String(30), default='wallet', nullable=False)
    payment_status = Column(String(20), default='Paid', nullable=False)
    order_status = Column(String(20), default='Queued', nullable=False, index=True)
    pickup_counter = Column(String(50), default='Counter 2', nullable=False)
    pickup_token = Column(String(20), nullable=True)
    queue_position = Column(Integer, default=1, nullable=False)
    prep_time_minutes = Column(Integer, default=5, nullable=False)
    estimated_ready_at = Column(DateTime(timezone=True), nullable=True)
    qr_code_data = Column(String(255), nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    special_instructions = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    ready_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class WalletTransaction(Base):
    """
    Wallet Transaction Table:
    Double-entry style financial ledger recording credits, debits, recharges, and refunds.
    """
    __tablename__ = 'wallet_transactions'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(20), nullable=False)
    payment_method = Column(String(30), default='UPI', nullable=False)
    description = Column(String(255), nullable=False)
    order_id = Column(Integer, nullable=True)
    reference_id = Column(String(100), nullable=True)
    status = Column(String(20), default='success', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    """
    Notification Table:
    Stores targeted student notifications (order ready, in-prep, promos, stock updates)
    as well as general canteen announcements.
    """
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=True, index=True)
    title = Column(String(100), nullable=False)
    body = Column(String(255), nullable=False)
    notification_type = Column(String(30), default='order_update', nullable=False)
    emoji = Column(String(10), default='🔔', nullable=False)
    color_theme = Column(String(20), default='mint', nullable=False)
    order_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class FeedbackReview(Base):
    """
    Feedback Review Table:
    Allows students to submit star ratings and qualitative reviews for specific orders
    as well as daily scheduled mess meals.
    """
    __tablename__ = 'feedback_reviews'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True, index=True)
    feedback_type = Column(String(20), default='order', nullable=False)
    item_id = Column(String(50), nullable=True)
    meal_day = Column(String(20), nullable=True)
    meal_type = Column(String(20), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PasswordResetOtp(Base):
    """
    Password Reset OTP Table:
    Stores time-sensitive OTP security tokens for password/passcode recovery.
    """
    __tablename__ = 'password_reset_otps'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    roll_number = Column(String(30), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
from sqlalchemy import Date, Numeric, CheckConstraint, Index, text

class MessPlan(Base):
    __tablename__ = 'mess_plans'
    id = Column(String(30), primary_key=True)
    name = Column(String(60), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    tokens = Column(Integer, nullable=False)
    duration_days = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, nullable=False, default=True)
    __table_args__ = (CheckConstraint('amount >= 0 AND tokens > 0 AND duration_days > 0', name='ck_mess_plan_values'),)

class MessSubscription(Base):
    __tablename__ = 'mess_subscriptions'
    id = Column(Integer, primary_key=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=True, index=True)
    student_name = Column(String(100), nullable=False)
    roll_number = Column(String(30), nullable=False, index=True)
    year = Column(String(30), nullable=False)
    branch = Column(String(100), nullable=False)
    mobile_number = Column(String(30), nullable=False)
    plan_type = Column(String(30), ForeignKey('mess_plans.id'), nullable=False)
    amount_paid = Column(Numeric(10, 2), nullable=False)
    total_tokens = Column(Integer, nullable=False)
    remaining_tokens = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default='Active', index=True)
    payment_method = Column(String(30), nullable=False)
    payment_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint('total_tokens > 0 AND remaining_tokens >= 0 AND remaining_tokens <= total_tokens', name='ck_mess_tokens'), CheckConstraint('end_date >= start_date AND amount_paid >= 0', name='ck_mess_subscription_values'), CheckConstraint("status IN ('Active','Expired','Exhausted','Cancelled')", name='ck_mess_subscription_status'))

class MessMealAttendance(Base):
    __tablename__ = 'mess_meal_attendance'
    id = Column(Integer, primary_key=True)
    subscription_id = Column(Integer, ForeignKey('mess_subscriptions.id'), nullable=False, index=True)
    student_id = Column(String(50), ForeignKey('students.id'), nullable=True, index=True)
    meal_date = Column(Date, nullable=False, index=True)
    meal_type = Column(String(20), nullable=False)
    marked_by_admin_id = Column(Integer, ForeignKey('admin_users.id'), nullable=True)
    status = Column(String(20), nullable=False, default='Taken')
    token_before = Column(Integer, nullable=False)
    token_after = Column(Integer, nullable=False)
    marked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    undo_reason = Column(Text, nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    reversed_by_admin_id = Column(Integer, ForeignKey('admin_users.id'), nullable=True)
    reversal_token_before = Column(Integer, nullable=True)
    reversal_token_after = Column(Integer, nullable=True)
    __table_args__ = (Index('uq_mess_taken_meal', 'subscription_id', 'meal_date', 'meal_type', unique=True, postgresql_where=text("status = 'Taken'"), sqlite_where=text("status = 'Taken'")), CheckConstraint("meal_type IN ('Breakfast','Lunch','Snacks','Dinner')", name='ck_mess_meal_type'), CheckConstraint("status IN ('Taken','Reversed')", name='ck_mess_attendance_status'), CheckConstraint('token_before > 0 AND token_after = token_before - 1', name='ck_mess_ledger_deduction'))
