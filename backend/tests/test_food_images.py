"""Real upload/decode, publication, historical delivery and quota boundaries."""
import hashlib
import io
from decimal import Decimal

import pytest
from PIL import Image
from sqlalchemy import func, select

from auth import create_access_token
from config import settings
from food_image_models import FoodImage
from image_service import MAX_UPLOAD_BYTES, optimize_photo
from models import FoodItem, Order
from image_fixtures import photo_bytes
from test_mess import mess_client
import admin_operations
import student_routes


@pytest.fixture(autouse=True)
def image_configuration(monkeypatch):
    monkeypatch.setattr(settings, 'PUBLIC_API_ORIGIN', 'http://test')
    monkeypatch.setattr(settings, 'FOOD_IMAGE_LIBRARY_MAX_BYTES', 64 * 1024 * 1024)
    monkeypatch.setattr(settings, 'RATE_LIMIT_ENABLED', False)
    async def no_cache(*args, **kwargs):
        return None
    for target, names in ((admin_operations, ('cache_invalidate_prefix',)), (student_routes, ('cache_get','cache_set','cache_invalidate_prefix'))):
        for name in names:
            monkeypatch.setattr(target, name, no_cache)


async def upload(client, *, color=(220, 80, 40), **metadata):
    fields = {'dishName': 'New genuine dish', 'source': 'Owner supplied photograph', 'license': 'Owner permission',
        'attribution': 'Canteen manager photograph', 'rightsConfirmed': 'true', 'author': 'Test manager',
        'licenseUrl': 'https://creativecommons.org/licenses/by/4.0/'}
    fields.update(metadata)
    return await client.post('/api/admin/food-images', data=fields,
        files={'file': ('dish.png', photo_bytes(color), 'image/png')})


async def published_item(client, image, *, name='Actual dish'):
    response = await client.post('/api/admin/catalogue', json={'name': name, 'price': 25, 'category': 'Snacks',
        'available': True, 'imageId': image['id'], 'imageConfirmed': True})
    assert response.status_code == 201, response.text
    return response.json()


async def test_authentication_precedes_multipart_parsing_and_private_preview(mess_client):
    client, _, _ = mess_client
    for method,path in (('get','/api/admin/food-images'), ('post','/api/admin/food-images'),
        ('get','/api/admin/food-images/'+'a'*32+'/content')):
        assert (await getattr(client, method)(path, headers={'Authorization': ''})).status_code == 401
    assert (await client.post('/api/admin/food-images', headers={'Authorization': 'Bearer '+create_access_token({'sub':'linked-student','role':'student'})})).status_code == 403
    assert (await client.get('/api/food-images/'+'a'*32)).status_code == 404


async def test_upload_optimized_private_deduplicated_and_metadata_retained(mess_client):
    client,sessions,_ = mess_client
    first = await upload(client)
    assert first.status_code == 201, first.text
    image = first.json()
    assert len(image['id']) == 32 and image['mimeType'] == 'image/webp'
    assert image['byteSize'] <= 327680 and not image['published']
    assert image['photo'] == 'http://test/api/food-images/'+image['id']
    assert image['source']=='Owner supplied photograph' and image['author']=='Test manager'
    assert (await client.get(image['photo'])).status_code == 404
    assert (await client.get(image['creditsUrl'])).status_code == 404
    preview = await client.get(image['previewUrl'])
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/webp'
    assert preview.headers['cache-control'] == 'private, no-store'
    assert hashlib.sha256(preview.content).hexdigest()==image['sha256']
    assert (await client.get('/api/admin/food-images/'+image['id'])).json()==image
    second=await upload(client)
    assert second.status_code==201 and second.json()['id']==image['id']
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(FoodImage))).scalar_one()==1
    assert len((await client.get('/api/admin/food-images?query=genuine')).json())==1
    assert (await client.get('/api/admin/food-images?query=does-not-match')).json()==[]


