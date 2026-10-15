"""Normal catalogue availability must gate lunch choices without deleting configuration."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

import admin_operations
from image_fixtures import attach_test_image
from models import FoodItem, Order, StudentUser, WalletTransaction, WeeklyMenu
from test_lunch import deterministic_lunch, item, order
from test_mess import mess_client
from test_order_payments import prepare

CONTENTS = ['3 chapatis', 'Salad', 'Paneer', 'Aloo', 'Dal', 'Rice']
SABJIS = ['Paneer', 'Aloo']


@pytest.fixture(autouse=True)
def isolated_availability_cache(monkeypatch):
    async def no_cache(*args, **kwargs):
        return None
    monkeypatch.setattr(admin_operations, 'cache_invalidate_prefix', no_cache)


async def ready(fixture):
    client, sessions, _ = fixture
    headers = await prepare(fixture, balance=500)
    async with sessions() as db:
        for name in SABJIS:
            row = FoodItem(id=name.lower() + '-id', name=name, price=30, category='Meals',
                           is_available=True, timing_window='all_day', customizations=[])
            db.add(row)
            await attach_test_image(db, row)
        await db.commit()
    saved = await client.post('/api/admin/menu/weekly', json={'schedule': [{
        'day': 'Thursday', 'meal_type': 'lunch', 'items': CONTENTS,
        'sabji_options': SABJIS, 'ordering_enabled': True,
    }]})
    assert saved.status_code == 200, saved.text
    response = await client.get('/api/menu/lunch')
    assert response.status_code == 200, response.text
    return client, headers, response.json()


async def toggle(client, name, available):
    response = await client.patch('/api/admin/catalogue/' + name.lower() + '-id/availability',
                                  json={'available': available})
    assert response.status_code == 200, response.text
    assert response.json()['available'] is available


async def assert_configuration_preserved(sessions):
    async with sessions() as db:
        row = (await db.execute(select(WeeklyMenu).where(
            WeeklyMenu.day == 'Thursday', WeeklyMenu.meal_type == 'lunch'))).scalar_one()
        assert row.items == CONTENTS
        assert row.sabji_options == SABJIS
        assert row.ordering_enabled is True


async def test_paneer_toggle_keeps_aloo_orderable_and_reenable_restores_same_configuration(mess_client):
    client, headers, initial = await ready(mess_client)
    assert initial['available'] is True and initial['sabjiOptions'] == SABJIS
    await toggle(client, 'Paneer', False)
    current = (await client.get('/api/menu/lunch')).json()
    assert current['sabjiOptions'] == ['Aloo']
    assert current['available'] is True
    assert current['mealRevision'] != initial['mealRevision']
    assert next(row['price'] for row in current['options'] if row['id'] == 'lunch-chapati-bhaji') == 45
    await assert_configuration_preserved(mess_client[1])
    response = await order(client, headers, [item(current, choice='Aloo')])
    assert response.status_code == 201, response.text
    assert response.json()['total'] == 45
    assert response.json()['items'][0]['contents'] == ['3 chapatis', 'Salad', 'Aloo']
    await toggle(client, 'Paneer', True)
    restored = (await client.get('/api/menu/lunch')).json()
    assert restored['available'] is True and restored['sabjiOptions'] == SABJIS
    await assert_configuration_preserved(mess_client[1])
    response = await order(client, headers, [item(restored, choice='Paneer')])
    assert response.status_code == 201, response.text


@pytest.mark.parametrize('attempt', ['unavailable-choice', 'stale-cart', 'missing-choice'])
async def test_unavailable_paneer_stale_cart_and_missing_selection_cannot_charge(mess_client, attempt):
    client, headers, initial = await ready(mess_client)
    await toggle(client, 'Paneer', False)
    current = (await client.get('/api/menu/lunch')).json()
    payload = item(initial if attempt == 'stale-cart' else current,
                   choice=None if attempt == 'missing-choice' else 'Paneer')
    response = await order(client, headers, [payload])
    assert response.status_code == (409 if attempt == 'stale-cart' else 422), response.text
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('500')
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0


async def test_thali_excludes_unavailable_paneer_and_preserves_past_order_snapshots(mess_client):
    client, headers, initial = await ready(mess_client)
    before = await order(client, headers, [item(initial, thali=True)])
    assert before.status_code == 201, before.text
    assert before.json()['items'][0]['contents'] == CONTENTS
    await toggle(client, 'Paneer', False)
    current = (await client.get('/api/menu/lunch')).json()
    expected = [name for name in CONTENTS if name != 'Paneer']
    assert current['contents'] == expected
    after = await order(client, headers, [item(current, thali=True)])
    assert after.status_code == 201, after.text
    assert after.json()['total'] == 80
    assert after.json()['items'][0]['contents'] == expected
    await toggle(client, 'Paneer', True)
    history = await client.get('/api/student/orders', headers=headers)
    assert history.status_code == 200, history.text
    by_id = {row['orderId']: row for row in history.json()}
    assert by_id[before.json()['orderId']]['items'] == before.json()['items']
    assert by_id[after.json()['orderId']]['items'] == after.json()['items']
    await assert_configuration_preserved(mess_client[1])


async def test_both_sabjis_unavailable_blocks_lunch_without_erasing_configuration(mess_client):
    client, headers, initial = await ready(mess_client)
    await toggle(client, 'Paneer', False)
    await toggle(client, 'Aloo', False)
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is False
    assert current['sabjiOptions'] == []
    for thali in (False, True):
        response = await order(client, headers, [item(initial, thali=thali, choice='Aloo')])
        assert response.status_code == 409, response.text
    await assert_configuration_preserved(mess_client[1])
    await toggle(client, 'Aloo', True)
    restored = (await client.get('/api/menu/lunch')).json()
    assert restored['available'] is True and restored['sabjiOptions'] == ['Aloo']


async def test_catalogue_name_case_and_whitespace_do_not_bypass_sabji_availability(mess_client):
    client, _, _ = await ready(mess_client)
    async with mess_client[1]() as db:
        paneer = await db.get(FoodItem, 'paneer-id')
        paneer.name = '  pAnEeR  '
        await db.commit()
    await toggle(client, 'Paneer', False)
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is True and current['sabjiOptions'] == ['Aloo']
    assert 'Paneer' not in current['contents']
    await assert_configuration_preserved(mess_client[1])


async def test_unavailable_salad_blocks_chapati_but_thali_uses_remaining_configured_contents(mess_client):
    client, headers, _ = await ready(mess_client)
    async with mess_client[1]() as db:
        salad = FoodItem(id='salad-id', name='Salad', price=10, category='Meals',
                         is_available=True, timing_window='all_day', customizations=[])
        db.add(salad)
        await attach_test_image(db, salad)
        await db.commit()
    await toggle(client, 'Salad', False)
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is True and current['sabjiOptions'] == SABJIS
    by_id = {row['id']: row for row in current['options']}
    assert by_id['lunch-chapati-bhaji']['available'] is False
    assert by_id['lunch-thali']['available'] is True
    rejected = await order(client, headers, [item(current, choice='Aloo')])
    assert rejected.status_code == 409, rejected.text
    expected = [name for name in CONTENTS if name != 'Salad']
    assert current['contents'] == expected
    accepted = await order(client, headers, [item(current, thali=True)])
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()['total'] == 80
    assert accepted.json()['items'][0]['contents'] == expected
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('420')
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 1
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 1
    await assert_configuration_preserved(mess_client[1])
