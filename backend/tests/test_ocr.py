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
    assert requests[0]["config"].response_schema == ocr_router.provider_menu_schema()
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


@pytest.mark.parametrize("payload,reason,hint",[
    ({"error":{"code":400,"status":"INVALID_ARGUMENT","message":"Rejected request secret-source-token","details":[{"reason":"API_KEY_INVALID","metadata":{"api_key":"secret-source-token"}}]}},"invalid_api_key","invalid or expired"),
    ({"error":{"code":400,"message":"API key not valid. Pass a valid API key secret-source-token"}},"invalid_api_key","invalid or expired"),
    ({"error":{"code":400,"message":"This model is not available for new projects secret-source-token"}},"model_unavailable","free-tier model"),
    ({"error":{"code":404,"message":"models/old-model is not found for API version v1beta secret-source-token"}},"model_unavailable","free-tier model"),
    ({"error":{"code":404,"status":"NOT_FOUND","message":"This model models/old-model is no longer available to new users. Please update your code to use models/new-model for the latest features and improvements."}},"model_unavailable","free-tier model"),
    ({"error":{"code":400,"message":"Unsupported request field secret-source-token","details":[{"reason":"secret-source-token"}]}},"request_invalid","OCR_MODEL"),
])
async def test_ocr_precise_provider_reason_never_logs_raw_details(monkeypatch,caplog,payload,reason,hint):
    code=payload["error"]["code"]
    async def generate(**kwargs):
        raise ocr_router.errors.APIError(code,payload)
    calls=provider(monkeypatch,generate)
    with pytest.raises(HTTPException) as response:
        await ocr_router.extract_menu(png(),"image/png")
    assert response.value.status_code==502 and hint in response.value.detail
    assert "reason="+reason in caplog.text
    for sensitive in ("secret-source-token","test-only-sensitive-key","metadata","old-model"):
        assert sensitive not in caplog.text and sensitive not in response.value.detail
    assert calls["closed"] is True


@pytest.mark.parametrize("details",[None,[],"unexpected provider body",{"error":{"details":"malformed"}},{"error":{"details":[None,4,{"reason":[]}]}}])
def test_ocr_reason_classifier_handles_malformed_provider_metadata(details):
    error=ocr_router.errors.APIError(400,details)
    assert ocr_router.provider_failure_reason(error)=="request_invalid"


@pytest.mark.parametrize("code,reason,expected",[(403,"permissions",502),(429,"quota_or_unavailable",503),(503,"quota_or_unavailable",503)])
async def test_ocr_transient_or_permissions_error_not_misclassified_as_model_config(monkeypatch,caplog,code,reason,expected):
    async def generate(**kwargs):
        raise ocr_router.errors.APIError(code,{"error":{"code":code,"message":"The model is unavailable secret-source-token"}})
    provider(monkeypatch,generate)
    with pytest.raises(HTTPException) as result:
        await ocr_router.extract_menu(png(),"image/png")
    assert result.value.status_code==expected and "reason="+reason in caplog.text
    assert "secret-source-token" not in caplog.text and "secret-source-token" not in result.value.detail
    if code in (429,503): assert result.value.headers=={"Retry-After":"60"}


@pytest.mark.parametrize("code,payload,reason,hint",[
    (400,{"message":"Your API key was reported as leaked. Please use another API key. secret-source-token"},"compromised_api_key","leaked or revoked"),
    (403,{"message":"API key has been revoked secret-source-token"},"compromised_api_key","leaked or revoked"),
    (400,{"details":[{"reason":"API_KEY_NOT_VALID"}],"message":"Rejected secret-source-token"},"invalid_api_key","invalid or expired"),
    (403,{"details":[{"reason":"API_KEY_SERVICE_BLOCKED"}],"message":"Rejected secret-source-token"},"project_access_restricted","API access"),
    (400,{"details":[{"reason":"SERVICE_DISABLED"}],"message":"Rejected secret-source-token"},"project_access_restricted","API access"),
    (400,{"details":[{"reason":"CONSUMER_INVALID"}],"message":"Rejected secret-source-token"},"project_access_restricted","API access"),
    (400,{"details":[{"reason":"BILLING_DISABLED"}],"message":"Rejected secret-source-token"},"free_tier_prerequisite","do not enable paid billing"),
    (400,{"message":"Gemini API free tier is not available in your country. Please enable billing secret-source-token"},"free_tier_prerequisite","do not enable paid billing"),
    (400,{"message":"User location is not supported for the API use secret-source-token"},"region_or_free_tier_unavailable","server location"),
    (400,{"message":"Invalid JSON payload received. Unknown name additionalProperties at generation_config.response_schema secret-source-token"},"response_schema_rejected","response schema"),
    (400,{"message":"responseSchema cannot include an unsupported field secret-source-token"},"response_schema_rejected","response schema"),
])
async def test_ocr_provider_prerequisites_are_specific_and_never_leak(monkeypatch,caplog,code,payload,reason,hint):
    async def generate(**kwargs):
        raise ocr_router.errors.APIError(code,{"error":{"code":code,**payload}})
    calls=provider(monkeypatch,generate)
    with pytest.raises(HTTPException) as result:
        await ocr_router.extract_menu(png(),"image/png")
    assert result.value.status_code==502 and hint in result.value.detail
    assert "reason="+reason in caplog.text
    assert "secret-source-token" not in caplog.text and "test-only-sensitive-key" not in caplog.text
    assert "secret-source-token" not in result.value.detail
    assert calls["closed"] is True