async def test_publication_confirmation_and_library_reuse(mess_client):
    client,_,_=mess_client
    assert (await client.post('/api/admin/catalogue',json={'name':'Missing image','price':25,'available':True})).status_code==422
    draft=await client.post('/api/admin/catalogue',json={'name':'Draft dish','price':25})
    assert draft.status_code==201 and draft.json()['available'] is False and draft.json()['imageId'] is None
    image=(await upload(client)).json()
    assert (await client.post('/api/admin/catalogue',json={'name':'Unconfirmed','price':25,'available':True,'imageId':image['id']})).status_code==422
    item=await published_item(client,image)
    result=await client.get(item['photo'])
    assert result.status_code==200 and result.headers['x-content-type-options']=='nosniff'
    assert 'immutable' in result.headers['cache-control']
    etag=result.headers['etag']
    assert (await client.get(item['photo'],headers={'If-None-Match':etag})).status_code==304
    credits=(await client.get(item['photoCredits'])).json()
    assert credits['license']=='Owner permission' and credits['author']=='Test manager'
    assert 'metadata removed' in credits['modifications']
    assert (await client.delete('/api/admin/food-images/'+image['id'])).status_code==409
    assert (await client.patch('/api/admin/catalogue/'+item['id']+'/availability',json={'available':False})).status_code==200
    assert (await client.patch('/api/admin/catalogue/'+item['id']+'/availability',json={'available':True})).status_code==200
    assert (await client.put('/api/admin/catalogue/'+item['id'],json={'name':'Different dish'})).status_code==422
    renamed=await client.put('/api/admin/catalogue/'+item['id'],json={'name':'Different dish','imageConfirmed':True})
    assert renamed.status_code==200
    assert (await client.post('/api/admin/catalogue',json={'name':'Invented URL','price':25,'photo':'https://wrong.example/a.jpg','available':True})).status_code==422


async def test_replacement_removal_archiving_preserve_historical_order_photos(mess_client):
    client,sessions,_=mess_client
    first=(await upload(client)).json()
    item=await published_item(client,first)
    async with sessions() as db:
        old=Order(order_number='#PHOTO-HISTORY',student_id='linked-student',items_json=[{'id':item['id'],'photo':item['photo'],'price':25,'qty':1}],item_total=25,total_amount=25,order_status='Queued',payment_status='Paid')
        db.add(old); await db.commit()
    second=(await upload(client,color=(30,150,70))).json()
    assert (await client.put('/api/admin/catalogue/'+item['id'],json={'imageId':second['id']})).status_code==422
    changed=await client.put('/api/admin/catalogue/'+item['id'],json={'imageId':second['id'],'imageConfirmed':True})
    assert changed.status_code==200 and changed.json()['photo']!=item['photo']
    assert (await client.delete('/api/admin/food-images/'+first['id'])).status_code==200
    assert (await client.get(item['photo'])).status_code==200
    assert (await client.get('/api/admin/food-images/'+first['id'])).status_code==404
    removed=await client.put('/api/admin/catalogue/'+item['id'],json={'imageId':None,'available':True})
    assert removed.status_code==200 and removed.json()['available'] is False and removed.json()['photo']==''
    assert (await client.patch('/api/admin/catalogue/'+item['id']+'/availability',json={'available':True,'imageConfirmed':True})).status_code==422
    async with sessions() as db:
        old=(await db.execute(select(Order).where(Order.order_number=='#PHOTO-HISTORY'))).scalar_one()
        assert old.items_json[0]['photo']==item['photo'] and old.total_amount==Decimal('25')
        assert await db.get(FoodItem,item['id']) is not None


async def test_quota_is_authoritative_and_failure_does_not_leave_rows(mess_client,monkeypatch):
    client,sessions,_=mess_client
    first=(await upload(client)).json()
    monkeypatch.setattr(settings,'FOOD_IMAGE_LIBRARY_MAX_BYTES',first['byteSize'])
    assert (await upload(client)).status_code==201  # Exact dedup consumes no additional bytes.
    denied=await upload(client,color=(10,40,120))
    assert denied.status_code==413
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(FoodImage))).scalar_one()==1


