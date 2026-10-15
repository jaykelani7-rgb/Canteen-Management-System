"""OCR weekly-menu replacement must invalidate stale lunch choices safely."""
from decimal import Decimal

from sqlalchemy import func, select

from models import Order, StudentUser, WalletTransaction, WeeklyMenu
from test_lunch import CONTENTS, SABJIS, configure, deterministic_lunch, item, order, ready
from test_mess import mess_client

NEW_CONTENTS = ['3 chapatis', 'Salad', 'Bhindi', 'Rajma', 'Dal', 'Rice']
NEW_SABJIS = ['Bhindi', 'Rajma']


async def import_menu(client, rows=None):
    """Match OCR review/save: it sends no lunch-configuration fields."""
    return await client.post('/api/admin/menu/weekly', json={'schedule': rows or [
        {'day': 'Thursday', 'meal_type': 'lunch', 'items': NEW_CONTENTS}
    ]})


async def saved_rows(fixture):
    async with fixture[1]() as db:
        return {
            (row.day, row.meal_type): {
                'items': list(row.items), 'sabji_options': list(row.sabji_options),
                'ordering_enabled': bool(row.ordering_enabled),
            }
            for row in (await db.execute(select(WeeklyMenu))).scalars()
        }


async def test_ocr_replacement_clears_invalid_choices_and_disables_ordering(mess_client):
    client, _, old_lunch = await ready(mess_client)
    response = await import_menu(client)
    assert response.status_code == 200, response.text
    replacement = response.json()['schedule'][0]
    assert replacement['items'] == NEW_CONTENTS
    assert replacement['sabji_options'] == []
    assert replacement['ordering_enabled'] is False
    saved = (await saved_rows(mess_client))[('Thursday', 'lunch')]
    assert saved == {
        'items': NEW_CONTENTS, 'sabji_options': [], 'ordering_enabled': False,
    }
    current = (await client.get('/api/menu/lunch')).json()
    assert current['contents'] == NEW_CONTENTS and current['sabjiOptions'] == []
    assert current['available'] is False
    assert current['mealRevision'] != old_lunch['mealRevision']

async def test_ocr_replacement_requires_admin_reconfiguration_and_preserves_history(mess_client):
    client, headers, lunch = await ready(mess_client)
    placed = await order(client, headers, [item(lunch, thali=True)])
    assert placed.status_code == 201, placed.text
    snapshot = placed.json()
    assert (await import_menu(client)).status_code == 200
    disabled = (await client.get('/api/menu/lunch')).json()
    for thali in (False, True):
        for state in (lunch, disabled):
            rejected = await order(client, headers, [item(state, thali=thali)])
            assert rejected.status_code == 409, rejected.text
    # Omitted configuration fields must never infer choices or re-enable service.
    assert (await import_menu(client)).status_code == 200
    current = (await client.get('/api/menu/lunch')).json()
    assert current['sabjiOptions'] == [] and current['available'] is False
    enable_only = await client.post('/api/admin/menu/weekly', json={'schedule': [{
        'day': 'Thursday', 'meal_type': 'lunch', 'items': NEW_CONTENTS,
        'ordering_enabled': True,
    }]})
    assert enable_only.status_code == 422, enable_only.text
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('420')
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 1
        assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 1
        assert (await db.get(Order, snapshot['orderId'])).items_json == snapshot['items']
    # Only an explicit valid Admin configuration restores the two fixed-price meals.
    configured = await configure(client, items=NEW_CONTENTS, sabji_options=NEW_SABJIS)
    assert configured.status_code == 200, configured.text
    enabled = (await client.get('/api/menu/lunch')).json()
    assert enabled['available'] is True and enabled['sabjiOptions'] == NEW_SABJIS
    chapati = await order(client, headers, [item(enabled, choice='Bhindi')])
    thali = await order(client, headers, [item(enabled, thali=True)])
    assert chapati.status_code == thali.status_code == 201
    assert chapati.json()['total'] == 45
    assert chapati.json()['items'][0]['contents'] == ['3 chapatis', 'Salad', 'Bhindi']
    assert thali.json()['total'] == 80 and thali.json()['items'][0]['contents'] == NEW_CONTENTS
    history = await client.get('/api/student/orders/' + str(snapshot['orderId']), headers=headers)
    assert history.status_code == 200 and history.json()['items'] == snapshot['items']
    async with mess_client[1]() as db:
        assert (await db.get(StudentUser, 'linked-student')).wallet_balance == Decimal('295')
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 3
        assert (await db.get(Order, snapshot['orderId'])).items_json == snapshot['items']


