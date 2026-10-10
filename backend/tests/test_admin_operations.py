"""Operational APIs read the shared PostgreSQL data rather than UI fixtures."""
from datetime import datetime,timezone
import pytest
from auth import create_access_token
from models import Order
from test_mess import mess_client
import admin_operations
import student_routes
from config import settings
from image_fixtures import attach_test_image

@pytest.fixture(autouse=True)
def isolated_menu_cache(monkeypatch):
    monkeypatch.setattr(settings,"PUBLIC_API_ORIGIN","http://test")
    async def nothing(*args,**kwargs): return None
    monkeypatch.setattr(admin_operations,"cache_invalidate_prefix",nothing)
    for name in ("cache_get","cache_set","cache_invalidate_prefix"):
        monkeypatch.setattr(student_routes,name,nothing)

async def test_operations_require_admin(mess_client):
    client,_,_=mess_client
    for path in ("/catalogue","/orders","/analytics","/operations/status"):
        assert (await client.get("/api/admin"+path,headers={"Authorization":""})).status_code==401
    student={"Authorization":"Bearer "+create_access_token({"sub":"linked-student","role":"student"})}
    assert (await client.get("/api/admin/catalogue",headers=student)).status_code==403

async def test_catalogue_is_shared_with_student_menu_and_soft_delete(mess_client):
    client,sessions,_=mess_client
    from models import FoodItem
    async with sessions() as db:
        photo=await attach_test_image(db,FoodItem(name="Real catalogue snack"))
        await db.commit()
    payload={"imageId":photo.id,"imageConfirmed":True,"name":"Real catalogue snack","price":25.50,"category":"Snacks","timingWindow":"all_day","available":True}
    created=await client.post("/api/admin/catalogue",json=payload)
    assert created.status_code==201,created.text
    item=created.json(); item_id=item["id"]
    assert item["price"]==25.50 and item["timingWindow"]=="all_day"
    assert any(row["id"]==item_id for row in (await client.get("/api/menu/items")).json())
    changed=await client.put("/api/admin/catalogue/"+item_id,json={"price":30,"name":"Updated snack","imageConfirmed":True})
    assert changed.status_code==200 and changed.json()["price"]==30
    assert (await client.patch("/api/admin/catalogue/"+item_id+"/availability",json={"available":False})).json()["available"] is False
    assert (await client.delete("/api/admin/catalogue/"+item_id)).status_code==200
    assert any(row["id"]==item_id and not row["available"] for row in (await client.get("/api/admin/catalogue")).json())
    from sqlalchemy import select,func
    from models import FoodItem
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(FoodItem).where(FoodItem.id==item_id))).scalar_one()==1

async def test_catalogue_validates_money_and_window(mess_client):
    client,_,_=mess_client
    for payload in ({"name":"Negative","price":-1},{"name":"Fraction","price":1.005},{"name":"Window","price":10,"timingWindow":"25:00-28:00"}):
        assert (await client.post("/api/admin/catalogue",json=payload)).status_code==422
    assert (await client.get("/api/admin/orders?limit=201")).status_code==422
    for category in ("Snacks","Meals","Beverages","Desserts","Quick Bites"):
        response=await client.post("/api/admin/catalogue",json={"name":"Category fixture "+category,"price":10,"category":category})
        assert response.status_code==201,response.text
        assert response.json()["category"]==category

async def test_order_identity_and_analytics_use_real_paid_rows(mess_client):
    client,sessions,_=mess_client
    async with sessions() as db:
        for number,status,payment,total in [("#OPS1","Queued","Paid",25),("#OPS2","Cancelled","Refunded",99),("#OPS3","Payment Pending","Pending",40)]:
            db.add(Order(order_number=number,student_id="linked-student",items_json=[{"name":"Actual rice","qty":1,"price":25}],item_total=total,total_amount=total,order_status=status,payment_status=payment,created_at=datetime.now(timezone.utc)))
        await db.commit()
    rows=(await client.get("/api/admin/orders")).json()
    assert len(rows)==3
    assert all(row["studentName"]=="Aarav Sharma" and row["rollNumber"]=="21CS1042" for row in rows)
    assert len((await client.get("/api/admin/orders?status=Queued")).json())==1
    stats=(await client.get("/api/admin/analytics")).json()
    assert stats["dailyRevenue"]==25
    assert stats["totalOrders"]==3 and stats["activeOrders"]==1
    assert stats["topItems"]==[{"name":"Actual rice","quantity":1,"revenue":25}]
    assert stats["redisCacheHitPercent"] is None and stats["wasteReductionPercent"] is None


