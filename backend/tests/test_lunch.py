"""Lunch checkout integration tests use isolated test DBs and no external payment."""
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from config import settings
from models import Order, StudentUser, WalletTransaction
from test_mess import mess_client
from test_order_payments import prepare
import routes
import lunch_service

CONTENTS = ['3 chapatis', 'Salad', 'Aloo Gobi', 'Chana Masala', 'Dal', 'Rice']
SABJIS = ['Aloo Gobi', 'Chana Masala']


@pytest.fixture(autouse=True)
def deterministic_lunch(monkeypatch):
    clock = {'now': datetime(2026, 10, 15, 12, 30, tzinfo=ZoneInfo('Asia/Kolkata'))}
    monkeypatch.setattr(lunch_service, 'lunch_now', lambda: clock['now'])
    monkeypatch.setattr(settings, 'RATE_LIMIT_ENABLED', False)
    async def no_cache(*args, **kwargs):
        return None
    for name in ('cache_get', 'cache_set', 'cache_invalidate_prefix'):
        monkeypatch.setattr(routes, name, no_cache)
    return clock


async def configure(client, **changes):
    row = {'day': 'Thursday', 'meal_type': 'lunch', 'items': CONTENTS,
           'sabji_options': SABJIS, 'ordering_enabled': True, **changes}
    return await client.post('/api/admin/menu/weekly', json={'schedule': [row]})


async def ready(fixture):
    client, _, _ = fixture
    headers = await prepare(fixture, balance=500)
    response = await configure(client)
    assert response.status_code == 200, response.text
    lunch = await client.get('/api/menu/lunch')
    assert lunch.status_code == 200, lunch.text
    assert lunch.json()['available'] is True
    return client, headers, lunch.json()


def item(lunch, thali=False, choice='Aloo Gobi', **changes):
    value = {'id': 'lunch-thali' if thali else 'lunch-chapati-bhaji', 'qty': 1,
             'mealRevision': lunch['mealRevision']}
    if not thali:
        value['sabjiChoice'] = choice
    return {**value, **changes}


async def order(client, headers, items, key=None, method='wallet'):
    return await client.post('/api/student/orders', headers={**headers, 'Idempotency-Key': key or uuid.uuid4().hex},
                             json={'items': items, 'paymentMethod': method})


async def test_unconfigured_lunch_lists_both_options_without_inventing_contents(mess_client):
    result = await mess_client[0].get('/api/menu/lunch')
    assert result.status_code == 200
    body = result.json()
    assert body['available'] is False and body['unavailableReason']
    assert body['contents'] == body['sabjiOptions'] == []
    assert {row['name']: row['price'] for row in body['options']} == {'Chapati Bhaji': 45, 'Thali': 80}


async def test_chapati_price_choice_wallet_and_idempotency(mess_client):
    client, headers, lunch = await ready(mess_client)
    key = uuid.uuid4().hex
    payload = item(lunch, name='Forged free dish')
    response = await order(client, headers, [payload], key)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['itemTotal'] == saved['total'] == 45
    assert saved['packagingFee'] == saved['gst'] == 0
    snapshot = saved['items'][0]
    assert snapshot['name'] == 'Chapati Bhaji' and snapshot['price'] == 45
    assert snapshot['contents'] == ['3 chapatis', 'Salad', 'Aloo Gobi']
    assert snapshot['sabjiChoice'] == 'Aloo Gobi'
    assert snapshot['mealDate'] == '2026-10-15' and snapshot['mealType'] == 'lunch'
    again = await order(client, headers, [payload], key)
    assert again.status_code == 201 and again.json()['orderId'] == saved['orderId']
    assert (await order(client, headers, [item(lunch, choice='Chana Masala')], key)).status_code == 409
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('455')
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 1


@pytest.mark.parametrize('changes', [
    {'sabjiChoice': None}, {'sabjiChoice': ''}, {'sabjiChoice': 'Unlisted Sabji'},
    {'sabjiChoice': ['Aloo Gobi', 'Chana Masala']}, {'customizations': ['Aloo Gobi', 'Chana Masala']},
    {'mealRevision': None}, {'mealRevision': 'stale-revision'},
    {'price': 0.01},
])
async def test_invalid_choice_or_revision_never_deducts_wallet(mess_client, changes):
    client, headers, lunch = await ready(mess_client)
    result = await order(client, headers, [item(lunch, **changes)])
    assert result.status_code in (409, 422), result.text
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('500')
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0


