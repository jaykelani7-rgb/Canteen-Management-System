import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app


@pytest_asyncio.fixture(scope="session")
async def client():
    """Session-scoped AsyncClient for super fast test execution on shared event loop."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def auth_headers(client: AsyncClient):
    """Provides valid JWT Bearer authentication headers for test student Aarav."""
    login_resp = await client.post(
        "/api/auth/login",
        json={"rollNumber": "21CS1042", "passcode": "000000"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# 1. SYSTEM HEALTH & METRICS
# =========================================================================
@pytest.mark.asyncio
async def test_system_health(client: AsyncClient):
    """Verify backend system health and database/redis connectivity."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "database" in data


@pytest.mark.asyncio
async def test_system_root(client: AsyncClient):
    """Verify root index metadata."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert "endpoints" in data


# =========================================================================
# 2. STUDENT AUTHENTICATION TESTS
# =========================================================================
@pytest.mark.asyncio
async def test_student_registration_success(client: AsyncClient):
    """Test registering a new student with welcome bonus."""
    unique_suffix = uuid.uuid4().hex[:6].upper()
    unique_roll = f"24CS{unique_suffix}"
    payload = {
        "rollNumber": unique_roll,
        "name": "Kavya Singhania",
        "branch": "B.Tech Computer Science & Eng.",
        "phone": "+91 98765 12345",
        "email": f"kavya.{unique_roll.lower()}@campus.edu",
        "passcode": "pass1234",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["token"] is not None
    assert data["user"]["rollNumber"] == unique_roll
    assert data["user"]["walletBalance"] == 250.0  # ₹250 signup bonus


@pytest.mark.asyncio
async def test_student_registration_duplicate_prevented(client: AsyncClient):
    """Test duplicate registration error."""
    payload = {
        "rollNumber": "21CS1042",  # already exists
        "name": "Duplicate Aarav",
        "passcode": "pass1234",
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_student_login_success(client: AsyncClient):
    """Test student login with valid credentials."""
    resp = await client.post(
        "/api/auth/login",
        json={"rollNumber": "21CS1042", "passcode": "000000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["token"] is not None
    assert data["user"]["name"] == "Aarav Sharma"


@pytest.mark.asyncio
async def test_student_login_invalid_passcode(client: AsyncClient):
    """Test login failure with incorrect passcode."""
    resp = await client.post(
        "/api/auth/login",
        json={"rollNumber": "21CS1042", "passcode": "wrongpasscode99"},
    )
    assert resp.status_code == 401
    assert "incorrect passcode" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_student_login_nonexistent_roll(client: AsyncClient):
    """Test login failure for nonexistent roll number."""
    resp = await client.post(
        "/api/auth/login",
        json={"rollNumber": "99ZZ9999", "passcode": "000000"},
    )
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_demo_users(client: AsyncClient):
    """Test fetching pre-seeded demo student accounts."""
    resp = await client.get("/api/auth/demo-users")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["users"]) >= 4


# =========================================================================
# 3. PASSCODE RESET OTP FLOW
# =========================================================================
@pytest.mark.asyncio
async def test_passcode_reset_otp_flow(client: AsyncClient):
    """Test end-to-end OTP request and passcode update flow."""
    # 1. Request OTP
    req_resp = await client.post(
        "/api/auth/forgot-passcode",
        json={"rollNumber": "21IT2015"},
    )
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert req_data["success"] is True
    otp_code = req_data.get("otp") or "123456"

    # 2. Reset Passcode with OTP
    reset_resp = await client.post(
        "/api/auth/reset-passcode",
        json={
            "rollNumber": "21IT2015",
            "otp": otp_code,
            "newPasscode": "newpass789",
        },
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["success"] is True

    # 3. Verify login with newly set passcode
    login_resp = await client.post(
        "/api/auth/login",
        json={"rollNumber": "21IT2015", "passcode": "newpass789"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["success"] is True


# =========================================================================
# 4. STUDENT PROFILE & PREFERENCES
# =========================================================================
@pytest.mark.asyncio
async def test_get_current_student_profile(client: AsyncClient, auth_headers: dict):
    """Test GET /api/auth/me with JWT bearer token."""
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["user"]["rollNumber"] == "21CS1042"
    assert "walletBalance" in data["user"]


@pytest.mark.asyncio
async def test_update_student_profile(client: AsyncClient, auth_headers: dict):
    """Test updating student profile attributes and dietary preference."""
    update_payload = {
        "phone": "+91 98765 44332",
        "dietaryPreference": "veg",
    }
    resp = await client.put(
        "/api/student/profile",
        json=update_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["user"]["dietaryPreference"] == "veg"
    assert data["user"]["phone"] == "+91 98765 44332"


# =========================================================================
# 5. FOOD MENU & FAVORITES TESTS
# =========================================================================
@pytest.mark.asyncio
async def test_get_food_items(client: AsyncClient):
    """Test retrieving food items catalogue."""
    resp = await client.get("/api/menu/items")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 6
    assert any(i["id"] == "veg-burger" for i in items)


@pytest.mark.asyncio
async def test_get_food_items_filtered_by_category(client: AsyncClient):
    """Test filtering menu items by category."""
    resp = await client.get("/api/menu/items?category=Beverages")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    assert all(i["category"].lower() == "beverages" for i in items)


@pytest.mark.asyncio
async def test_get_food_items_search(client: AsyncClient):
    """Test searching food items by keyword."""
    resp = await client.get("/api/menu/items?query=burger")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert "burger" in items[0]["name"].lower()


@pytest.mark.asyncio
async def test_get_food_item_detail(client: AsyncClient):
    """Test getting single food item detail with customizations."""
    resp = await client.get("/api/menu/items/veg-burger")
    assert resp.status_code == 200
    item = resp.json()
    assert item["id"] == "veg-burger"
    assert item["price"] == 60.0
    assert len(item["customizations"]) >= 1


@pytest.mark.asyncio
async def test_toggle_and_get_favorites(client: AsyncClient, auth_headers: dict):
    """Test toggling item favorite and getting favorites list."""
    # 1. Toggle favorite
    resp = await client.post(
        "/api/student/favorites/paneer-wrap",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # 2. Retrieve favorites
    fav_resp = await client.get("/api/student/favorites", headers=auth_headers)
    assert fav_resp.status_code == 200
    fav_items = fav_resp.json()
    assert isinstance(fav_items, list)


# =========================================================================
# 6. WALLET & RECHARGE TESTS
# =========================================================================
@pytest.mark.asyncio
async def test_get_wallet_balance(client: AsyncClient, auth_headers: dict):
    """Test fetching wallet balance."""
    resp = await client.get("/api/student/wallet", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "walletBalance" in data
    assert "upiId" in data
    assert data["walletBalance"] >= 0


@pytest.mark.asyncio
async def test_wallet_recharge(client: AsyncClient, auth_headers: dict):
    """Test recharging wallet with funds and ledger tracking."""
    recharge_amount = 150.0
    b_before = (await client.get("/api/student/wallet", headers=auth_headers)).json()["walletBalance"]

    resp = await client.post(
        "/api/student/wallet/recharge",
        json={"amount": recharge_amount, "paymentMethod": "UPI"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["walletBalance"] == pytest.approx(b_before + recharge_amount, 0.01)

    # Verify transaction ledger
    txns_resp = await client.get("/api/student/wallet/transactions", headers=auth_headers)
    assert txns_resp.status_code == 200
    txns = txns_resp.json()
    assert len(txns) >= 1
    assert txns[0]["type"] == "credit"
    assert txns[0]["amount"] == recharge_amount


# =========================================================================
# 7. ORDER PLACEMENT & LIVE TRACKING TESTS
# =========================================================================
@pytest.mark.asyncio
async def test_place_order_with_wallet(client: AsyncClient, auth_headers: dict):
    """Test placing a food order paying via Canteen Wallet."""
    # Ensure sufficient balance
    await client.post(
        "/api/student/wallet/recharge",
        json={"amount": 300.0, "paymentMethod": "UPI"},
        headers=auth_headers,
    )

    order_payload = {
        "items": [
            {"id": "veg-burger", "name": "Veg Burger", "qty": 1, "price": 60.0, "customizations": ["Extra cheese"]},
            {"id": "tea", "name": "Masala Tea", "qty": 1, "price": 15.0},
        ],
        "paymentMethod": "wallet",
        "specialInstructions": "Make tea extra hot",
    }

    resp = await client.post(
        "/api/student/orders",
        json=order_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    order = resp.json()
    assert "number" in order
    assert order["payment"] == "Paid"
    assert order["paymentMethod"] == "wallet"
    assert order["pickupCounter"] == "Counter 2"
    assert order["queuePosition"] >= 1
    assert len(order["items"]) == 2

    # Verify live tracking endpoint
    order_id = order["orderId"]
    track_resp = await client.get(
        f"/api/student/orders/{order_id}/tracking",
        headers=auth_headers,
    )
    assert track_resp.status_code == 200
    track_data = track_resp.json()
    assert track_data["orderNumber"] == order["number"]
    assert "countdownSeconds" in track_data
    assert len(track_data["timeline"]) == 6


@pytest.mark.asyncio
async def test_place_order_with_upi(client: AsyncClient, auth_headers: dict):
    """Test placing a food order paying via Campus UPI."""
    order_payload = {
        "items": [
            {"id": "cold-coffee", "name": "Cold Coffee", "qty": 2, "price": 50.0},
        ],
        "paymentMethod": "UPI",
    }
    resp = await client.post(
        "/api/student/orders",
        json=order_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    order = resp.json()
    assert order["paymentMethod"] == "UPI"
    assert order["payment"] == "Paid"


@pytest.mark.asyncio
async def test_get_student_orders_list(client: AsyncClient, auth_headers: dict):
    """Test listing student orders with active/past filter."""
    resp = await client.get("/api/student/orders?filter_type=all", headers=auth_headers)
    assert resp.status_code == 200
    orders = resp.json()
    assert len(orders) >= 1


# =========================================================================
# 8. ORDER CANCELLATION & WALLET REFUND TEST
# =========================================================================
@pytest.mark.asyncio
async def test_order_cancellation_and_auto_refund(client: AsyncClient, auth_headers: dict):
    """Test cancelling an active order and receiving an automatic wallet refund."""
    # Place an order via wallet
    order_payload = {
        "items": [{"id": "masala-maggi", "name": "Masala Maggi", "qty": 1, "price": 40.0}],
        "paymentMethod": "wallet",
    }
    create_resp = await client.post("/api/student/orders", json=order_payload, headers=auth_headers)
    assert create_resp.status_code == 201
    created_order = create_resp.json()
    order_id = created_order["orderId"]
    total_paid = created_order["total"]

    # Balance before cancel
    w_before = (await client.get("/api/student/wallet", headers=auth_headers)).json()["walletBalance"]

    # Cancel the order
    cancel_resp = await client.post(
        f"/api/student/orders/{order_id}/cancel?reason=Changed+mind",
        headers=auth_headers,
    )
    assert cancel_resp.status_code == 200
    cancelled_order = cancel_resp.json()
    assert cancelled_order["status"] == "Cancelled"
    assert cancelled_order["payment"] == "Refunded"

    # Balance after cancel must be refunded
    w_after = (await client.get("/api/student/wallet", headers=auth_headers)).json()["walletBalance"]
    assert w_after == pytest.approx(w_before + total_paid, 0.01)


# =========================================================================
# 9. ORDER STATUS SIMULATION & PICKUP COMPLETION
# =========================================================================
@pytest.mark.asyncio
async def test_order_status_progression_and_pickup(client: AsyncClient, auth_headers: dict):
    """Test updating order to Ready and then picking up / completing."""
    order_payload = {
        "items": [{"id": "french-fries", "name": "French Fries", "qty": 1, "price": 55.0}],
        "paymentMethod": "UPI",
    }
    ord_resp = await client.post("/api/student/orders", json=order_payload, headers=auth_headers)
    order_id = ord_resp.json()["orderId"]

    # 1. Update status to Ready
    ready_resp = await client.post(
        f"/api/student/orders/{order_id}/status",
        json={"status": "Ready"},
        headers=auth_headers,
    )
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "Ready"

    # 2. Mark as picked up by student
    pickup_resp = await client.post(
        f"/api/student/orders/{order_id}/pickup",
        headers=auth_headers,
    )
    assert pickup_resp.status_code == 200
    assert pickup_resp.json()["status"] == "Completed"


# =========================================================================
# 10. REVIEWS & FEEDBACK TESTS
# =========================================================================
@pytest.mark.asyncio
async def test_submit_order_review(client: AsyncClient, auth_headers: dict):
    """Test submitting review for a completed order."""
    orders = (await client.get("/api/student/orders", headers=auth_headers)).json()
    assert len(orders) >= 1
    order_id = orders[0]["orderId"]

    review_payload = {
        "orderId": order_id,
        "rating": 5,
        "comment": "Food was super tasty and piping hot!",
        "tags": ["Fast Service", "Delicious", "Hot"],
    }
    resp = await client.post(
        f"/api/student/orders/{order_id}/review",
        json=review_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rating"] == 5
    assert data["feedbackType"] == "order"


@pytest.mark.asyncio
async def test_submit_mess_meal_feedback(client: AsyncClient, auth_headers: dict):
    """Test submitting qualitative feedback for a scheduled mess meal."""
    feedback_payload = {
        "mealDay": "Monday",
        "mealType": "lunch",
        "rating": 4,
        "comment": "Paneer Butter Masala was very good today!",
        "tags": ["Rich Gravy", "Soft Roti"],
    }
    resp = await client.post(
        "/api/student/feedback/meal",
        json=feedback_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["mealDay"] == "Monday"
    assert data["rating"] == 4


@pytest.mark.asyncio
async def test_get_student_reviews(client: AsyncClient, auth_headers: dict):
    """Test listing all submitted reviews for student."""
    resp = await client.get("/api/student/reviews", headers=auth_headers)
    assert resp.status_code == 200
    reviews = resp.json()
    assert isinstance(reviews, list)
    assert len(reviews) >= 1


# =========================================================================
# 11. NOTIFICATIONS & ALERTS TESTS
# =========================================================================
@pytest.mark.asyncio
async def test_student_notifications_flow(client: AsyncClient, auth_headers: dict):
    """Test fetching notifications, marking single as read, and marking all read."""
    # 1. Fetch notifications
    resp = await client.get("/api/student/notifications", headers=auth_headers)
    assert resp.status_code == 200
    notes = resp.json()
    assert len(notes) >= 1

    # 2. Mark single notification as read
    note_id = notes[0]["id"]
    read_resp = await client.post(
        f"/api/student/notifications/{note_id}/read",
        headers=auth_headers,
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["success"] is True

    # 3. Mark all notifications as read
    all_read_resp = await client.post(
        "/api/student/notifications/mark-all-read",
        headers=auth_headers,
    )
    assert all_read_resp.status_code == 200
    assert all_read_resp.json()["success"] is True


# =========================================================================
# 12. CANTEEN QUEUE STATUS METRICS
# =========================================================================
@pytest.mark.asyncio
async def test_get_canteen_queue_status(client: AsyncClient):
    """Test retrieving live canteen queue load and wait time metrics."""
    resp = await client.get("/api/student/canteen/queue-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "activeOrdersCount" in data
    assert "currentRushLevel" in data
    assert "estimatedWaitMinutes" in data
    assert data["counterOpen"] is True
