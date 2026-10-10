"""Money, lifecycle and webhook assertions use isolated schemas, never real payments."""
import asyncio
import hashlib
import hmac
import json
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select,func
from auth import create_access_token,credential_fingerprint
from config import settings
from models import FoodItem,StudentUser,Order,Notification,WalletTransaction
from payment_models import PaymentIntent,PaymentEvent
from payment_provider import provider
from test_mess import mess_client
from image_fixtures import attach_test_image

async def prepare(fixture,balance=200):
    client,sessions,postgres=fixture
    async with sessions() as db:
        student=await db.get(StudentUser,"linked-student")
        student.wallet_balance=Decimal(str(balance))
        item=FoodItem(id="financial-test-food",name="Financial Test Food",price=60,category="Snacks",is_available=True,timing_window="all_day",customizations=[{"name":"Extra cheese","price":10}])
        db.add(item)
        await attach_test_image(db,item)
        await db.commit()
        token=create_access_token({"sub":student.id,"role":"student","credential_version":credential_fingerprint(student.hashed_passcode)})
    return {"Authorization":"Bearer "+token}

def payload(method="wallet",**changes):
    return {"items":[{"id":"financial-test-food","qty":1,"price":0.01,"name":"Forged client name"}],"paymentMethod":method,**changes}

async def place(client,headers,key=None,body=None):
    return await client.post("/api/student/orders",headers={**headers,"Idempotency-Key":key or uuid.uuid4().hex},json=body or payload())

async def test_authoritative_prices_and_idempotency(mess_client):
    client,sessions,_=mess_client
    headers=await prepare(mess_client)
    key=uuid.uuid4().hex
    first=await place(client,headers,key)
    assert first.status_code==201,first.text
    assert first.json()["total"]==60
    assert first.json()["packagingFee"]==first.json()["gst"]==0
    assert first.json()["items"][0]["name"]=="Financial Test Food"
    again=await place(client,headers,key)
    assert again.json()["orderId"]==first.json()["orderId"]
    changed=payload();changed["items"][0]["qty"]=2
    assert (await place(client,headers,key,changed)).status_code==409
    async with sessions() as db:
        assert (await db.get(StudentUser,"linked-student")).wallet_balance==Decimal("140.00")
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one()==1

async def test_validation_unavailable_and_no_fake_money(mess_client,monkeypatch):
    client,sessions,_=mess_client
    headers=await prepare(mess_client)
    monkeypatch.setattr(settings,"PAYMENT_PROVIDER","disabled")
    assert (await client.post("/api/student/orders",headers=headers,json=payload())).status_code==422
    assert (await place(client,headers,body=payload("upi"))).status_code==503
    assert (await client.post("/api/student/wallet/recharge",headers=headers,json={"amount":100,"paymentMethod":"UPI"})).status_code==503
    body=payload();body["paymentStatus"]="Paid"
    assert (await place(client,headers,body=body)).status_code==422
    body=payload();body["items"][0]["customizations"]=["Invented free topping"]
    assert (await place(client,headers,body=body)).status_code==422
    async with sessions() as db:
        item=await db.get(FoodItem,"financial-test-food");item.is_available=False;await db.commit()
    assert (await place(client,headers)).status_code==409

async def test_legal_lifecycle_and_single_refund(mess_client):
    client,sessions,_=mess_client
    headers=await prepare(mess_client)
    order=(await place(client,headers)).json();oid=order["orderId"]
    path=f"/api/admin/orders/{oid}/status"
    assert (await client.post(path,json={"status":"Ready"})).status_code==409
    assert (await client.post(f"/api/student/orders/{oid}/pickup",headers=headers)).status_code==409
    for _ in range(2):
        response=await client.post(f"/api/student/orders/{oid}/cancel",headers=headers)
        assert response.status_code==200,response.text
    async with sessions() as db:
        assert (await db.get(StudentUser,"linked-student")).wallet_balance==Decimal("200.00")
        assert (await db.execute(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.transaction_type=="credit"))).scalar_one()==1
    assert (await client.post(path,json={"status":"Preparing"})).status_code==409

async def test_ready_notifications_are_idempotent(mess_client):
    client,sessions,_=mess_client;headers=await prepare(mess_client)
    oid=(await place(client,headers)).json()["orderId"]
    path=f"/api/admin/orders/{oid}/status"
    assert (await client.post(path,json={"status":"Preparing"})).status_code==200
    first=await client.post(path,json={"status":"Ready"})
    second=await client.post(path,json={"status":"Ready"})
    assert first.json()["readyAt"]==second.json()["readyAt"]
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(Notification).where(Notification.order_id==oid,Notification.title.like("Your food is ready%")))).scalar_one()==1
    assert (await client.post(f"/api/student/orders/{oid}/pickup",headers=headers)).json()["status"]=="Picked Up"
    assert (await client.post(path,json={"status":"Completed"})).status_code==200

