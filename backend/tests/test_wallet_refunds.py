"""PostgreSQL financial regression checks; every provider operation is mocked."""
import asyncio
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import hmac
import json
import re
import uuid
import pytest
import httpx
from fastapi import HTTPException
from sqlalchemy import select,func
from auth import create_access_token,credential_fingerprint
from config import settings
from models import StudentUser,Order,WalletTransaction
from payment_models import PaymentIntent,PaymentRefund,PaymentEvent
from payment_provider import provider,RazorpayProvider
from test_mess import mess_client
from test_order_payments import prepare,place,payload

class Gateway:
    def __init__(self):
        self.orders={}; self.payments={}; self.refunds={}; self.created=[]; self.refund_calls=[]
        self.refund_state='processed'; self.timeout=False; self.order_timeout=False
    async def create_order(self,amount,receipt,order_id):
        value={'id':'order_QA'+str(len(self.orders)+1),'amount':amount,'currency':'INR','receipt':receipt}
        self.orders[value['id']]=value; self.created.append(value)
        if self.order_timeout: raise HTTPException(502,'Simulated provider timeout')
        return value.copy()
    def capture(self,order_id):
        value={'id':'pay_QA'+str(len(self.payments)+1),'order_id':order_id,'amount':self.orders[order_id]['amount'],'currency':'INR','status':'captured','captured':True}
        self.payments[value['id']]=value
        return value
    async def fetch_payment(self,pid):return self.payments[pid].copy()
    async def fetch_order(self,oid):return self.orders[oid].copy()
    async def order_payments(self,oid):return {'items':[p.copy() for p in self.payments.values() if p['order_id']==oid]}
    async def payment_refunds(self,pid):return {'items':[r.copy() for r in self.refunds.values() if r['payment_id']==pid]}
    def refund(self,pid,amount=None):
        value={'id':'rfnd_QA'+str(len(self.refunds)+1),'payment_id':pid,'amount':amount if amount is not None else self.payments[pid]['amount'],'currency':'INR','status':self.refund_state}
        self.refunds[value['id']]=value
        return value
    async def create_refund(self,pid,amount,receipt,key):
        self.refund_calls.append((pid,amount,receipt,key))
        previous=next((r for r in self.refunds.values() if r['payment_id']==pid),None)
        value=previous or self.refund(pid,amount)
        if self.timeout:self.timeout=False;raise HTTPException(502,'Simulated lost refund response')
        return value.copy()
    async def fetch_refund(self,pid,rid):return self.refunds[rid].copy()

@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setattr(settings,'PAYMENT_PROVIDER','razorpay')
    monkeypatch.setattr(settings,'RAZORPAY_KEY_ID','qa_public_key')
    monkeypatch.setattr(settings,'RAZORPAY_KEY_SECRET','qa_private_test_key')
    monkeypatch.setattr(settings,'RAZORPAY_WEBHOOK_SECRET','qa_webhook_test_key')
    async def forbidden(*args,**kwargs):raise AssertionError('Unexpected real provider request')
    monkeypatch.setattr(provider,'request',forbidden)
    fake=Gateway()
    for name in ('create_order','fetch_payment','fetch_order','order_payments','create_refund','fetch_refund','payment_refunds'):
        monkeypatch.setattr(provider,name,getattr(fake,name))
    return fake

def verification(payment):
    oid,pid=payment['order_id'],payment['id']
    signature=hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),(oid+'|'+pid).encode(),hashlib.sha256).hexdigest()
    return {'razorpay_order_id':oid,'razorpay_payment_id':pid,'razorpay_signature':signature}

async def webhook(client,kind,entity,event_id=None):
    key='refund' if kind.startswith('refund.') else 'payment'
    raw=json.dumps({'event':kind,'payload':{key:{'entity':entity}}},separators=(',',':')).encode()
    headers={'Content-Type':'application/json','X-Razorpay-Event-Id':event_id or 'event_'+uuid.uuid4().hex,'X-Razorpay-Signature':hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(),raw,hashlib.sha256).hexdigest()}
    return await client.post('/api/payments/webhooks/razorpay',content=raw,headers=headers)

