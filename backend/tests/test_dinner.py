"""Lunch/dinner bundles share validation but retain independent menu snapshots.

All dishes and balances here are isolated fixtures, never live menu data.
"""
import asyncio
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import func, select

import admin_operations
from image_fixtures import attach_test_image
from models import FoodItem, Order, StudentUser, WalletTransaction, WeeklyMenu
from test_lunch import CONTENTS, SABJIS, deterministic_lunch, order
from test_mess import mess_client
from test_order_payments import prepare

DINNER_CONTENTS = ['3 chapatis', 'Salad', 'Paneer', 'Aloo', 'Moong Dal', 'Jeera Rice']
DINNER_SABJIS = ['Paneer', 'Aloo']


@pytest.fixture(autouse=True)
def isolated_availability_cache(monkeypatch):
    async def no_cache(*args, **kwargs):
        return None
    monkeypatch.setattr(admin_operations, 'cache_invalidate_prefix', no_cache)


async def configure(client, meal='dinner', **changes):
    row = {'day': 'Thursday', 'meal_type': meal,
           'items': DINNER_CONTENTS if meal == 'dinner' else CONTENTS,
           'sabji_options': DINNER_SABJIS if meal == 'dinner' else SABJIS,
           'ordering_enabled': True, **changes}
    response = await client.post('/api/admin/menu/weekly', json={'schedule': [row]})
    assert response.status_code == 200, response.text
    return response


async def ready(fixture, clock):
    client = fixture[0]
    headers = await prepare(fixture, balance=500)
    await configure(client, 'lunch')
    await configure(client)
    clock['now'] = clock['now'].replace(hour=20, minute=0)
    result = await client.get('/api/menu/dinner')
    assert result.status_code == 200, result.text
    assert result.json()['available'] is True, result.text
    return client, headers, result.json()


def item(state, *, meal='dinner', thali=False, choice='Aloo', **changes):
    value = {'id': meal + ('-thali' if thali else '-chapati-bhaji'), 'qty': 1,
             'mealRevision': state['mealRevision']}
    if not thali:
        value['sabjiChoice'] = choice
    return {**value, **changes}


