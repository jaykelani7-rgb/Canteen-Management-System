"""OCR tests never call a live provider and use isolated admin/data fixtures."""
import io
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi import HTTPException
from pydantic import ValidationError
import ocr_router
from test_mess import mess_client

def png(size=(8,8)):
    out=io.BytesIO()
    Image.new("RGB",size,"white").save(out,format="PNG")
    return out.getvalue()

async def test_ocr_requires_admin_before_provider(mess_client,monkeypatch):
    client,_,_=mess_client
    async def forbidden(*args): raise AssertionError("Provider must not be called")
    monkeypatch.setattr(ocr_router,"extract_menu",forbidden)
    response=await client.post("/api/admin/menu/upload-ocr",headers={"Authorization":""},files={"file":("menu.png",png(),"image/png")})
    assert response.status_code==401

@pytest.mark.parametrize("body,mime,status",[(b"","image/png",400),(b"not an image","image/png",400),(b"fake","text/plain",400)])
async def test_ocr_rejects_invalid_upload(mess_client,monkeypatch,body,mime,status):
    client,_,_=mess_client
    async def forbidden(*args): raise AssertionError("Provider must not be called")
    monkeypatch.setattr(ocr_router,"extract_menu",forbidden)
    assert (await client.post("/api/admin/menu/upload-ocr",files={"file":("menu",body,mime)})).status_code==status

async def test_ocr_rejects_byte_and_pixel_limits(mess_client,monkeypatch):
    client,_,_=mess_client
    monkeypatch.setattr(ocr_router,"MAX_UPLOAD_BYTES",12)
    assert (await client.post("/api/admin/menu/upload-ocr",files={"file":("menu.png",b"x"*13,"image/png")})).status_code==413
    monkeypatch.setattr(ocr_router,"MAX_UPLOAD_BYTES",1024)
    monkeypatch.setattr(ocr_router,"MAX_IMAGE_PIXELS",16)
    assert (await client.post("/api/admin/menu/upload-ocr",files={"file":("menu.png",png(),"image/png")})).status_code==400

async def test_ocr_valid_extract_does_not_save_weekly_menu(mess_client,monkeypatch):
    from sqlalchemy import select,func
    from models import WeeklyMenu as StoredMenu
    client,sessions,_=mess_client
    async def extract(*args): return ocr_router.WeeklyMenu(schedule=[{"day":"Monday","meal_type":"lunch","items":["Dal","Rice"]}])
    monkeypatch.setattr(ocr_router,"extract_menu",extract)
    response=await client.post("/api/admin/menu/upload-ocr",files={"file":("menu.png",png(),"image/png")})
    assert response.status_code==200
    assert response.json()["schedule"][0]["items"]==["Dal","Rice"]
    async with sessions() as db: assert (await db.execute(select(func.count()).select_from(StoredMenu))).scalar_one()==0

@pytest.mark.parametrize("schedule",[
    [{"day":"Funday","meal_type":"lunch","items":["Rice"]}],
    [{"day":"Monday","meal_type":"brunch","items":["Rice"]}],
    [{"day":"Monday","meal_type":"lunch","items":[""]}],
    [{"day":"Monday","meal_type":"lunch","items":["Rice"]}]*2,
])
def test_ocr_validates_provider_schedule(schedule):
    with pytest.raises(ValidationError): ocr_router.WeeklyMenu(schedule=schedule)

async def test_ocr_provider_errors_are_generic(monkeypatch):
    def broken(**kwargs): raise RuntimeError("provider-sensitive-internal-detail")
    monkeypatch.setattr(ocr_router.genai,"Client",broken)
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==502
    assert "sensitive" not in error.value.detail

async def test_ocr_provider_timeout_is_bounded(monkeypatch):
    import asyncio
    async def generate(**kwargs): await asyncio.sleep(1)
    async def close(): pass
    monkeypatch.setattr(ocr_router.genai,"Client",lambda **kwargs: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate),aclose=close)))
    monkeypatch.setattr(ocr_router,"settings",SimpleNamespace(OCR_TIMEOUT_SECONDS=0.01))
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==504