async def topup(fixture,gateway,amount='100.50',balance=0):
    client,_,_=fixture
    headers=await prepare(fixture,balance)
    result=await client.post('/api/student/wallet/recharge',headers={**headers,'Idempotency-Key':uuid.uuid4().hex},json={'amount':amount,'paymentMethod':'razorpay'})
    assert result.status_code==200,result.text
    row=result.json();payment=gateway.capture(row['checkout']['providerOrderId'])
    return headers,row,payment

async def verify_topup(client,headers,row,payment):
    return await client.post(f'/api/student/wallet/topups/{row["id"]}/verify',headers=headers,json=verification(payment))

async def paid_order(fixture,gateway):
    client,_,_=fixture
    headers=await prepare(fixture)
    result=await place(client,headers,body=payload('razorpay'))
    assert result.status_code==201,result.text
    row=result.json();payment=gateway.capture(row['checkout']['providerOrderId'])
    verified=await client.post(f'/api/student/orders/{row["orderId"]}/payment/verify',headers=headers,json=verification(payment))
    assert verified.status_code==200,verified.text
    return headers,row,payment

async def test_topup_validation_idempotency_and_no_unverified_credit(mess_client,gateway):
    client,sessions,_=mess_client;headers=await prepare(mess_client,balance=0)
    path='/api/student/wallet/recharge';key=uuid.uuid4().hex
    for amount in (0,-1,1.005,10001,'NaN','Infinity'):
        assert (await client.post(path,headers={**headers,'Idempotency-Key':key},json={'amount':amount})).status_code==422
    assert (await client.post(path,headers=headers,json={'amount':100})).status_code==422
    first=await client.post(path,headers={**headers,'Idempotency-Key':key},json={'amount':'100.50'})
    again=await client.post(path,headers={**headers,'Idempotency-Key':key},json={'amount':'100.50'})
    assert first.status_code==again.status_code==200
    assert first.json()['id']==again.json()['id'] and len(gateway.created)==1
    assert (await client.post(path,headers={**headers,'Idempotency-Key':key},json={'amount':101})).status_code==409
    async with sessions() as db:
        assert (await db.get(StudentUser,'linked-student')).wallet_balance==Decimal('0.00')
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one()==0

async def test_topup_signature_entity_and_owner_checks(mess_client,gateway):
    client,sessions,_=mess_client;headers,row,payment=await topup(mess_client,gateway)
    path=f'/api/student/wallet/topups/{row["id"]}/verify';body=verification(payment)
    assert (await client.post(path,headers=headers,json={**body,'razorpay_signature':'0'*64})).status_code==400
    assert (await client.post(path,headers=headers,json={**body,'razorpay_order_id':'order_Wrong'})).status_code==400
    for field,value in [('amount',10051),('currency','USD'),('status','authorized'),('status','failed'),('captured',False)]:
        original=payment[field];payment[field]=value
        assert (await client.post(path,headers=headers,json=body)).status_code==409
        payment[field]=original
    async with sessions() as db:
        db.add(StudentUser(id='qa-other',roll_number='QAOTHER',name='Other',email='other@qa.invalid',hashed_passcode='unused'))
        await db.commit()
    other={'Authorization':'Bearer '+create_access_token({'sub':'qa-other','role':'student','credential_version':credential_fingerprint('unused')})}
    assert (await client.post(path,headers=other,json=body)).status_code==404
    assert (await client.get(f'/api/student/wallet/topups/{row["id"]}',headers=other)).status_code==404
    assert (await verify_topup(client,headers,row,payment)).status_code==200