async def test_optional_qa_credit_is_disabled_and_admin_only(mess_client,monkeypatch):
    client,_,_=mess_client
    monkeypatch.setattr(settings,"STAGING_QA_WALLET_ENABLED",False)
    assert (await client.post("/api/admin/qa-wallet-credit")).status_code==404
    assert (await client.post("/api/admin/qa-wallet-credit",headers={"Authorization":""})).status_code==401
    token=create_access_token({"sub":"linked-student","role":"student"})
    assert (await client.post("/api/admin/qa-wallet-credit",headers={"Authorization":"Bearer "+token})).status_code==403


async def test_qa_credit_database_gate_requires_staging_exact_identity_and_database(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    class Result:
        def scalar_one(self): return self.name
    class Database:
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        async def execute(self,query):
            result=Result(); result.name=self.name; return result
    db=Database(); db.name="canteen_staging"
    monkeypatch.setattr(settings,"STAGING_QA_WALLET_ENABLED",True)
    monkeypatch.setattr(settings,"STAGING_QA_STUDENT_ID","known-synthetic-qa")
    monkeypatch.setattr(settings,"STAGING_QA_STUDENT_ROLL","STGQA123456")
    monkeypatch.setattr(settings,"DEPLOYMENT_TIER","staging")
    monkeypatch.setattr(settings,"PAYMENT_PROVIDER","disabled")
    await admin_operations.require_staging_qa_credit_database(db)
    for field,value in (("DEPLOYMENT_TIER","production"),("STAGING_QA_STUDENT_ID",""),("STAGING_QA_STUDENT_ROLL",""),("PAYMENT_PROVIDER","razorpay")):
        previous=getattr(settings,field); monkeypatch.setattr(settings,field,value)
        with pytest.raises(HTTPException) as error:
            await admin_operations.require_staging_qa_credit_database(db)
        assert error.value.status_code==404
        monkeypatch.setattr(settings,field,previous)
    db.name="actual_production"
    with pytest.raises(HTTPException) as error:
        await admin_operations.require_staging_qa_credit_database(db)
    assert error.value.status_code==404


async def test_qa_credit_ignores_arbitrary_identity_and_uses_exact_configured_account(mess_client,monkeypatch):
    client,sessions,_=mess_client
    from models import StudentUser
    import staging_wallet
    async with sessions() as db:
        student=await db.get(StudentUser,"linked-student")
        student.name="STAGING QA Student"; student.roll_number="STGQA123456"
        await db.commit()
    monkeypatch.setattr(settings,"STAGING_QA_STUDENT_ID","linked-student")
    monkeypatch.setattr(settings,"STAGING_QA_STUDENT_ROLL","STGQA123456")
    async def fake_guard(db): pass
    monkeypatch.setattr(admin_operations,"require_staging_qa_credit_database",fake_guard)
    calls=[]
    async def fake_credit(db,student_id,roll):
        calls.append((student_id,roll)); return {"credited":False}
    monkeypatch.setattr(staging_wallet,"credit_staging_qa_wallet",fake_credit)
    result=await client.post("/api/admin/qa-wallet-credit",json={"student_id":"another-account","amount":99999})
    assert result.status_code==200 and calls==[("linked-student","STGQA123456")]
    monkeypatch.setattr(settings,"STAGING_QA_STUDENT_ROLL","STGQA999999")
    assert (await client.post("/api/admin/qa-wallet-credit")).status_code==404 and len(calls)==1
