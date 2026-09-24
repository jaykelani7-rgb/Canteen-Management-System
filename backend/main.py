from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from auth import get_password_hash
from config import settings
from database import get_redis_client, init_db, AsyncSessionLocal
from models import AdminUser, FoodItem, StudentUser
from routes import admin_router, auth_router, menu_router
from ocr_router import ocr_router
from student_routes import student_router


SAMPLE_DEMO_STUDENTS = [
    {
        "id": "usr_aarav",
        "roll_number": "21CS1042",
        "name": "Aarav Sharma",
        "branch": "B.Tech Computer Science & Eng.",
        "email": "aarav.sharma@campus.edu",
        "phone": "+91 98765 43210",
        "wallet_balance": 340.0,
        "upi_id": "aarav@campuspay",
        "dietary_preference": "all",
        "favorites": ["veg-burger", "cold-coffee", "french-fries"],
        "total_orders": 38,
        "total_spent": 4200.0,
        "saved_minutes": 12,
        "passcode": "000000",
    },
    {
        "id": "usr_priya",
        "roll_number": "21IT2015",
        "name": "Priya Patel",
        "branch": "B.Tech Information Technology",
        "email": "priya.patel@campus.edu",
        "phone": "+91 98765 11223",
        "wallet_balance": 520.0,
        "upi_id": "priya@campuspay",
        "dietary_preference": "veg",
        "favorites": ["paneer-wrap", "masala-maggi"],
        "total_orders": 42,
        "total_spent": 5120.0,
        "saved_minutes": 18,
        "passcode": "000000",
    },
    {
        "id": "usr_rohan",
        "roll_number": "22EC3088",
        "name": "Rohan Verma",
        "branch": "B.Tech Electronics & Comm.",
        "email": "rohan.verma@campus.edu",
        "phone": "+91 98765 99887",
        "wallet_balance": 150.0,
        "upi_id": "rohan@campuspay",
        "dietary_preference": "all",
        "favorites": ["tea", "cheese-sandwich"],
        "total_orders": 19,
        "total_spent": 1850.0,
        "saved_minutes": 6,
        "passcode": "000000",
    },
    {
        "id": "usr_ananya",
        "roll_number": "23ME5001",
        "name": "Ananya Iyer",
        "branch": "B.Tech Mechanical Engineering",
        "email": "ananya.iyer@campus.edu",
        "phone": "+91 98765 66554",
        "wallet_balance": 780.0,
        "upi_id": "ananya@campuspay",
        "dietary_preference": "veg",
        "favorites": ["veg-pizza", "cold-coffee"],
        "total_orders": 12,
        "total_spent": 1400.0,
        "saved_minutes": 4,
        "passcode": "000000",
    },
]