async def test_concurrent_topup_callbacks_and_reordered_webhooks_credit_once(mess_client,gateway):
    client,sessions,postgres=mess_client
    if not postgres:pytest.skip('Real row locks require PostgreSQL')
    headers,row,payment=await topup(mess_client,gateway)
    responses=await asyncio.gather(verify_topup(client,headers,row,payment),verify_topup(client,headers,row,payment),webhook(client,'payment.captured',payment,'event_capture_race'))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert (await webhook(client,'payment.captured',payment,'event_capture_race')).json()['duplicate']
    for kind in ('payment.failed','payment.authorized'):
        assert (await webhook(client,kind,{**payment,'status':kind.split('.')[1]})).status_code==200
    async with sessions() as db:
        student=await db.get(StudentUser,'linked-student');intent=await db.get(PaymentIntent,row['id'])
        assert student.wallet_balance==Decimal('100.50') and student.total_spent==0 and student.total_orders==0
        assert intent.state=='captured' and intent.wallet_credited_at is not None
        transactions=(await db.execute(select(WalletTransaction))).scalars().all()
        assert len(transactions)==1 and transactions[0].amount==Decimal('100.50') and transactions[0].payment_intent_id==row['id']

async def test_topup_credit_races_wallet_spend_without_lost_balance(mess_client,gateway):
    client,sessions,postgres=mess_client
    if not postgres:pytest.skip('Real row locks require PostgreSQL')
    headers,row,payment=await topup(mess_client,gateway,balance=71)
    verified,order=await asyncio.gather(verify_topup(client,headers,row,payment),place(client,headers))
    assert verified.status_code==200 and order.status_code==201
    async with sessions() as db:
        assert (await db.get(StudentUser,'linked-student')).wallet_balance==Decimal('100.50')
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one()==2

async def test_topup_timeout_preserves_intent_and_reconciles_without_second_post(mess_client,gateway):
    client,sessions,_=mess_client;headers=await prepare(mess_client,0);key=uuid.uuid4().hex;gateway.order_timeout=True
    path='/api/student/wallet/recharge';body={'amount':100}
    assert (await client.post(path,headers={**headers,'Idempotency-Key':key},json=body)).status_code==503
    repeated=await client.post(path,headers={**headers,'Idempotency-Key':key},json=body)
    assert repeated.status_code==200 and len(gateway.created)==1
    intent_id=repeated.json()['id'];remote=gateway.created[0];gateway.order_timeout=False
    result=await client.post(f'/api/admin/payments/intents/{intent_id}/reconcile',json={'providerOrderId':remote['id']})
    assert result.status_code==200,result.text
    current=(await client.get(f'/api/student/wallet/topups/{intent_id}',headers=headers)).json()
    assert current['checkout']['providerOrderId']==remote['id'] and current['walletBalance']==0

