"""
Database Seeding Script for Canteen Management System.
Populates PostgreSQL with:
1. Full 7-day rotating weekly mess menu schedule.
2. A La Carte dish items with timing windows.
3. Rich food items catalogue with photos, emojis, prep times, and customization options.
4. Demo student user accounts (Aarav, Priya, Rohan, Ananya) with passcodes and balances.
5. Sample active & past orders with live status tracking.
6. Wallet ledger transactions and notification alerts.

Run with: python seed_data.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from auth import get_password_hash
from database import AsyncSessionLocal, init_db
from models import (
    AlaCarte,
    FeedbackReview,
    FoodItem,
    Notification,
    Order,
    StudentUser,
    WalletTransaction,
    WeeklyMenu,
)

SAMPLE_WEEKLY_MENU = [
    # Monday
    {
        "day": "Monday",
        "meal_type": "breakfast",
        "items": ["Idli", "Medu Vada", "Coconut Chutney", "Sambar", "Tea / Coffee"],
    },
    {
        "day": "Monday",
        "meal_type": "lunch",
        "items": ["Steamed Basmati Rice", "Dal Tadka", "Paneer Butter Masala", "Chapati", "Curd", "Gulab Jamun"],
    },
    {
        "day": "Monday",
        "meal_type": "snacks",
        "items": ["Samosa with Mint Chutney", "Ginger Cardamom Tea"],
    },
    {
        "day": "Monday",
        "meal_type": "dinner",
        "items": ["Jeera Rice", "Dal Makhani", "Mixed Veg Curry", "Tandoori Roti", "Salad", "Ice Cream"],
    },
    # Tuesday
    {
        "day": "Tuesday",
        "meal_type": "breakfast",
        "items": ["Masala Poha", "Sev & Lemon", "Boiled Eggs", "Sprouts Salad", "Coffee"],
    },
    {
        "day": "Tuesday",
        "meal_type": "lunch",
        "items": ["Veg Biryani", "Mirchi Ka Salan", "Boondi Raita", "Phulka", "Yellow Moong Dal"],
    },
    {
        "day": "Tuesday",
        "meal_type": "snacks",
        "items": ["Pani Puri / Sev Puri", "Masala Chai"],
    },
    {
        "day": "Tuesday",
        "meal_type": "dinner",
        "items": ["Ghee Rice", "Chole Masala", "Bhature / Kulcha", "Pickle", "Kheer"],
    },
    # Wednesday
    {
        "day": "Wednesday",
        "meal_type": "breakfast",
        "items": ["Aloo Paratha with Butter", "Pickle", "Curd", "Fresh Fruit Bowl", "Tea"],
    },
    {
        "day": "Wednesday",
        "meal_type": "lunch",
        "items": ["Steamed Rice", "Chicken Curry / Kadhai Paneer", "Dal Fry", "Roti", "Raita"],
    },
    {
        "day": "Wednesday",
        "meal_type": "snacks",
        "items": ["Veg Cutlet", "Tomato Ketchup", "Green Tea"],
    },
    {
        "day": "Wednesday",
        "meal_type": "dinner",
        "items": ["Fried Rice", "Chilli Paneer / Chicken Manchurian", "Hot & Sour Soup", "Brownie"],
    },
    # Thursday
    {
        "day": "Thursday",
        "meal_type": "breakfast",
        "items": ["Mysore Masala Dosa", "Tomato Chutney", "Filter Coffee"],
    },
    {
        "day": "Thursday",
        "meal_type": "lunch",
        "items": ["Lemon Rice", "Sambhar", "Avial", "Papad", "Curd Rice"],
    },
    {
        "day": "Thursday",
        "meal_type": "snacks",
        "items": ["Bhel Puri", "Cold Coffee"],
    },
    {
        "day": "Thursday",
        "meal_type": "dinner",
        "items": ["Methi Roti", "Palak Paneer", "Rajma Masala", "Basmati Rice", "Rasgulla"],
    },
    # Friday
    {
        "day": "Friday",
        "meal_type": "breakfast",
        "items": ["Upma", "Coconut Chutney", "Boiled Egg / Banana", "Tea"],
    },
    {
        "day": "Friday",
        "meal_type": "lunch",
        "items": ["Hyderabadi Dum Biryani (Veg/Chicken)", "Raita", "Salad", "Gulab Jamun"],
    },
    {
        "day": "Friday",
        "meal_type": "snacks",
        "items": ["Pav Bhaji", "Masala Butter Milk"],
    },
    {
        "day": "Friday",
        "meal_type": "dinner",
        "items": ["Naan", "Butter Chicken / Shahi Paneer", "Dal Tadka", "Jeera Rice", "Pastry"],
    },
    # Saturday
    {
        "day": "Saturday",
        "meal_type": "breakfast",
        "items": ["Puri Bhaji", "Halwa", "Tea / Coffee"],
    },
    {
        "day": "Saturday",
        "meal_type": "lunch",
        "items": ["Rajma Chawal", "Mixed Veg Raita", "Crispy Papad", "Chapati"],
    },
    {
        "day": "Saturday",
        "meal_type": "snacks",
        "items": ["Grilled Cheese Sandwich", "Cold Drink / Juice"],
    },
    {
        "day": "Saturday",
        "meal_type": "dinner",
        "items": ["Pasta Alfredo / Arrabbiata", "Garlic Bread", "Caesar Salad", "Choco Lava Cake"],
    },
    # Sunday
    {
        "day": "Sunday",
        "meal_type": "breakfast",
        "items": ["Chole Bhature", "Lassi", "Pickle", "Special Sweet"],
    },
    {
        "day": "Sunday",
        "meal_type": "lunch",
        "items": ["Special Thali (Rice, Dal, 2 Curries, Roti, Sweet, Papad, Curd)"],
    },
    {
        "day": "Sunday",
        "meal_type": "snacks",
        "items": ["Kachori with Sweet & Spicy Chutney", "Chai"],
    },
    {
        "day": "Sunday",
        "meal_type": "dinner",
        "items": ["Special Biryani Feast", "Raita", "Double Ka Meetha"],
    },
]

SAMPLE_ALA_CARTE = [
    {"item_name": "Crispy French Fries", "price": 80.0, "timing_window": "all_day", "is_available": True},
    {"item_name": "Paneer Tikka Roll", "price": 140.0, "timing_window": "12:00-22:00", "is_available": True},
    {"item_name": "Chicken Tikka Roll", "price": 160.0, "timing_window": "12:00-22:00", "is_available": True},
    {"item_name": "Veg Cheese Burger", "price": 110.0, "timing_window": "11:00-22:00", "is_available": True},
    {"item_name": "Cold Coffee with Ice Cream", "price": 75.0, "timing_window": "all_day", "is_available": True},
    {"item_name": "Fresh Orange Juice", "price": 60.0, "timing_window": "08:00-18:00", "is_available": True},
    {"item_name": "Maggi Noodles (Double Masala)", "price": 50.0, "timing_window": "all_day", "is_available": True},
    {"item_name": "Oreo Thickshake", "price": 95.0, "timing_window": "12:00-22:30", "is_available": True},
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
        "is_available": False,  # Sold out sample
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


async def seed():
    print("🌱 Initializing Database Schema...")
    await init_db()

    async with AsyncSessionLocal() as session:
        # 1. Weekly Menu
        print("🌱 Seeding Weekly Menu schedule...")
        for item in SAMPLE_WEEKLY_MENU:
            stmt = select(WeeklyMenu).where(
                WeeklyMenu.day == item["day"],
                WeeklyMenu.meal_type == item["meal_type"],
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.items = item["items"]
            else:
                session.add(WeeklyMenu(**item))

        # 2. A La Carte Items
        print("🌱 Seeding A La Carte items...")
        for item in SAMPLE_ALA_CARTE:
            stmt = select(AlaCarte).where(AlaCarte.item_name == item["item_name"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.price = item["price"]
                existing.timing_window = item["timing_window"]
                existing.is_available = item["is_available"]
            else:
                session.add(AlaCarte(**item))

        # 3. Rich Food Items Catalogue
        print("🌱 Seeding Rich Food Items catalogue...")
        for item in SAMPLE_FOOD_ITEMS:
            stmt = select(FoodItem).where(FoodItem.id == item["id"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.price = item["price"]
                existing.name = item["name"]
                existing.desc = item["desc"]
                existing.category = item["category"]
                existing.veg = item["veg"]
                existing.is_available = item["is_available"]
                existing.prep_mins = item["prep_mins"]
                existing.rating = item["rating"]
                existing.tag = item.get("tag")
                existing.emoji = item["emoji"]
                existing.photo = item["photo"]
                existing.customizations = item["customizations"]
            else:
                session.add(FoodItem(**item, timing_window="all_day"))

        # 4. Student Accounts
        print("🌱 Seeding Demo Student accounts...")
        for s in SAMPLE_DEMO_STUDENTS:
            stmt = select(StudentUser).where(StudentUser.roll_number == s["roll_number"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if not existing:
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

        await session.commit()

        # 5. Sample Orders for Aarav (#1042 Preparing, #1031 Completed)
        print("🌱 Seeding Sample Orders & Live Tracking...")
        aarav_stmt = select(StudentUser).where(StudentUser.roll_number == "21CS1042")
        aarav_res = await session.execute(aarav_stmt)
        aarav = aarav_res.scalar_one_or_none()

        if aarav:
            existing_ord = await session.execute(select(Order).where(Order.order_number == "#1042"))
            if not existing_ord.scalar_one_or_none():
                now = datetime.now(timezone.utc)
                order_1042 = Order(
                    order_number="#1042",
                    student_id=aarav.id,
                    items_json=[
                        {"id": "veg-burger", "name": "Veg Burger", "qty": 1, "price": 60.0},
                        {"id": "cold-coffee", "name": "Cold Coffee", "qty": 1, "price": 50.0},
                        {"id": "french-fries", "name": "French Fries", "qty": 1, "price": 55.0},
                    ],
                    item_total=165.0,
                    packaging_fee=8.0,
                    gst_amount=8.25,
                    total_amount=181.25,
                    payment_method="UPI",
                    payment_status="Paid",
                    order_status="Preparing",
                    pickup_counter="Counter 2",
                    pickup_token="1042",
                    queue_position=4,
                    prep_time_minutes=8,
                    estimated_ready_at=now + timedelta(minutes=5),
                    qr_code_data="SCO-ORDER-#1042",
                )
                session.add(order_1042)

                order_1031 = Order(
                    order_number="#1031",
                    student_id=aarav.id,
                    items_json=[
                        {"id": "masala-maggi", "name": "Masala Maggi", "qty": 2, "price": 40.0},
                        {"id": "tea", "name": "Masala Tea", "qty": 2, "price": 15.0},
                    ],
                    item_total=110.0,
                    packaging_fee=8.0,
                    gst_amount=5.5,
                    total_amount=123.5,
                    payment_method="Wallet",
                    payment_status="Paid",
                    order_status="Completed",
                    pickup_counter="Counter 2",
                    pickup_token="1031",
                    queue_position=1,
                    prep_time_minutes=6,
                    estimated_ready_at=now - timedelta(hours=2),
                    completed_at=now - timedelta(hours=2),
                    qr_code_data="SCO-ORDER-#1031",
                )
                session.add(order_1031)

                # Add sample notification
                note_1 = Notification(
                    student_id=aarav.id,
                    title="Order #1042 is being prepared 👨‍🍳",
                    body="You’re 4th in the queue · ready in ~5 min.",
                    notification_type="order_update",
                    emoji="👨‍🍳",
                    color_theme="tangerine",
                    is_read=False,
                )
                session.add(note_1)

                note_2 = Notification(
                    student_id=aarav.id,
                    title="Order #1042 placed ✅",
                    body="Payment of ₹181.25 successful via Campus UPI.",
                    notification_type="order_update",
                    emoji="✅",
                    color_theme="slate",
                    is_read=True,
                )
                session.add(note_2)

                # Add sample transaction
                txn_1 = WalletTransaction(
                    student_id=aarav.id,
                    amount=500.0,
                    transaction_type="credit",
                    payment_method="UPI",
                    description="Wallet Recharge via Campus UPI",
                    status="success",
                )
                session.add(txn_1)

                # Add sample feedback review
                review = FeedbackReview(
                    student_id=aarav.id,
                    feedback_type="order",
                    rating=5,
                    comment="Burger was hot and crispy, cold coffee was thick and chilled!",
                    tags=["Delicious", "Fast Service"],
                )
                session.add(review)

        await session.commit()
        print("✅ Database successfully seeded with full weekly schedule, food catalogue, student accounts, orders, and notifications!")


if __name__ == "__main__":
    asyncio.run(seed())