async def test_thali_snapshots_configured_contents_history_and_admin_order_management(mess_client):
    client, headers, lunch = await ready(mess_client)
    response = await order(client, headers, [item(lunch, thali=True)])
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['total'] == 80 and saved['items'][0]['contents'] == CONTENTS
    assert (await configure(client, items=['Roti', 'Salad', 'Bhindi', 'Rajma', 'Jeera Rice'],
                            sabji_options=['Bhindi', 'Rajma'])).status_code == 200
    history = await client.get('/api/student/orders/' + str(saved['orderId']), headers=headers)
    assert history.status_code == 200
    assert history.json()['items'] == saved['items']
    async with mess_client[1]() as db:
        assert (await db.get(Order, saved['orderId'])).items_json == saved['items']
    for state in ('Preparing', 'Ready', 'Completed'):
        updated = await client.post('/api/admin/orders/' + str(saved['orderId']) + '/status', json={'status': state})
        assert updated.status_code == 200, updated.text
        assert updated.json()['items'] == saved['items']
    assert (await client.get('/api/student/orders', headers=headers)).json()[0]['items'] == saved['items']


async def test_two_sabji_variants_and_ala_carte_share_authoritative_checkout(mess_client):
    client, headers, lunch = await ready(mess_client)
    result = await order(client, headers, [item(lunch), item(lunch, choice='Chana Masala', qty=2),
                                          {'id': 'financial-test-food', 'qty': 1}])
    assert result.status_code == 201, result.text
    assert result.json()['total'] == 195
    assert [row.get('sabjiChoice') for row in result.json()['items'][:2]] == SABJIS


@pytest.mark.parametrize('changes', [
    {'sabji_options': ['Aloo Gobi']}, {'sabji_options': ['Aloo Gobi', 'Aloo Gobi']},
    {'sabji_options': ['Aloo Gobi', 'Missing from thali']}, {'items': []},
])
async def test_admin_cannot_enable_incomplete_lunch(mess_client, changes):
    result = await configure(mess_client[0], **changes)
    assert result.status_code in (409, 422), result.text
    assert (await mess_client[0].get('/api/menu/lunch')).json()['available'] is False


async def test_ocr_style_update_preserves_explicit_lunch_configuration(mess_client):
    client, _, lunch = await ready(mess_client)
    body = {'schedule': [{'day': 'Thursday', 'meal_type': 'lunch', 'items': [*CONTENTS, 'Papad']}]}
    response = await client.post('/api/admin/menu/weekly', json=body)
    assert response.status_code == 200, response.text
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is True and current['sabjiOptions'] == SABJIS
    assert current['contents'] == [*CONTENTS, 'Papad']
    assert current['mealRevision'] != lunch['mealRevision']


async def test_config_change_or_disable_rejects_stale_cart_without_payment(mess_client):
    client, headers, lunch = await ready(mess_client)
    assert (await configure(client, items=[*CONTENTS, 'Papad'])).status_code == 200
    assert (await order(client, headers, [item(lunch, thali=True)])).status_code == 409
    current = (await client.get('/api/menu/lunch')).json()
    assert (await configure(client, ordering_enabled=False)).status_code == 200
    assert (await order(client, headers, [item(current)])).status_code == 409


@pytest.mark.parametrize('hour,minute', [(11, 59), (15, 0), (19, 0)])
async def test_outside_lunch_window_rejects_order(mess_client, deterministic_lunch, hour, minute):
    client, headers, lunch = await ready(mess_client)
    deterministic_lunch['now'] = deterministic_lunch['now'].replace(hour=hour, minute=minute)
    assert (await client.get('/api/menu/lunch')).json()['available'] is False
    assert (await order(client, headers, [item(lunch)])).status_code == 409


async def test_next_day_cannot_order_yesterdays_lunch(mess_client, deterministic_lunch):
    client, headers, lunch = await ready(mess_client)
    deterministic_lunch['now'] += timedelta(days=1)
    assert (await order(client, headers, [item(lunch)])).status_code == 409


async def test_thali_rejects_choice_and_ala_carte_rejects_lunch_fields(mess_client):
    client, headers, lunch = await ready(mess_client)
    assert (await order(client, headers, [item(lunch, thali=True, sabjiChoice='Aloo Gobi')])).status_code == 422
    assert (await order(client, headers, [{'id': 'financial-test-food', 'qty': 1, 'sabjiChoice': 'Aloo Gobi'}])).status_code == 422


async def test_unauthenticated_or_student_cannot_configure_lunch(mess_client):
    client, headers, _ = await ready(mess_client)
    body = {'schedule': [{'day': 'Thursday', 'meal_type': 'lunch', 'items': CONTENTS,
                           'sabji_options': SABJIS, 'ordering_enabled': False}]}
    assert (await client.post('/api/admin/menu/weekly', headers=headers, json=body)).status_code in (401, 403)
    client.headers.pop('Authorization', None)
    assert (await client.post('/api/admin/menu/weekly', json=body)).status_code == 401
    assert (await client.post('/api/student/orders', json={'items': [{'id': 'lunch-thali', 'qty': 1}], 'paymentMethod': 'wallet'},
                              headers={'Idempotency-Key': uuid.uuid4().hex})).status_code == 401