@pytest.mark.parametrize('state',['pending','failed','processed'])
async def test_full_gateway_refund_states_and_reordered_events(mess_client,gateway,state):
    client,sessions,_=mess_client;headers,row,payment=await paid_order(mess_client,gateway);gateway.refund_state=state
    oid=row['orderId'];result=await client.post(f'/api/student/orders/{oid}/cancel',headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['status']=='Cancelled'
    assert result.json()['payment']==('Refunded' if state=='processed' else 'Paid')
    polled=await client.get('/api/admin/orders')
    assert polled.status_code==200 and next(order for order in polled.json() if order['orderId']==oid)['refundStatus']==state
    remote=next(iter(gateway.refunds.values()));remote['status']='processed'
    assert (await webhook(client,'refund.processed',remote,'event_refund_processed')).status_code==200
    assert (await webhook(client,'refund.processed',remote,'event_refund_processed')).json()['duplicate']
    remote['status']='pending'
    assert (await webhook(client,'refund.created',remote)).status_code==200
    async with sessions() as db:
        student=await db.get(StudentUser,'linked-student');order=await db.get(Order,oid)
        refund=(await db.execute(select(PaymentRefund))).scalar_one()
        assert refund.state=='processed' and order.payment_status=='Refunded'
        assert student.total_spent==0 and student.wallet_balance==Decimal('200.00')
        assert len(gateway.refund_calls)==1
    assert (await client.get('/api/admin/analytics')).json()['dailyRevenue']==0

async def test_refund_timeout_reuses_persisted_key_and_identical_body(mess_client,gateway):
    client,sessions,_=mess_client;headers,row,payment=await paid_order(mess_client,gateway);gateway.timeout=True
    path=f'/api/admin/payments/{row["orderId"]}/refund'
    first=await client.post(path,json={'reason':'Kitchen cannot fulfil'})
    assert first.status_code==200 and first.json()['payment']=='Paid'
    async with sessions() as db:
        refund=(await db.execute(select(PaymentRefund))).scalar_one();key=refund.idempotency_key
        assert refund.state=='reconciliation_required' and re.fullmatch(r'[A-Za-z0-9_-]{10,64}',key)
    second=await client.post(path,json={'reason':'Kitchen cannot fulfil'})
    assert second.status_code==200 and second.json()['payment']=='Refunded'
    assert len(gateway.refund_calls)==2 and gateway.refund_calls[0]==gateway.refund_calls[1]
    assert gateway.refund_calls[1][3]==key
    assert (await client.post(path,json={'reason':'Retry processed refund'})).status_code==200
    assert len(gateway.refund_calls)==2

async def test_student_cancellation_policy_and_admin_override(mess_client,gateway):
    client,sessions,_=mess_client;headers,row,payment=await paid_order(mess_client,gateway);oid=row['orderId']
    assert (await client.post(f'/api/admin/orders/{oid}/status',json={'status':'Preparing'})).status_code==200
    assert (await client.post(f'/api/student/orders/{oid}/cancel',headers=headers)).status_code==409
    assert not gateway.refund_calls
    assert (await client.post(f'/api/admin/payments/{oid}/refund',headers=headers,json={'reason':'Unauthorized'})).status_code==403
    result=await client.post(f'/api/admin/payments/{oid}/refund',json={'reason':'Kitchen problem'})
    assert result.status_code==200 and result.json()['payment']=='Refunded'
    async with sessions() as db:
        refund=(await db.execute(select(PaymentRefund))).scalar_one()
        assert refund.requested_by_admin_id is not None and refund.requested_by_student_id is None

@pytest.mark.parametrize('late',['cancelled','expired'])
async def test_late_capture_never_enters_kitchen_and_refunds_once(mess_client,gateway,late):
    client,sessions,_=mess_client;headers=await prepare(mess_client)
    result=await place(client,headers,body=payload('razorpay'));row=result.json();oid=row['orderId']
    if late=='cancelled':assert (await client.post(f'/api/student/orders/{oid}/cancel',headers=headers)).status_code==200
    else:
        async with sessions() as db:
            intent=(await db.execute(select(PaymentIntent))).scalar_one();intent.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);await db.commit()
        refreshed=await client.get(f'/api/student/orders/{oid}',headers=headers)
        assert refreshed.status_code==200 and refreshed.json()['checkout'] is None
    payment=gateway.capture(row['checkout']['providerOrderId'])
    result=await client.post(f'/api/student/orders/{oid}/payment/verify',headers=headers,json=verification(payment))
    assert result.status_code==200,result.text
    assert result.json()['status']=='Cancelled' and result.json()['payment']=='Refunded'
    assert (await webhook(client,'payment.captured',payment)).status_code==200
    async with sessions() as db:
        student=await db.get(StudentUser,'linked-student')
        assert student.total_spent==0 and student.total_orders==0 and student.wallet_balance==Decimal('200.00')
        assert len(gateway.refund_calls)==1

@pytest.mark.parametrize('spend',[False,True])
async def test_provider_topup_refund_recovers_available_balance_and_freezes_debt(mess_client,gateway,spend):
    client,sessions,_=mess_client;headers,row,payment=await topup(mess_client,gateway)
    assert (await verify_topup(client,headers,row,payment)).status_code==200
    assert (await client.post(f'/api/admin/payments/intents/{row["id"]}/refund',json={'reason':'Cannot refund spendable funds'})).status_code==409
    if spend:assert (await place(client,headers)).status_code==201
    remote=gateway.refund(payment['id'])
    assert (await webhook(client,'refund.processed',remote,'event_wallet_refund')).status_code==200
    assert (await webhook(client,'refund.processed',remote,'event_wallet_refund')).json()['duplicate']
    remote['status']='pending'
    assert (await webhook(client,'refund.created',remote)).status_code==200
    async with sessions() as db:
        student=await db.get(StudentUser,'linked-student');intent=await db.get(PaymentIntent,row['id'])
        assert student.wallet_balance==0 and student.is_active is (not spend)
        assert intent.state=='refunded' and intent.unrecovered_refund_paise==(7100 if spend else 0)
        recovery=(await db.execute(select(WalletTransaction).where(WalletTransaction.payment_intent_id==row['id'],WalletTransaction.transaction_type=='debit'))).scalar_one()
        assert recovery.amount==Decimal('29.50' if spend else '100.50')

