"""Admin operations share the authoritative food catalogue and order database."""
import asyncio
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import re
import unicodedata
import uuid
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from auth import get_current_admin
from database import cache_invalidate_prefix,get_db,get_redis_client
from models import AdminUser,FoodItem,Order,OrderStatusEnum,StudentUser
from schemas import FoodItemResponse
from image_service import apply_catalogue_image

IST=timezone(timedelta(hours=5,minutes=30))
ACTIVE_STATES=("Queued","Preparing","Ready","Delayed")
admin_operations_router=APIRouter(prefix="/admin",tags=["Admin Operations"])

class CatalogueCustomization(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    name:str=Field(min_length=1,max_length=60)
    price:Decimal=Field(default=Decimal("0"),ge=0,max_digits=12,decimal_places=2)

class CatalogueInput(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    id:str|None=Field(default=None,pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$")
    name:str|None=Field(default=None,min_length=2,max_length=100)
    desc:str|None=Field(default=None,max_length=255)
    price:Decimal|None=Field(default=None,ge=0,max_digits=12,decimal_places=2)
    category:Literal["Snacks","Meals","Beverages","Desserts","Quick Bites"]|None=None
    veg:bool|None=None
    available:bool|None=None
    prepMins:int|None=Field(default=None,ge=1,le=240)
    rating:float|None=Field(default=None,ge=0,le=5)
    tag:str|None=Field(default=None,max_length=50)
    emoji:str|None=Field(default=None,max_length=10)
    photo:str|None=Field(default=None,max_length=500)
    imageId:str|None=Field(default=None,pattern=r"^[a-f0-9]{32}$")
    imageConfirmed:bool|None=None
    calories:int|None=Field(default=None,ge=0,le=10000)
    customizations:list[CatalogueCustomization]|None=Field(default=None,max_length=30)
    timingWindow:str|None=Field(default=None,max_length=50)

    @field_validator("timingWindow")
    @classmethod
    def valid_window(cls,value):
        if value is None or value=="all_day": return value
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d",value):
            raise ValueError("Use all_day or an HH:MM-HH:MM timing window")
        if value[:5]==value[6:]: raise ValueError("Timing window start and end must differ")
        return value

class AvailabilityInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    available:bool
    imageConfirmed:bool|None=None

def catalogue_values(payload):
    if payload.photo:
        raise HTTPException(422,"Select a managed photograph from the image library")
    mapping={"available":"is_available","prepMins":"prep_mins","timingWindow":"timing_window","imageId":"image_id"}
    values={mapping.get(key,key):value for key,value in payload.model_dump(exclude_unset=True).items() if key not in {"id","imageConfirmed","photo"}}
    for key,value in values.items():
        if value is None and key not in {"desc","tag","image_id"}:
            raise HTTPException(422,"Catalogue fields cannot be null")
    if "customizations" in values:
        values["customizations"]=[{"name":option.name,"price":float(option.price)} for option in payload.customizations]
    return values

async def locked_food(db,item_id):
    row=(await db.execute(select(FoodItem).where(FoodItem.id==item_id).with_for_update())).scalar_one_or_none()
    if row is None: raise HTTPException(404,"Catalogue item not found")
    return row

async def save_food(db,row):
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError as cause:
        await db.rollback()
        raise HTTPException(409,"An item with that name or identifier already exists") from cause
    await cache_invalidate_prefix("canteen:food_items:")
    return row.to_dict()

@admin_operations_router.get("/catalogue",response_model=list[FoodItemResponse])
async def catalogue(limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    return [row.to_dict() for row in (await db.execute(select(FoodItem).order_by(FoodItem.name,FoodItem.id).limit(limit).offset(offset))).scalars()]

@admin_operations_router.post("/catalogue",response_model=FoodItemResponse,status_code=201)
async def create_catalogue(payload:CatalogueInput,db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    if payload.name is None or payload.price is None: raise HTTPException(422,"Name and price are required")
    values=catalogue_values(payload)
    slug=re.sub(r"[^a-z0-9]+","-",unicodedata.normalize("NFKD",payload.name).encode("ascii","ignore").decode().lower()).strip("-")[:40] or "food"
    item_id=payload.id or slug+"-"+uuid.uuid4().hex[:8]
    values.setdefault("is_available",False)
    row=FoodItem(id=item_id,**values)
    await apply_catalogue_image(db,row,image_changed="image_id" in values,confirmed=payload.imageConfirmed)
    db.add(row)
    return await save_food(db,row)

@admin_operations_router.put("/catalogue/{item_id}",response_model=FoodItemResponse)
async def update_catalogue(item_id:str,payload:CatalogueInput,db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    if payload.id is not None and payload.id!=item_id: raise HTTPException(422,"Catalogue identifiers cannot change")
    row=await locked_food(db,item_id)
    old_image,old_name=row.image_id,row.name
    for key,value in catalogue_values(payload).items(): setattr(row,key,value)
    await apply_catalogue_image(db,row,image_changed=row.image_id!=old_image,name_changed=row.name!=old_name,confirmed=payload.imageConfirmed)
    return await save_food(db,row)

@admin_operations_router.patch("/catalogue/{item_id}/availability",response_model=FoodItemResponse)
async def update_availability(item_id:str,payload:AvailabilityInput,db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    row=await locked_food(db,item_id)
    row.is_available=payload.available
    if payload.available:
        await apply_catalogue_image(db,row,confirmed=payload.imageConfirmed)
    return await save_food(db,row)

@admin_operations_router.delete("/catalogue/{item_id}",response_model=FoodItemResponse)
async def disable_catalogue(item_id:str,db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    row=await locked_food(db,item_id)
    row.is_available=False
    return await save_food(db,row)

@admin_operations_router.get("/orders")
async def orders(status:OrderStatusEnum|None=None,limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    query=select(Order,StudentUser.name,StudentUser.roll_number).join(StudentUser,StudentUser.id==Order.student_id)
    if status is not None: query=query.where(Order.order_status==status.value)
    rows=(await db.execute(query.order_by(Order.created_at.desc(),Order.id.desc()).limit(limit).offset(offset))).all()
    from payment_models import PaymentIntent, PaymentRefund
    ids = [row.id for row, _, _ in rows]
    refunds = (await db.execute(select(PaymentIntent.order_id, PaymentRefund.state).join(PaymentRefund, PaymentRefund.payment_intent_id == PaymentIntent.id).where(PaymentIntent.order_id.in_(ids)))).all() if ids else []
    refund_states = dict(refunds)
    return [{**row.to_dict(), "studentName":name, "rollNumber":roll, "refundStatus":refund_states.get(row.id)} for row,name,roll in rows]

@admin_operations_router.get("/analytics")
async def analytics(db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    now=datetime.now(IST)
    start=datetime.combine(now.date(),datetime.min.time(),IST)
    previous=start-timedelta(days=1)
    paid=select(Order).where(Order.payment_status=="Paid",Order.order_status!="Cancelled",Order.created_at>=previous,Order.created_at<start+timedelta(days=1))
    rows=(await db.execute(paid)).scalars().all()
    today=[]; yesterday=[]
    for row in rows:
        when=row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
        (today if when>=start else yesterday).append(row)
    popular=defaultdict(lambda:{"quantity":0,"revenue":Decimal("0")})
    for row in today:
        for item in row.items_json:
            try:
                name=str(item["name"]); quantity=int(item["qty"]); price=Decimal(str(item["price"]))
                if quantity<1 or not price.is_finite() or price<0: continue
            except (KeyError,TypeError,ValueError,ArithmeticError): continue
            popular[name]["quantity"]+=quantity
            popular[name]["revenue"]+=price*quantity
    top=sorted([{"name":name,**values} for name,values in popular.items()],key=lambda item:(-item["quantity"],item["name"]))[:10]
    return {"dailyRevenue":sum((row.total_amount for row in today),Decimal("0")),"yesterdayRevenue":sum((row.total_amount for row in yesterday),Decimal("0")),
        "activeStudents":(await db.execute(select(func.count()).select_from(StudentUser).where(StudentUser.is_active.is_(True)))).scalar_one(),
        "totalOrders":(await db.execute(select(func.count()).select_from(Order))).scalar_one(),
        "activeOrders":(await db.execute(select(func.count()).select_from(Order).where(Order.order_status.in_(ACTIVE_STATES),Order.payment_status=="Paid"))).scalar_one(),
        "topItems":top,"redisCacheHitPercent":None,"wasteReductionPercent":None}

@admin_operations_router.get("/operations/status")
async def operations_status(db:AsyncSession=Depends(get_db),admin:AdminUser=Depends(get_current_admin)):
    active=(await db.execute(select(func.count()).select_from(Order).where(Order.order_status.in_(ACTIVE_STATES),Order.payment_status=="Paid"))).scalar_one()
    queued=(await db.execute(select(func.count()).select_from(Order).where(Order.order_status=="Queued",Order.payment_status=="Paid"))).scalar_one()
    hour=datetime.now(IST).hour
    window="Breakfast" if 8<=hour<11 else "Lunch" if 12<=hour<15 else "Snacks" if 16<=hour<18 else "Dinner" if 19<=hour<22 else "Closed"
    try: redis_available=bool(await asyncio.wait_for(get_redis_client().ping(),timeout=2))
    except Exception: redis_available=False
    return {"serviceOnline":True,"pendingOrders":active,"countQueued":queued,"activeWindow":window,"redisAvailable":redis_available}
@admin_operations_router.post("/qa-wallet-credit")
async def credit_qa_wallet_test(db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    from staging_wallet import credit_staging_qa_wallet
    from sqlalchemy import select
    from models import StudentUser
    student = (await db.execute(select(StudentUser).where(StudentUser.name == "STAGING QA Student"))).scalars().first()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(404, "STAGING QA Student not found")
    return await credit_staging_qa_wallet(db, student.id, student.roll_number)