async def test_upload_rejects_unlicensed_missing_invalid_and_oversized_content(mess_client):
    client,_,_=mess_client
    assert (await upload(client,rightsConfirmed='false')).status_code==422
    assert (await upload(client,licenseUrl='javascript:alert(1)')).status_code==422
    assert (await client.post('/api/admin/food-images',data={'dishName':'Dish'})).status_code==415
    fields={'dishName':'Dish','source':'Owner','license':'Owner','attribution':'Owner','rightsConfirmed':'true'}
    for raw,mime,expected in ((b'<svg/>','image/svg+xml',415),(b'bad','image/png',422),
        (photo_bytes(),'image/jpeg',415),(photo_bytes(size=(32,96)),'image/png',422),
        (b'x'*(MAX_UPLOAD_BYTES+1),'image/png',413)):
        response=await client.post('/api/admin/food-images',data=fields,files={'file':('upload.png',raw,mime)})
        assert response.status_code==expected,response.text


def test_optimized_photo_strips_exif_and_rejects_animation_and_excessive_pixels():
    raw=io.BytesIO()
    exif=Image.Exif(); exif[0x010e]='Private embedded location metadata'
    Image.new('RGB',(1800,1200),'orange').save(raw,format='JPEG',exif=exif)
    content,width,height=optimize_photo(raw.getvalue(),'image/jpeg')
    assert max(width,height)==1280 and len(content)<=327680
    with Image.open(io.BytesIO(content)) as decoded:
        assert not decoded.getexif() and 'exif' not in decoded.info
    animated=io.BytesIO()
    frames=[Image.new('RGB',(128,96),color) for color in ('red','green')]
    frames[0].save(animated,format='WEBP',save_all=True,append_images=frames[1:],duration=100,loop=0)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        optimize_photo(animated.getvalue(),'image/webp')
    assert error.value.status_code==422
    with pytest.raises(HTTPException) as error:
        optimize_photo(photo_bytes(size=(3000,3000)),'image/png')
    assert error.value.status_code==422


async def test_missing_public_origin_fails_before_upload_commit(mess_client,monkeypatch):
    client,sessions,_=mess_client
    monkeypatch.setattr(settings,'PUBLIC_API_ORIGIN','')
    assert (await upload(client)).status_code==503
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(FoodImage))).scalar_one()==0


async def test_source_modifications_retained_with_backend_conversion_note(mess_client):
    client,_,_=mess_client
    response=await upload(client,modifications="Cropped original dish photograph.")
    assert response.status_code==201,response.text
    note=response.json()["modifications"]
    assert note.startswith("Cropped original dish photograph.") and "EXIF" in note and len(note)<=255


async def test_parallel_uploads_cannot_overrun_postgresql_quota(mess_client,monkeypatch):
    client,sessions,postgres=mess_client
    if not postgres:
        pytest.skip("PostgreSQL required for advisory-lock concurrency; isolated schema only")
    import asyncio
    first=optimize_photo(photo_bytes((20,100,40)),"image/png")[0]
    second=optimize_photo(photo_bytes((100,40,20)),"image/png")[0]
    monkeypatch.setattr(settings,"FOOD_IMAGE_LIBRARY_MAX_BYTES",len(first)+len(second)-1)
    responses=await asyncio.gather(upload(client,color=(20,100,40)),upload(client,color=(100,40,20)))
    assert sorted(response.status_code for response in responses)==[201,413]
    async with sessions() as db:
        assert (await db.execute(select(func.count()).select_from(FoodImage))).scalar_one()==1
        assert (await db.execute(select(func.sum(FoodImage.byte_size)))).scalar_one()<=settings.FOOD_IMAGE_LIBRARY_MAX_BYTES