async def test_partial_provider_refund_freezes_for_operator_review(mess_client,gateway):
    client,sessions,_=mess_client;headers,row,payment=await topup(mess_client,gateway)
    assert (await verify_topup(client,headers,row,payment)).status_code==200
    remote=gateway.refund(payment['id'],amount=5000)
    result=await webhook(client,'refund.processed',remote)
    assert result.status_code==200,result.text
    async with sessions() as db:
        student=await db.get(StudentUser,'linked-student');intent=await db.get(PaymentIntent,row['id'])
        assert not student.is_active and student.wallet_balance>=0 and intent.state=='refund_review'
        assert (await db.execute(select(func.count()).select_from(PaymentRefund))).scalar_one()==0

async def test_missed_provider_refund_webhook_is_reconciled(mess_client,gateway):
    client,sessions,_=mess_client;headers,row,payment=await topup(mess_client,gateway)
    assert (await verify_topup(client,headers,row,payment)).status_code==200
    gateway.refund(payment['id'])
    payment['amount_refunded']=payment['amount']
    payment['status']='refunded'
    result=await client.post(f'/api/admin/payments/intents/{row["id"]}/reconcile',json={})
    assert result.status_code==200,result.text
    async with sessions() as db:
        assert (await db.get(StudentUser,'linked-student')).wallet_balance==0
        assert (await db.get(PaymentIntent,row['id'])).state=='refunded'
        assert (await db.execute(select(func.count()).select_from(PaymentRefund))).scalar_one()==1

async def test_provider_adapter_sends_exact_refund_idempotency_header(monkeypatch):
    monkeypatch.setattr(settings,'PAYMENT_PROVIDER','razorpay');monkeypatch.setattr(settings,'RAZORPAY_KEY_ID','qa_key');monkeypatch.setattr(settings,'RAZORPAY_KEY_SECRET','qa_secret')
    calls=[];real_client=httpx.AsyncClient
    def respond(request):
        calls.append((request.method,request.url.path,request.headers.get('X-Refund-Idempotency'),json.loads(request.content)))
        return httpx.Response(200,json={'id':'rfnd_Adapter','payment_id':'pay_Adapter','amount':7100,'currency':'INR','status':'processed'})
    transport=httpx.MockTransport(respond)
    import payment_provider
    monkeypatch.setattr(payment_provider.httpx,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))
    key='refund_'+uuid.uuid4().hex
    for _ in range(2):await RazorpayProvider().create_refund('pay_Adapter',7100,'qa_receipt',key)
    assert calls[0]==calls[1]==('POST','/v1/payments/pay_Adapter/refund',key,{'amount':7100,'speed':'normal','receipt':'qa_receipt'})


@pytest.mark.parametrize("changes", [{"amount_refunded": 1}, {"refund_status": "full"}])
def test_preexisting_provider_refund_cannot_be_captured_as_new_funds(changes):
    from types import SimpleNamespace
    from financial_service import validate_capture
    intent = SimpleNamespace(provider_order_id="order_Refunded", amount_paise=10000, currency="INR")
    payment = {"id":"pay_Refunded", "order_id":"order_Refunded", "amount":10000,
               "currency":"INR", "status":"captured", "captured":True, **changes}
    with pytest.raises(HTTPException) as rejected:
        validate_capture(intent, payment)
    assert rejected.value.status_code == 409
