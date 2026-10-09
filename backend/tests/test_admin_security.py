from datetime import timedelta
import pytest
from sqlalchemy import select

from auth import create_access_token
from config import settings
from models import AdminUser, Notification, Order
from test_mess import mess_client


@pytest.fixture(autouse=True)
def disable_admission_in_security_fixtures(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)


async def test_admin_login_and_session_security(mess_client):
    client, sessions, _ = mess_client
    for headers in ({}, {"Authorization": "Bearer " + create_access_token({"sub": "linked-student", "role": "student"})}, {"Authorization": "Bearer " + create_access_token({"sub": "test-admin", "role": "admin"}, timedelta(seconds=-1))}):
        assert (await client.get("/api/admin/me", headers=headers if headers else {"Authorization": ""})).status_code in (401, 403)
    assert (await client.post("/api/admin/login", json={"username": "test-admin", "password": "wrong"})).status_code == 401
    login = await client.post("/api/admin/login", json={"username": "test-admin", "password": "test-password"})
    assert login.status_code == 200
    assert (await client.get("/api/admin/me")).json()["username"] == "test-admin"
    async with sessions() as db:
        admin = (await db.execute(select(AdminUser))).scalar_one()
        admin.is_active = False
        await db.commit()
    assert (await client.get("/api/admin/me")).status_code == 403
    assert (await client.post("/api/admin/login", json={"username": "test-admin", "password": "test-password"})).status_code == 403


async def test_order_status_requires_admin_and_preserves_legal_lifecycle(mess_client):
    client, sessions, _ = mess_client
    async with sessions() as db:
        order = Order(order_number="#SECURITY", student_id="linked-student", item_total=55, total_amount=55, items_json=[],
                      order_status="Queued", payment_status="Paid", payment_method="wallet")
        db.add(order)
        await db.commit()
        order_id = order.id
    path = f"/api/admin/orders/{order_id}/status"
    assert (await client.post(path, json={"status": "Ready"}, headers={"Authorization": ""})).status_code == 401
    student_header = {"Authorization": "Bearer " + create_access_token({"sub": "linked-student", "role": "student"})}
    assert (await client.post(path, json={"status": "Ready"}, headers=student_header)).status_code == 403
    assert (await client.post(f"/api/student/orders/{order_id}/status", json={"status": "Ready"}, headers=student_header)).status_code == 404
    assert (await client.post(path, json={"status": "Unsupported"})).status_code == 422
    assert (await client.post(path, json={"status": "Ready"})).status_code == 409
    assert (await client.post(path, json={"status": "Preparing"})).status_code == 200
    ready = await client.post(path, json={"status": "Ready"})
    assert ready.status_code == 200
    assert ready.json()["readyAt"]
    repeated = await client.post(path, json={"status": "Ready"})
    assert repeated.status_code == 200
    assert repeated.json()["readyAt"] == ready.json()["readyAt"]
    async with sessions() as db:
        notifications = (await db.execute(select(Notification).where(Notification.order_id == order_id))).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].student_id == "linked-student"
    for state in ("Picked Up", "Completed"):
        response = await client.post(path, json={"status": state})
        assert response.status_code == 200
        assert response.json()["status"] == state
    assert (await client.post(path, json={"status": "Cancelled", "cancellationReason": "Too late"})).status_code == 409
    async with sessions() as db:
        saved = await db.get(Order, order_id)
        assert saved.completed_at
        assert saved.order_status == "Completed"