@pytest.mark.parametrize("code",[429,503])
def test_ocr_quota_has_precedence_over_incidental_project_or_schema_phrases(code):
    error=ocr_router.errors.APIError(code,{"error":{"code":code,"message":"Check billing or response_schema secret-source-token","details":[{"reason":"BILLING_DISABLED"}]}})
    assert ocr_router.provider_failure_reason(error)=="quota_or_unavailable"


def test_sanitized_provider_diagnostics_preserve_error_not_credentials():
    key = "AIza" + "sensitive_key_" * 3
    error = ocr_router.errors.APIError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
        "message": "Unknown name additionalProperties at generation_config.response_schema. " + key + " secret-source-token https://provider.invalid/?key=hidden Bearer confidential-value",
        "details": [{"reason": "API_KEY_SERVICE_BLOCKED", "metadata": {"key": key, "consumer": "private-project"}}]}})
    result = ocr_router.sanitized_provider_error(error, key)
    assert result["code"] == 400 and result["status"] == "INVALID_ARGUMENT"
    assert result["reasons"] == ["API_KEY_SERVICE_BLOCKED"]
    assert "additionalProperties" in result["message"]
    for value in (key, "secret-source-token", "hidden", "confidential-value", "private-project"):
        assert value not in str(result)
    assert "metadata" not in result


def test_sanitized_provider_diagnostics_omit_oversized_payload():
    error = ocr_router.errors.APIError(400, {"error": {"code": 400, "message": "x" * 5000}})
    assert ocr_router.sanitized_provider_error(error, "private-key")["message"] == "[oversized provider message omitted]"


async def test_real_sdk_wire_schema_omits_rejected_field_and_preserves_image(monkeypatch):
    """Intercept the installed SDK's actual HTTP JSON, without contacting Gemini."""
    import base64
    import json
    import httpx
    observed = []
    original_client = ocr_router.genai.Client

    async def transport(request):
        body = json.loads(request.content)
        schema = body['generationConfig']['responseSchema']
        serialized = json.dumps(schema)
        assert 'additional_properties' not in serialized and 'additionalProperties' not in serialized
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert schema['required'] == ['schedule']
        meal = schema['properties']['schedule']['items']
        assert meal['required'] == ['day', 'meal_type', 'items']
        assert 'Monday' in meal['properties']['day']['enum']
        assert set(meal['properties']['meal_type']['enum']) == {'breakfast', 'lunch', 'snacks', 'dinner'}
        part = body['contents'][0]['parts'][0]['inlineData']
        assert part.get('mimeType', part.get('mime_type')) == 'image/png'
        with Image.open(io.BytesIO(base64.urlsafe_b64decode(part['data']))) as actual:
            assert actual.format == 'PNG' and actual.size == (8, 8)
        assert str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent'
        observed.append(True)
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [
            {'text': '{"schedule":[{"day":"Monday","meal_type":"lunch","items":["Dal","Rice"]}]}'}]}}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    def client(**kwargs):
        kwargs['http_options'] = kwargs['http_options'].model_copy(update={'httpx_async_client': http})
        return original_client(**kwargs)
    monkeypatch.setattr(ocr_router.genai, 'Client', client)
    monkeypatch.setattr(ocr_router, 'settings', SimpleNamespace(GEMINI_API_KEY='offline-test-key', OCR_TIMEOUT_SECONDS=30))
    result = await ocr_router.extract_menu(png(), 'image/png')
    assert observed == [True] and result.schedule[0].items == ['Dal', 'Rice']
    await http.aclose()  # The SDK leaves caller-owned HTTP clients to their owner.
    assert http.is_closed


def test_provider_schema_compatibility_does_not_relax_local_menu_validation():
    with pytest.raises(ValidationError):
        ocr_router.WeeklyMenu.model_validate({'schedule': [{'day': 'Monday', 'meal_type': 'lunch', 'items': ['Rice'], 'unexpected': 'ignored?'}]})
    with pytest.raises(ValidationError):
        ocr_router.WeeklyMenu.model_validate({'schedule': [{'day': 'Monday', 'meal_type': 'lunch', 'items': ['Rice']}], 'unexpected': True})