@pytest.mark.parametrize("same_key",[False,True])
async def test_postgres_wallet_concurrency(mess_client,same_key):
    client,sessions,postgres=mess_client
    if not postgres:pytest.skip("True row-lock verification requires PostgreSQL")
    headers=await prepare(mess_client,balance=60)
    key=uuid.uuid4().hex
    results=await asyncio.gather(place(client,headers,key),place(client,headers,key if same_key else uuid.uuid4().hex))
    assert sorted(r.status_code for r in results)==([201,201] if same_key else [201,400])
    async with sessions() as db:
        assert (await db.get(StudentUser,"linked-student")).wallet_balance==Decimal("0.00")
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one()==1
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one()==1

async def gateway(mess_client,monkeypatch):
    headers=await prepare(mess_client)
    monkeypatch.setattr(settings,"PAYMENT_PROVIDER","razorpay")
    monkeypatch.setattr(settings,"RAZORPAY_KEY_ID","test_public_key")
    monkeypatch.setattr(settings,"RAZORPAY_KEY_SECRET","isolated-test-key")
    monkeypatch.setattr(settings,"RAZORPAY_WEBHOOK_SECRET","isolated-webhook-key")
    async def fake_order(amount,receipt,order_id):return {"id":"order_Test123","amount":amount,"currency":"INR","receipt":receipt}
    monkeypatch.setattr(provider,"create_order",fake_order)
    order=await place(mess_client[0],headers,body=payload("razorpay"))
    assert order.status_code==201,order.text
    return headers,order.json()

async def test_verified_capture_and_duplicate_callbacks(mess_client,monkeypatch):
    client,sessions,_=mess_client;headers,order=await gateway(mess_client,monkeypatch)
    assert order["payment"]=="Pending" and order["status"]=="Payment Pending"
    payment={"id":"pay_Test123","order_id":"order_Test123","amount":6000,"currency":"INR","status":"captured","captured":True}
    async def fetch(_):return payment
    monkeypatch.setattr(provider,"fetch_payment",fetch)
    path=f'/api/student/orders/{order["orderId"]}/payment/verify'
    signature=hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),b"order_Test123|pay_Test123",hashlib.sha256).hexdigest()
    body={"razorpay_order_id":"order_Test123","razorpay_payment_id":"pay_Test123","razorpay_signature":signature}
    assert (await client.post(path,headers=headers,json={**body,"razorpay_signature":"0"*64})).status_code==400
    payment["amount"]=7000
    assert (await client.post(path,headers=headers,json=body)).status_code==409
    payment["amount"]=6000
    for _ in range(2):
        result=await client.post(path,headers=headers,json=body)
        assert result.status_code==200,result.text
        assert result.json()["payment"]=="Paid" and result.json()["status"]=="Queued"
    raw=json.dumps({"event":"payment.captured","payload":{"payment":{"entity":payment}}},separators=(",",":")).encode()
    webhook_headers={"X-Razorpay-Event-Id":"event_test123","X-Razorpay-Signature":hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(),raw,hashlib.sha256).hexdigest(),"Content-Type":"application/json"}
    assert (await client.post("/api/payments/webhooks/razorpay",content=raw,headers={**webhook_headers,"X-Razorpay-Signature":"bad"})).status_code==400
    assert (await client.post("/api/payments/webhooks/razorpay",content=raw,headers=webhook_headers)).status_code==200
    assert (await client.post("/api/payments/webhooks/razorpay",content=raw,headers=webhook_headers)).json()["duplicate"]
    async with sessions() as db:
        student=await db.get(StudentUser,"linked-student")
        assert student.wallet_balance==Decimal("200.00") and student.total_orders==1 and student.total_spent==Decimal("60.00")
        assert (await db.execute(select(func.count()).select_from(PaymentEvent))).scalar_one()==1

async def test_authorized_payment_is_not_paid(mess_client,monkeypatch):
    client,sessions,_=mess_client;headers,order=await gateway(mess_client,monkeypatch)
    async def fetch(_):return {"id":"pay_Test123","order_id":"order_Test123","amount":6000,"currency":"INR","status":"authorized","captured":False}
    monkeypatch.setattr(provider,"fetch_payment",fetch)
    signature=hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),b"order_Test123|pay_Test123",hashlib.sha256).hexdigest()
    result=await client.post(f'/api/student/orders/{order["orderId"]}/payment/verify',headers=headers,json={"razorpay_order_id":"order_Test123","razorpay_payment_id":"pay_Test123","razorpay_signature":signature})
    assert result.status_code==409
    async with sessions() as db:assert (await db.get(Order,order["orderId"])).payment_status=="Pending"

async def test_broadcast_read_is_private(mess_client):
    client,sessions,_=mess_client;headers=await prepare(mess_client)
    async with sessions() as db:
        db.add(StudentUser(id="other-student",roll_number="QAOTHER",name="Other Student",email="other@test.invalid",hashed_passcode="unused"))
        note=Notification(title="Campus notice",body="General announcement",student_id=None);db.add(note);await db.commit();nid=note.id
    other={"Authorization":"Bearer "+create_access_token({"sub":"other-student","role":"student","credential_version":credential_fingerprint("unused")})}
    assert (await client.post(f"/api/student/notifications/{nid}/read",headers=headers)).status_code==200
    first=(await client.get("/api/student/notifications",headers=headers)).json()
    second=(await client.get("/api/student/notifications",headers=other)).json()
    assert next(n for n in first if n["id"]==nid)["unread"] is False
    assert next(n for n in second if n["id"]==nid)["unread"] is True