SAMPLE_FOOD_ITEMS = [
    {
        "id": "veg-burger",
        "name": "Veg Burger",
        "desc": "Crispy patty, lettuce, house sauce in a toasted bun.",
        "price": 60.0,
        "rating": 4.6,
        "rating_count": 84,
        "prep_mins": 8,
        "category": "Snacks",
        "veg": True,
        "is_available": True,
        "tag": "Bestseller",
        "emoji": "🍔",
        "photo": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=360&h=360&fit=crop&auto=format",
        "calories": 360,
        "customizations": [{"name": "Extra cheese", "price": 15.0}, {"name": "Spicy peri-peri", "price": 0.0}, {"name": "No onions", "price": 0.0}],
    },
    {
        "id": "paneer-wrap",
        "name": "Paneer Wrap",
        "desc": "Spiced paneer, onions & mint chutney rolled fresh.",
        "price": 80.0,
        "rating": 4.7,
        "rating_count": 62,
        "prep_mins": 10,
        "category": "Meals",
        "veg": True,
        "is_available": True,
        "tag": "Chef’s pick",
        "emoji": "🌯",
        "photo": "https://images.unsplash.com/photo-1626700051175-6818013e1d4f?w=360&h=360&fit=crop&auto=format",
        "calories": 420,
        "customizations": [{"name": "Extra paneer", "price": 20.0}, {"name": "Extra sauce", "price": 5.0}],
    },
    {
        "id": "masala-maggi",
        "name": "Masala Maggi",
        "desc": "Classic hostel-night noodles with extra masala.",
        "price": 40.0,
        "rating": 4.8,
        "rating_count": 128,
        "prep_mins": 7,
        "category": "Meals",
        "veg": True,
        "is_available": True,
        "tag": "Student fav",
        "emoji": "🍜",
        "photo": "https://images.unsplash.com/photo-1612929633738-8fe44f7ec841?w=360&h=360&fit=crop&auto=format",
        "calories": 310,
        "customizations": [{"name": "Double masala", "price": 5.0}, {"name": "Cheese topping", "price": 15.0}],
    },
    {
        "id": "cold-coffee",
        "name": "Cold Coffee",
        "desc": "Thick, frothy & chilled. The 4 PM lifesaver.",
        "price": 50.0,
        "rating": 4.5,
        "rating_count": 95,
        "prep_mins": 5,
        "category": "Beverages",
        "veg": True,
        "is_available": True,
        "emoji": "🥤",
        "photo": "https://images.unsplash.com/photo-1461023058943-07fcbe16d735?w=360&h=360&fit=crop&auto=format",
        "calories": 210,
        "customizations": [{"name": "Extra scoop ice cream", "price": 20.0}, {"name": "Strong decoction", "price": 0.0}],
    },
    {
        "id": "tea",
        "name": "Masala Tea",
        "desc": "Freshly brewed cutting chai, served hot.",
        "price": 15.0,
        "rating": 4.4,
        "rating_count": 140,
        "prep_mins": 4,
        "category": "Beverages",
        "veg": True,
        "is_available": True,
        "emoji": "☕",
        "photo": "https://images.unsplash.com/photo-1571934811356-5cc061b6821f?w=360&h=360&fit=crop&auto=format",
        "calories": 90,
        "customizations": [{"name": "Adrak / Ginger extra", "price": 0.0}, {"name": "Less sugar", "price": 0.0}],
    },
    {
        "id": "french-fries",
        "name": "French Fries",
        "desc": "Golden, salted & crunchy with peri-peri dip.",
        "price": 55.0,
        "rating": 4.5,
        "rating_count": 78,
        "prep_mins": 6,
        "category": "Snacks",
        "veg": True,
        "is_available": True,
        "emoji": "🍟",
        "photo": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=360&h=360&fit=crop&auto=format",
        "calories": 280,
        "customizations": [{"name": "Cheese dip", "price": 15.0}, {"name": "Peri peri spice", "price": 0.0}],
    },
    {
        "id": "veg-pizza",
        "name": "Veg Pizza",
        "desc": "Cheese-loaded personal pizza with garden veggies.",
        "price": 120.0,
        "rating": 4.6,
        "rating_count": 45,
        "prep_mins": 14,
        "category": "Meals",
        "veg": True,
        "is_available": True,
        "emoji": "🍕",
        "photo": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=360&h=360&fit=crop&auto=format",
        "calories": 520,
        "customizations": [{"name": "Extra cheese burst", "price": 30.0}, {"name": "Jalapenos & olives", "price": 20.0}],
    },
    {
        "id": "cheese-sandwich",
        "name": "Cheese Sandwich",
        "desc": "Grilled triple-cheese sandwich, gooey inside.",
        "price": 70.0,
        "rating": 4.3,
        "rating_count": 51,
        "prep_mins": 8,
        "category": "Snacks",
        "veg": True,
        "is_available": True,
        "emoji": "🥪",
        "photo": "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=360&h=360&fit=crop&auto=format",
        "calories": 340,
        "customizations": [{"name": "Toast well done", "price": 0.0}, {"name": "Green chutney spread", "price": 0.0}],
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager:
    - Runs schema migrations / table creations on startup
    - Bootstraps default canteen admin account if empty
    - Bootstraps sample student accounts & food catalogue if empty
    - Verifies Redis connectivity
    - Gracefully closes connection pools on shutdown
    """
    print("\n🚀 Starting Canteen Management System Backend...")

    # 1. Initialize PostgreSQL Tables
    try:
        await init_db()
        print("✅ PostgreSQL Database Schema initialized successfully.")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

    # 2. Seed Default Admin Account if missing
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(AdminUser).where(AdminUser.username == settings.DEFAULT_ADMIN_USERNAME)
            result = await session.execute(stmt)
            admin = result.scalar_one_or_none()

            if not admin:
                default_admin = AdminUser(
                    username=settings.DEFAULT_ADMIN_USERNAME,
                    hashed_password=get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                session.add(default_admin)
                await session.commit()
                print(
                    f"✅ Seeded initial admin account: '{settings.DEFAULT_ADMIN_USERNAME}' (Password: '{settings.DEFAULT_ADMIN_PASSWORD}')"
                )
            else:
                print(f"ℹ️ Admin account '{settings.DEFAULT_ADMIN_USERNAME}' already exists.")
    except Exception as e:
        print(f"⚠️ Error verifying/seeding admin account: {e}")

    # 3. Seed Demo Students & Food Items
    try:
        async with AsyncSessionLocal() as session:
            # Students
            for s in SAMPLE_DEMO_STUDENTS:
                res = await session.execute(select(StudentUser).where(StudentUser.roll_number == s["roll_number"]))
                if not res.scalar_one_or_none():
                    new_s = StudentUser(
                        id=s["id"],
                        roll_number=s["roll_number"],
                        name=s["name"],
                        branch=s["branch"],
                        email=s["email"],
                        phone=s["phone"],
                        hashed_passcode=get_password_hash(s["passcode"]),
                        wallet_balance=s["wallet_balance"],
                        upi_id=s["upi_id"],
                        dietary_preference=s["dietary_preference"],
                        favorites=s["favorites"],
                        total_orders=s["total_orders"],
                        total_spent=s["total_spent"],
                        saved_minutes=s["saved_minutes"],
                        is_active=True,
                    )
                    session.add(new_s)

            # Food Items
            for item in SAMPLE_FOOD_ITEMS:
                res = await session.execute(select(FoodItem).where(FoodItem.id == item["id"]))
                if not res.scalar_one_or_none():
                    new_item = FoodItem(
                        id=item["id"],
                        name=item["name"],
                        desc=item["desc"],
                        price=item["price"],
                        rating=item["rating"],
                        rating_count=item["rating_count"],
                        prep_mins=item["prep_mins"],
                        category=item["category"],
                        veg=item["veg"],
                        is_available=item["is_available"],
                        tag=item.get("tag"),
                        emoji=item["emoji"],
                        photo=item["photo"],
                        calories=item["calories"],
                        customizations=item["customizations"],
                        timing_window="all_day",
                    )
                    session.add(new_item)

            await session.commit()
            print("✅ Verified/Seeded student accounts and food item catalogue.")
    except Exception as e:
        print(f"⚠️ Error seeding students/food items: {e}")

    # 4. Verify Redis Connection
    try:
        client = get_redis_client()
        await client.ping()
        print("✅ Redis caching connection verified successfully.")
    except Exception as e:
        print(f"⚠️ Redis is unreachable ({e}). Cache will fallback to database queries.")

    yield

    # Teardown / Graceful Shutdown
    print("\n🛑 Shutting down Canteen Management System Backend...")
    try:
        client = get_redis_client()
        await client.close()
        print("✅ Redis client connection closed.")
    except Exception:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
High-Performance Canteen & Mess Management API built with **FastAPI**, **PostgreSQL**, and **Redis**.

### Student & Admin APIs:
* 🎓 **Student Authentication**: Register, Login, Passcode Reset OTP, Profile (`/api/auth/*`, `/api/student/*`).
* 🍔 **Live Menu & Search**: Browse snacks, meals, drinks, and dietary tags (`/api/menu/items`).
* 👛 **Canteen Wallet**: Recharges, atomic balance checks, transactions ledger (`/api/student/wallet`).
* 📦 **Orders & Live Tracking**: Placement, smart ETA, queue position countdown, pickup token (`/api/student/orders`).
* 🔔 **Notifications & Alerts**: Real-time order updates, food ready alerts, announcements (`/api/student/notifications`).
* ⭐ **Ratings & Reviews**: Order reviews and daily scheduled mess feedback (`/api/student/feedback/*`).
* 🕒 **Dynamic Meal Routing**: Returns current/upcoming meal (`GET /api/menu/today`) based on system clock and day.
* ⚡ **High Throughput with Redis**: Sub-millisecond cached responses for high student concurrency.
* 🔒 **JWT Protection**: Strictly secured endpoints for weekly schedules & a la carte management.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# -------------------------------------------------------------------------
# CORS (Cross-Origin Resource Sharing) Middleware
# -------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------------
# Register Modular APIRouters
# -------------------------------------------------------------------------
app.include_router(student_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(menu_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(ocr_router, prefix=settings.API_V1_STR)


# -------------------------------------------------------------------------
# Health Check & Root Endpoints
# -------------------------------------------------------------------------
@app.get("/", tags=["System"])
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "documentation": "/docs",
        "endpoints": {
            "student_login": "/api/auth/login",
            "student_register": "/api/auth/register",
            "student_menu": "/api/menu/items",
            "student_orders": "/api/student/orders",
            "student_wallet": "/api/student/wallet",
            "today_menu": "/api/menu/today",
            "weekly_menu": "/api/menu/weekly",
            "ala_carte": "/api/menu/ala-carte",
            "admin_login": "/api/auth/login",
            "admin_upload_weekly": "/api/admin/menu/weekly",
        },
    }


@app.get("/api/health", tags=["System"], status_code=status.HTTP_200_OK)
async def health_check():
    """System health check endpoint verifying DB & Redis health."""
    db_status = "healthy"
    redis_status = "healthy"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    try:
        client = get_redis_client()
        await client.ping()
    except Exception as e:
        redis_status = f"unreachable: {str(e)}"

    return {
        "status": "ok" if db_status == "healthy" and redis_status == "healthy" else "degraded",
        "database": db_status,
        "redis": redis_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