async def assert_not_charged(fixture):
    async with fixture[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('500')
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0


async def add_sabji_catalogue(fixture):
    async with fixture[1]() as db:
        for name in DINNER_SABJIS:
            food = FoodItem(id=name.lower() + '-id', name=name, price=30, category='Meals',
                            is_available=True, timing_window='all_day', customizations=[])
            db.add(food)
            await attach_test_image(db, food)
        await db.commit()


async def toggle(client, name, available):
    result = await client.patch('/api/admin/catalogue/' + name.lower() + '-id/availability',
                                json={'available': available})
    assert result.status_code == 200, result.text


async def saved_configs(fixture):
    async with fixture[1]() as db:
        return {row.meal_type.value if hasattr(row.meal_type, 'value') else row.meal_type:
                {'items': list(row.items), 'sabjis': list(row.sabji_options), 'enabled': row.ordering_enabled}
                for row in (await db.execute(select(WeeklyMenu).where(WeeklyMenu.day == 'Thursday'))).scalars()}


async def test_unconfigured_dinner_lists_prices_without_invented_contents(mess_client):
    response = await mess_client[0].get('/api/menu/dinner')
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['mealType'] == 'dinner'
    assert state['available'] is False and state['unavailableReason']
    assert state['contents'] == state['sabjiOptions'] == []
    assert {row['id']: row['price'] for row in state['options']} == {
        'dinner-chapati-bhaji': 45, 'dinner-thali': 80}


@pytest.mark.parametrize('meal,hour,choice,expected', [
    ('lunch', 12, 'Aloo Gobi', CONTENTS), ('dinner', 20, 'Aloo', DINNER_CONTENTS),
])
async def test_both_periods_fixed_prices_snapshots_and_mixed_alacarte(
        mess_client, deterministic_lunch, meal, hour, choice, expected):
    client, headers, _ = await ready(mess_client, deterministic_lunch)
    deterministic_lunch['now'] = deterministic_lunch['now'].replace(hour=hour, minute=30)
    state = (await client.get('/api/menu/' + meal)).json()
    response = await order(client, headers, [item(state, meal=meal, choice=choice, price=45),
                                            item(state, meal=meal, thali=True, price=80),
                                            {'id': 'financial-test-food', 'qty': 1}])
    assert response.status_code == 201, response.text
    assert response.json()['total'] == 185
    chapati, thali, alacarte = response.json()['items']
    assert chapati['contents'] == ['3 chapatis', 'Salad', choice]
    assert thali['contents'] == expected
    assert chapati['mealType'] == thali['mealType'] == meal
    assert chapati['mealDate'] == thali['mealDate'] == '2026-10-15'
    assert alacarte['id'] == 'financial-test-food' and alacarte['price'] == 60
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('315')
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 1


async def test_lunch_and_dinner_revisions_configuration_and_enable_flags_are_independent(
        mess_client, deterministic_lunch):
    client, _, dinner = await ready(mess_client, deterministic_lunch)
    lunch = (await client.get('/api/menu/lunch')).json()
    assert dinner['contents'] == DINNER_CONTENTS and lunch['contents'] == CONTENTS
    assert dinner['sabjiOptions'] == DINNER_SABJIS and lunch['sabjiOptions'] == SABJIS
    assert dinner['mealRevision'] != lunch['mealRevision']
    await configure(client, items=[*DINNER_CONTENTS, 'Papad'], ordering_enabled=False)
    assert (await client.get('/api/menu/lunch')).json() == lunch
    assert (await client.get('/api/menu/dinner')).json()['available'] is False
    deterministic_lunch['now'] = deterministic_lunch['now'].replace(hour=12, minute=30)
    assert (await client.get('/api/menu/lunch')).json()['available'] is True
    configs = await saved_configs(mess_client)
    assert configs['lunch'] == {'items': CONTENTS, 'sabjis': SABJIS, 'enabled': True}
    assert configs['dinner']['enabled'] is False


@pytest.mark.parametrize('hour,minute,allowed', [(19, 0, False), (19, 29, False), (19, 30, True),
                                               (22, 29, True), (22, 30, False)])
async def test_dinner_uses_existing_service_window_exact_boundaries(
        mess_client, deterministic_lunch, hour, minute, allowed):
    client, headers, _ = await ready(mess_client, deterministic_lunch)
    deterministic_lunch['now'] = deterministic_lunch['now'].replace(hour=hour, minute=minute)
    response = await client.get('/api/menu/dinner')
    state = response.json()
    assert state['available'] is allowed
    placed = await order(client, headers, [item(state)])
    assert placed.status_code == (201 if allowed else 409), placed.text
    if not allowed:
        await assert_not_charged(mess_client)


@pytest.mark.parametrize('changes', [{'price': 1}, {'sabjiChoice': None},
                                     {'sabjiChoice': 'Unlisted'}, {'mealRevision': 'stale'}])
async def test_invalid_dinner_selection_price_and_revision_do_not_charge(
        mess_client, deterministic_lunch, changes):
    client, headers, dinner = await ready(mess_client, deterministic_lunch)
    response = await order(client, headers, [item(dinner, **changes)])
    assert response.status_code in (409, 422), response.text
    await assert_not_charged(mess_client)


async def test_paneer_toggle_leaves_aloo_available_rejects_unavailable_and_restores(
        mess_client, deterministic_lunch):
    client, headers, initial = await ready(mess_client, deterministic_lunch)
    await add_sabji_catalogue(mess_client)
    await toggle(client, 'Paneer', False)
    current = (await client.get('/api/menu/dinner')).json()
    assert current['available'] is True and current['sabjiOptions'] == ['Aloo']
    assert 'Paneer' not in current['contents']
    assert (await order(client, headers, [item(current, choice='Paneer')])).status_code == 422
    assert (await order(client, headers, [item(initial, choice='Aloo')])).status_code == 409
    await assert_not_charged(mess_client)
    accepted = await order(client, headers, [item(current)])
    assert accepted.status_code == 201 and accepted.json()['total'] == 45
    await toggle(client, 'Paneer', True)
    restored = (await client.get('/api/menu/dinner')).json()
    assert restored['sabjiOptions'] == DINNER_SABJIS and restored['available'] is True
    configs = await saved_configs(mess_client)
    assert configs['dinner'] == {'items': DINNER_CONTENTS, 'sabjis': DINNER_SABJIS, 'enabled': True}


async def test_no_sabjis_disables_only_chapati_and_preserves_actual_thali_contents(
        mess_client, deterministic_lunch):
    client, headers, _ = await ready(mess_client, deterministic_lunch)
    await add_sabji_catalogue(mess_client)
    for name in DINNER_SABJIS:
        await toggle(client, name, False)
    state = (await client.get('/api/menu/dinner')).json()
    by_id = {row['id']: row for row in state['options']}
    assert state['available'] is True and state['sabjiOptions'] == []
    assert by_id['dinner-chapati-bhaji']['available'] is False
    assert by_id['dinner-thali']['available'] is True
    assert (await order(client, headers, [item(state)])).status_code == 409
    accepted = await order(client, headers, [item(state, thali=True)])
    assert accepted.status_code == 201 and accepted.json()['total'] == 80
    assert accepted.json()['items'][0]['contents'] == [name for name in DINNER_CONTENTS if name not in DINNER_SABJIS]


async def test_cross_meal_revision_and_mixed_lunch_dinner_cart_are_rejected_atomically(
        mess_client, deterministic_lunch):
    client, headers, dinner = await ready(mess_client, deterministic_lunch)
    lunch = (await client.get('/api/menu/lunch')).json()
    assert (await order(client, headers, [item(lunch)])).status_code == 409
    assert (await order(client, headers, [item(dinner), item(lunch, meal='lunch', choice='Aloo Gobi')])).status_code == 409
    await assert_not_charged(mess_client)


async def test_identical_meal_contents_still_require_period_specific_revision(mess_client, deterministic_lunch):
    client, headers, _ = await ready(mess_client, deterministic_lunch)
    await configure(client, 'lunch', items=DINNER_CONTENTS, sabji_options=DINNER_SABJIS)
    lunch = (await client.get('/api/menu/lunch')).json()
    dinner = (await client.get('/api/menu/dinner')).json()
    assert lunch['contents'] == dinner['contents']
    assert lunch['sabjiOptions'] == dinner['sabjiOptions']
    assert lunch['mealRevision'] != dinner['mealRevision']
    rejected = await order(client, headers, [item(lunch)])
    assert rejected.status_code == 409, rejected.text
    await assert_not_charged(mess_client)
    accepted = await order(client, headers, [item(dinner)])
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()['items'][0]['mealType'] == 'dinner'


@pytest.mark.parametrize('updated,unaffected', [('dinner', 'lunch'), ('lunch', 'dinner')])
async def test_ocr_replacement_disables_only_invalidated_period_and_requires_reconfiguration(
        mess_client, deterministic_lunch, updated, unaffected):
    client, _, _ = await ready(mess_client, deterministic_lunch)
    before = await saved_configs(mess_client)
    new_contents = ['3 chapatis', 'Salad', 'Bhindi', 'Rajma', 'Rice']
    response = await client.post('/api/admin/menu/weekly', json={'schedule': [
        {'day': 'Thursday', 'meal_type': updated, 'items': new_contents}]})
    assert response.status_code == 200, response.text
    after = await saved_configs(mess_client)
    assert after[updated] == {'items': new_contents, 'sabjis': [], 'enabled': False}
    assert after[unaffected] == before[unaffected]
    rejected = await client.post('/api/admin/menu/weekly', json={'schedule': [
        {'day': 'Thursday', 'meal_type': updated, 'items': new_contents, 'ordering_enabled': True}]})
    assert rejected.status_code == 422, rejected.text
    await configure(client, updated, items=new_contents, sabji_options=['Bhindi', 'Rajma'])
    assert (await saved_configs(mess_client))[unaffected] == before[unaffected]


async def test_dinner_order_snapshot_history_and_admin_updates_survive_both_menu_edits(
        mess_client, deterministic_lunch):
    client, headers, dinner = await ready(mess_client, deterministic_lunch)
    placed = await order(client, headers, [item(dinner), item(dinner, thali=True)])
    assert placed.status_code == 201, placed.text
    saved = placed.json()
    for meal in ('lunch', 'dinner'):
        await configure(client, meal, items=['3 chapatis', 'Salad', 'Bhindi', 'Rajma', 'Rice'],
                        sabji_options=['Bhindi', 'Rajma'])
    assert (await order(client, headers, [item(dinner)])).status_code == 409
    detail = await client.get('/api/student/orders/' + str(saved['orderId']), headers=headers)
    assert detail.status_code == 200 and detail.json()['items'] == saved['items']
    history = await client.get('/api/student/orders', headers=headers)
    assert history.status_code == 200 and history.json()[0]['items'] == saved['items']
    for status in ('Preparing', 'Ready', 'Completed'):
        updated = await client.post('/api/admin/orders/' + str(saved['orderId']) + '/status', json={'status': status})
        assert updated.status_code == 200 and updated.json()['items'] == saved['items']
    async with mess_client[1]() as db:
        assert (await db.get(Order, saved['orderId'])).items_json == saved['items']
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('375')


async def test_student_and_unauthenticated_clients_cannot_configure_dinner(mess_client, deterministic_lunch):
    client, headers, _ = await ready(mess_client, deterministic_lunch)
    body = {'schedule': [{'day': 'Thursday', 'meal_type': 'dinner', 'items': DINNER_CONTENTS,
                           'sabji_options': DINNER_SABJIS, 'ordering_enabled': True}]}
    assert (await client.post('/api/admin/menu/weekly', headers=headers, json=body)).status_code in (401, 403)
    client.headers.pop('Authorization', None)
    assert (await client.post('/api/admin/menu/weekly', json=body)).status_code == 401
    assert (await order(client, {}, [{'id': 'dinner-thali', 'qty': 1}])).status_code == 401


@pytest.mark.parametrize('same_key', [False, True])
async def test_postgres_dinner_wallet_race_never_double_charges(mess_client, deterministic_lunch, same_key):
    if not mess_client[2]:
        pytest.skip('True dinner wallet row-lock verification requires isolated PostgreSQL')
    client, headers, dinner = await ready(mess_client, deterministic_lunch)
    async with mess_client[1]() as db:
        (await db.get(StudentUser, 'linked-student')).wallet_balance = Decimal('45')
        await db.commit()
    key = uuid.uuid4().hex
    responses = await asyncio.gather(
        order(client, headers, [item(dinner)], key),
        order(client, headers, [item(dinner)], key if same_key else uuid.uuid4().hex))
    assert sorted(response.status_code for response in responses) == ([201, 201] if same_key else [201, 400])
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('0')
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 1
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 1