async def test_ocr_batch_saves_other_slots_and_preserves_omitted_entries(mess_client):
    client, _, _ = await ready(mess_client)
    old_other = [
        {'day': 'Monday', 'meal_type': 'breakfast', 'items': ['Idli', 'Chutney']},
        {'day': 'Sunday', 'meal_type': 'dinner', 'items': ['Dal', 'Rice']},
    ]
    assert (await client.post('/api/admin/menu/weekly', json={'schedule': old_other})).status_code == 200
    before = await saved_rows(mess_client)
    rows = [
        {'day': 'Thursday', 'meal_type': 'lunch', 'items': NEW_CONTENTS},
        {'day': 'Monday', 'meal_type': 'breakfast', 'items': ['Dosa', 'Sambar']},
        {'day': 'Friday', 'meal_type': 'snacks', 'items': ['Pohe']},
    ]
    response = await import_menu(client, rows)
    assert response.status_code == 200, response.text
    after = await saved_rows(mess_client)
    assert after[('Thursday', 'lunch')]['items'] == NEW_CONTENTS
    assert after[('Thursday', 'lunch')]['sabji_options'] == []
    assert after[('Thursday', 'lunch')]['ordering_enabled'] is False
    assert after[('Monday', 'breakfast')]['items'] == ['Dosa', 'Sambar']
    assert after[('Friday', 'snacks')]['items'] == ['Pohe']
    assert after[('Sunday', 'dinner')] == before[('Sunday', 'dinner')]


async def test_ocr_retains_valid_explicit_lunch_configuration(mess_client):
    client, _, _ = await ready(mess_client)
    response = await import_menu(client, [{
        'day': 'Thursday', 'meal_type': 'lunch', 'items': [*CONTENTS, 'Papad'],
    }])
    assert response.status_code == 200, response.text
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is True and current['sabjiOptions'] == SABJIS
    assert current['contents'] == [*CONTENTS, 'Papad']


async def test_ocr_clears_stale_choices_even_when_ordering_already_disabled(mess_client):
    client, _, _ = await ready(mess_client)
    assert (await configure(client, ordering_enabled=False)).status_code == 200
    response = await import_menu(client)
    assert response.status_code == 200, response.text
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is False and current['sabjiOptions'] == []
    # Restoring the old meal contents through OCR still cannot auto-enable lunch.
    assert (await import_menu(client, [{
        'day': 'Thursday', 'meal_type': 'lunch', 'items': CONTENTS,
    }])).status_code == 200
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is False and current['sabjiOptions'] == []


async def test_explicit_invalid_admin_enable_rejects_entire_batch_atomically(mess_client):
    client, _, _ = await ready(mess_client)
    before = await saved_rows(mess_client)
    response = await client.post('/api/admin/menu/weekly', json={'schedule': [
        {'day': 'Monday', 'meal_type': 'breakfast', 'items': ['Dosa']},
        {'day': 'Thursday', 'meal_type': 'lunch', 'items': NEW_CONTENTS,
         'sabji_options': SABJIS, 'ordering_enabled': True},
    ]})
    assert response.status_code == 422, response.text
    assert await saved_rows(mess_client) == before
    current = (await client.get('/api/menu/lunch')).json()
    assert current['available'] is True and current['sabjiOptions'] == SABJIS


async def test_full_ocr_week_preserves_slots_and_disables_only_invalidated_lunch(mess_client):
    client, _, _ = await ready(mess_client)
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    initial = []
    for day in days:
        for meal in ['breakfast', 'lunch', 'snacks', 'dinner']:
            row = {'day': day, 'meal_type': meal, 'items': CONTENTS if meal == 'lunch' else [day + ' ' + meal]}
            if meal == 'lunch':
                row.update(sabji_options=SABJIS, ordering_enabled=True)
            initial.append(row)
    assert (await client.post('/api/admin/menu/weekly', json={'schedule': initial})).status_code == 200
    imported = [{'day': row['day'], 'meal_type': row['meal_type'], 'items': list(row['items'])} for row in initial]
    next(row for row in imported if row['day'] == 'Thursday' and row['meal_type'] == 'lunch')['items'] = NEW_CONTENTS
    response = await import_menu(client, imported)
    assert response.status_code == 200, response.text
    saved = await saved_rows(mess_client)
    assert len(saved) == 28
    for row in imported:
        current = saved[(row['day'], row['meal_type'])]
        assert current['items'] == row['items']
        if row['meal_type'] == 'lunch' and row['day'] != 'Thursday':
            assert current['sabji_options'] == SABJIS and current['ordering_enabled'] is True
        else:
            assert current['sabji_options'] == [] and current['ordering_enabled'] is False
