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
    monkeypatch.setattr(ocr_router,"settings",SimpleNamespace(GEMINI_API_KEY="test-only-key"))
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==502
    assert "sensitive" not in error.value.detail

async def test_ocr_provider_timeout_is_bounded(monkeypatch):
    import asyncio
    async def generate(**kwargs): await asyncio.sleep(1)
    async def close(): pass
    monkeypatch.setattr(ocr_router.genai,"Client",lambda **kwargs: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate),aclose=close)))
    monkeypatch.setattr(ocr_router,"settings",SimpleNamespace(GEMINI_API_KEY="test-only-key",OCR_TIMEOUT_SECONDS=0.01))
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==504

@pytest.mark.parametrize("key", ["", "   ", None])
async def test_ocr_missing_key_is_actionable_without_constructing_provider(monkeypatch,key,caplog):
    def forbidden(**kwargs): raise AssertionError("Provider must not be constructed without configuration")
    monkeypatch.setattr(ocr_router.genai,"Client",forbidden)
    monkeypatch.setattr(ocr_router,"settings",SimpleNamespace(GEMINI_API_KEY=key))
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==503
    assert "GEMINI_API_KEY" in error.value.detail and "privately" in error.value.detail
    assert "not configured" in caplog.text

def provider(monkeypatch,generate,key="test-only-sensitive-key",timeout=30):
    calls={"closed":False}
    async def close(): calls["closed"]=True
    def client(**kwargs):
        calls["constructor"]=kwargs
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate),aclose=close))
    monkeypatch.setattr(ocr_router.genai,"Client",client)
    monkeypatch.setattr(ocr_router,"settings",SimpleNamespace(GEMINI_API_KEY=key,OCR_MODEL="gemini-2.5-flash",OCR_TIMEOUT_SECONDS=timeout))
    return calls

async def test_ocr_uses_explicit_configured_key_strict_schema_and_closes_client(monkeypatch):
    requests=[]
    async def generate(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(text='{"schedule":[{"day":"monday","meal_type":"LUNCH","items":["Dal","Rice"]}]}')
    calls=provider(monkeypatch,generate)
    extracted=await ocr_router.extract_menu(png(),"image/png")
    assert extracted.schedule[0].day=="Monday" and extracted.schedule[0].meal_type=="lunch"
    assert calls["constructor"]["api_key"]=="test-only-sensitive-key"
    assert calls["constructor"]["vertexai"] is False
    assert calls["constructor"]["http_options"].retry_options.attempts==1
    assert requests[0]["model"]=="gemini-2.5-flash"
    assert requests[0]["config"].response_schema is ocr_router.WeeklyMenu
    assert calls["closed"] is True

@pytest.mark.parametrize("code,status,hint",[(401,502,"credentials"),(403,502,"permissions"),(429,503,"quota"),(503,503,"temporarily"),(400,502,"OCR_MODEL"),(404,502,"OCR_MODEL"),(500,502,"unavailable")])
async def test_ocr_provider_error_classification_is_sanitized(monkeypatch,caplog,code,status,hint):
    async def generate(**kwargs):
        raise ocr_router.errors.APIError(code,{"error":{"code":code,"message":"provider-sensitive-internal-detail test-only-sensitive-key"}})
    calls=provider(monkeypatch,generate)
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==status and hint in error.value.detail
    assert "sensitive" not in error.value.detail and "sensitive" not in caplog.text
    assert calls["closed"] is True
    if code in (429,503): assert error.value.headers=={"Retry-After":"60"}

@pytest.mark.parametrize("body",[None,"", "not-json", '{"schedule":[]}', '{"schedule":[{"day":"Monday","meal_type":"brunch","items":["Rice"]}]}', '{"schedule":[{"day":"Monday","meal_type":"lunch","items":["Rice"]},{"day":"Monday","meal_type":"lunch","items":["Dal"]}]}'])
async def test_ocr_malformed_or_invalid_provider_response_requires_retry_not_save(monkeypatch,body):
    async def generate(**kwargs): return SimpleNamespace(text=body)
    calls=provider(monkeypatch,generate)
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==502 and "review" in error.value.detail
    assert calls["closed"] is True

async def test_ocr_sdk_network_timeout_is_actionable_and_does_not_leak(monkeypatch):
    async def generate(**kwargs): raise ocr_router.httpx.ReadTimeout("test-only-sensitive-key")
    calls=provider(monkeypatch,generate)
    with pytest.raises(HTTPException) as error: await ocr_router.extract_menu(png(),"image/png")
    assert error.value.status_code==504 and "sensitive" not in error.value.detail
    assert calls["closed"] is True
