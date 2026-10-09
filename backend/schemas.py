from datetime import datetime
from typing import Literal, Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from models import DayOfWeek, MealType, OrderStatusEnum, PaymentStatusEnum


# =========================================================================
# 1. WEEKLY MENU & A LA CARTE SCHEMAS (ADMIN & PUBLIC)
# =========================================================================
class WeeklyMenuItemCreate(BaseModel):
    day: DayOfWeek = Field(
        ...,
        description="Day of the week (e.g. Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday)",
        examples=["Monday"],
    )
    meal_type: MealType = Field(
        ...,
        description="Type of meal: breakfast, lunch, snacks, or dinner",
        examples=["breakfast"],
    )
    items: List[str] = Field(
        ...,
        min_length=1,
        description="Array of food items served for this meal",
        examples=[["Masala Dosa", "Sambar", "Coconut Chutney", "Filter Coffee"]],
    )


class WeeklyMenuBatchUpload(BaseModel):
    schedule: List[WeeklyMenuItemCreate] = Field(
        ...,
        min_length=1,
        description="List of weekly meal items to upsert",
    )


class WeeklyMenuItemResponse(BaseModel):
    id: int
    day: str
    meal_type: str
    items: List[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlaCarteCreate(BaseModel):
    item_name: str = Field(..., min_length=2, max_length=100, examples=["Paneer Butter Masala"])
    price: float = Field(..., gt=0, description="Unit price in local currency", examples=[180.0])
    timing_window: str = Field(
        ...,
        description="Active timing window in 'HH:MM-HH:MM' 24h format or 'all_day'",
        examples=["12:00-15:00"],
    )
    is_available: bool = Field(default=True, description="Item availability toggle")


class AlaCarteUpdate(BaseModel):
    item_name: Optional[str] = Field(None, min_length=2, max_length=100)
    price: Optional[float] = Field(None, gt=0)
    timing_window: Optional[str] = None
    is_available: Optional[bool] = None


class AlaCarteResponse(BaseModel):
    id: int
    item_name: str
    price: float
    timing_window: str
    is_available: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RelevantMealDetails(BaseModel):
    meal_type: str
    status: str  # "active" or "upcoming"
    timing_window: str
    items: List[str]


class TodayMenuResponse(BaseModel):
    system_day: str
    system_time: str
    target_meal: Optional[RelevantMealDetails] = None
    all_today_meals: List[WeeklyMenuItemResponse] = []
    available_ala_carte: List[AlaCarteResponse] = []
    cached: bool = False
    message: str


# =========================================================================
# 2. FOOD ITEMS CATALOGUE SCHEMAS
# =========================================================================
class CustomizationOption(BaseModel):
    name: str
    price: float = 0.0


class FoodItemCreate(BaseModel):
    id: str
    name: str
    desc: Optional[str] = ""
    price: float
    category: str = "Snacks"
    veg: bool = True
    is_available: bool = True
    prep_mins: int = 7
    rating: float = 4.5
    tag: Optional[str] = None
    emoji: str = "🍔"
    photo: Optional[str] = ""
    calories: int = 300
    customizations: List[CustomizationOption] = []
    timing_window: str = "all_day"


class FoodItemResponse(BaseModel):
    id: str
    name: str
    desc: str
    price: float
    category: str
    veg: bool
    available: bool
    prepMins: int
    rating: float
    ratingCount: Optional[int] = 1
    tag: Optional[str] = None
    emoji: str
    photo: str
    calories: int
    customizations: List[Dict[str, Any]] = []
    timingWindow: str
    createdAt: Optional[str] = None


# =========================================================================
# 3. STUDENT AUTHENTICATION & PROFILE SCHEMAS
# =========================================================================
class AdminLoginRequest(BaseModel):
    username: str = Field(..., examples=["admin"])
    password: str = Field(..., examples=["admin123"])


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    role: str
    user: Optional[Dict[str, Any]] = None


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[int] = None

    credential_version: Optional[str] = None


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class StudentRegisterRequest(BaseModel):
    rollNumber: str = Field(..., min_length=4, max_length=30, examples=["21CS1042"])
    name: str = Field(..., min_length=2, max_length=100, examples=["Aarav Sharma"])
    branch: Optional[str] = Field(None, examples=["B.Tech Computer Science & Eng."])
    phone: Optional[str] = Field(None, examples=["+91 98765 43210"])
    email: Optional[str] = Field(None, examples=["aarav.sharma@campus.edu"])
    passcode: str = Field(..., min_length=4, max_length=20, examples=["000000"])


class StudentLoginRequest(BaseModel):
    rollNumber: str = Field(..., examples=["21CS1042"])
    passcode: str = Field(..., examples=["000000"])


class StudentProfileResponse(BaseModel):
    id: str
    rollNumber: str
    name: str
    branch: str
    email: str
    phone: str
    walletBalance: float
    upiId: str
    dietaryPreference: str
    favorites: List[str]
    totalOrders: int
    totalSpent: float
    savedMinutes: int
    createdAt: Optional[str] = None


class StudentProfileUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    dietaryPreference: Optional[str] = None  # all, veg, non-veg, vegan


class ForgotPasscodeRequest(BaseModel):
    rollNumber: str = Field(..., examples=["21CS1042"])


class ResetPasscodeRequest(BaseModel):
    rollNumber: str = Field(..., examples=["21CS1042"])
    otp: str = Field(..., min_length=4, max_length=10, examples=["123456"])
    newPasscode: str = Field(..., min_length=4, max_length=20, examples=["000000"])


class OtpResponse(BaseModel):
    success: bool
    message: str
    otp: Optional[str] = None


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[StudentProfileResponse] = None
    token: Optional[str] = None


class FavoritesToggleResponse(BaseModel):
    success: bool
    itemId: str
    isFavorite: bool
    favorites: List[str]
    message: str


# =========================================================================
# 4. WALLET & TRANSACTION SCHEMAS
# =========================================================================
class WalletRechargeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(..., ge=1, le=10000, max_digits=7, decimal_places=2)
    paymentMethod: Literal["razorpay", "UPI", "Card", "NetBanking"] = "razorpay"


class WalletTransactionResponse(BaseModel):
    id: str
    studentId: str
    amount: float
    type: str  # credit or debit
    paymentMethod: str
    description: str
    orderId: Optional[int] = None
    referenceId: Optional[str] = None
    status: str
    createdAt: Optional[str] = None
    dateFormatted: Optional[str] = None


class WalletBalanceResponse(BaseModel):
    walletBalance: float
    upiId: str
    totalSpent: float
    totalOrders: int


# =========================================================================
# 5. ORDER PLACEMENT & TRACKING SCHEMAS
# =========================================================================
class OrderItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    qty: int = Field(gt=0, le=50)
    # Legacy display values are accepted for compatibility, never used for pricing.
    name: Optional[str] = Field(default=None, max_length=100)
    price: Optional[float] = Field(default=None, ge=0)
    customizations: List[str] = Field(default_factory=list, max_length=10)
    photo: Optional[str] = Field(default=None, max_length=2000)


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[OrderItemInput] = Field(min_length=1, max_length=50)
    paymentMethod: Literal["wallet", "razorpay", "upi", "card"] = "wallet"
    specialInstructions: Optional[str] = Field(default=None, max_length=255)


class OrderResponse(BaseModel):
    id: str
    orderId: int
    number: str
    studentId: str
    items: List[Dict[str, Any]]
    itemTotal: float
    packagingFee: float
    gst: float
    total: float
    paymentMethod: str
    payment: str
    status: str
    pickupCounter: str
    pickupToken: str
    queuePosition: int
    prepTimeMinutes: int
    estimatedReadyAt: Optional[str] = None
    qrCodeData: str
    cancellationReason: Optional[str] = None
    specialInstructions: Optional[str] = None
    date: str
    createdAt: Optional[str] = None
    readyAt: Optional[str] = None
    completedAt: Optional[str] = None

    checkout: Optional[Dict[str, Any]] = None
    refundStatus: Optional[str] = None


class TimelineStep(BaseModel):
    key: str
    label: str
    note: str
    done: bool
    active: bool


class OrderTrackingResponse(BaseModel):
    orderNumber: str
    status: str
    queuePosition: int
    ordersAhead: int
    countdownSeconds: int
    countdownMinutesFormatted: str
    estimatedReadyTime: str
    progressPercent: int
    pickupCounter: str
    pickupToken: str
    timeline: List[TimelineStep]
    activeStepIndex: int
    items: List[Dict[str, Any]]
    totalAmount: float
    paymentStatus: str


class OrderStatusUpdateRequest(BaseModel):
    status: OrderStatusEnum = Field(..., examples=["Preparing", "Ready", "Completed", "Cancelled"])
    cancellationReason: Optional[str] = None
    cancellation_reason: Optional[str] = None


class CanteenQueueStatusResponse(BaseModel):
    activeOrdersCount: int
    queuedOrdersCount: int
    preparingOrdersCount: int
    averagePrepMinutes: int
    currentRushLevel: str  # "Low", "Moderate", "High Rush"
    estimatedWaitMinutes: int
    counterOpen: bool = True
    activeCounterName: str = "Counter 2 (Main Block)"


# =========================================================================
# 6. NOTIFICATIONS SCHEMAS
# =========================================================================
class NotificationResponse(BaseModel):
    id: int
    studentId: Optional[str] = None
    title: str
    subtitle: str
    type: str
    emoji: str
    color: str
    orderId: Optional[int] = None
    unread: bool
    createdAt: Optional[str] = None
    time: str


class NotificationCreateRequest(BaseModel):
    studentId: Optional[str] = None
    title: str
    body: str
    type: str = "order_update"
    emoji: str = "🔔"
    colorTheme: str = "mint"
    orderId: Optional[int] = None


# =========================================================================
# 7. FEEDBACK & REVIEW SCHEMAS
# =========================================================================
class OrderReviewCreate(BaseModel):
    orderId: int
    rating: int = Field(..., ge=1, le=5, description="1 to 5 star rating")
    comment: Optional[str] = ""
    tags: Optional[List[str]] = []


class MessMealFeedbackCreate(BaseModel):
    mealDay: str = Field(..., examples=["Monday"])
    mealType: str = Field(..., examples=["lunch"])
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = ""
    tags: Optional[List[str]] = []


class FeedbackResponse(BaseModel):
    id: int
    studentId: str
    feedbackType: str
    orderId: Optional[int] = None
    mealDay: Optional[str] = None
    mealType: Optional[str] = None
    rating: int
    comment: str
    tags: List[str]
    createdAt: Optional[str] = None


# Mess staff input. Balances and audit fields are always server-owned.
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import model_validator, field_validator


class MessSubscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    student_name: str = Field(min_length=2, max_length=100)
    roll_number: str = Field(min_length=3, max_length=30)
    year: str = Field(min_length=1, max_length=30)
    branch: str = Field(min_length=1, max_length=100)
    mobile_number: str = Field(min_length=8, max_length=30)
    plan_type: Literal["single", "double"]
    amount_paid: Optional[Decimal] = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    total_tokens: Optional[int] = Field(default=None, gt=0, le=10000)
    start_date: date
    end_date: Optional[date] = None
    payment_method: str = Field(min_length=1, max_length=30)
    payment_reference: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("roll_number")
    @classmethod
    def normalize_roll(cls, value):
        value = value.upper().replace(" ", "")
        if len(value) < 3:
            raise ValueError("Roll number must contain at least three characters")
        return value

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        return self


class MessSubscriptionUpdate(MessSubscriptionInput):
    status: Literal["Active", "Cancelled"] = "Active"


class MessMarkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscription_id: int = Field(gt=0)
    meal_date: date
    # The ledger retains other meal types for history and future expansion.
    meal_type: Literal["Lunch", "Dinner"]


class MessUndoInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=500)


class MessPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=60)
    amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    tokens: int = Field(gt=0, le=10000)
    duration_days: int = Field(gt=0, le=366)
    is_active: bool = True
