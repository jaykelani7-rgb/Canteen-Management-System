"""Both frontend origins share one API without sharing authorization roles."""
import pytest
from httpx import ASGITransport, AsyncClient
from main import app
from auth import create_access_token, get_optional_student
from fastapi.security import HTTPAuthorizationCredentials
from test_mess import mess_client


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:8443", "http://127.0.0.1:5173", "http://127.0.0.1:8443"])
async def test_frontend_origin_preflight(origin):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options("/api/auth/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "Origin" in response.headers.get("vary", "")


async def test_unconfigured_origin_is_not_allowed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options("/api/admin/me", headers={"Origin": "https://unconfigured.example", "Access-Control-Request-Method": "GET"})
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


async def test_frontend_sessions_do_not_cross_roles(mess_client):
    client, _, _ = mess_client
    assert (await client.get("/api/auth/me")).status_code in (401, 403)
    token = create_access_token({"sub": "linked-student", "role": "student"})
    response = await client.get("/api/admin/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code in (401, 403)


async def test_admin_role_cannot_impersonate_matching_student_identifier(mess_client):
    client, sessions, _ = mess_client
    token = create_access_token({"sub": "linked-student", "role": "admin"})
    assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer " + token})).status_code == 403
    async with sessions() as db:
        assert await get_optional_student(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db) is None
