from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Optional
from urllib.parse import urlsplit

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import AdminUser, StudentUser
from schemas import TokenPayload

security = HTTPBearer(scheme_name="JWT Bearer Token", auto_error=False)
optional_security = security
COOKIE_NAMES = {"student": "canteen_student", "admin": "canteen_admin"}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        raw = plain_password.encode("utf-8")
        if not raw or len(raw) > 72 or not hashed_password:
            return False
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except (ValueError, TypeError, UnicodeError):
        return False


def get_password_hash(password: str) -> str:
    raw = password.encode("utf-8")
    if not raw or len(raw) > 72:
        raise ValueError("Password must contain between 1 and 72 UTF-8 bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def normalize_roll_number(roll: str) -> str:
    return "".join(roll.upper().split()) if roll else ""


def credential_fingerprint(password_hash: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), password_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    if not isinstance(data.get("sub"), str) or not data["sub"] or not isinstance(data.get("role"), str):
        raise ValueError("Token subject and role are required")
    now = datetime.now(timezone.utc)
    claims = dict(data)
    claims.update({"exp": now + (expires_delta if expires_delta is not None else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)), "iat": now})
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                            options={"require": ["exp", "iat", "sub", "role"]})
        if (not isinstance(claims["sub"], str) or not claims["sub"]
                or claims["role"] not in {"student", "admin"}
                or not isinstance(claims["exp"], int) or isinstance(claims["exp"], bool)
                or not isinstance(claims["iat"], int) or isinstance(claims["iat"], bool)):
            raise jwt.InvalidTokenError("Invalid claims")
        return TokenPayload(sub=claims["sub"], role=claims["role"], exp=claims["exp"],
                            credential_version=claims.get("credential_version"))
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired session",
                            headers={"WWW-Authenticate": "Bearer"})


def validate_session_origin(request: Request, role: str) -> None:
    # Ports share cookies in development, and sibling production hosts are
    # same-site. Authorize the requesting application independently of CORS.
    source = request.headers.get("origin")
    from_referer = False
    if not source and request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        source = request.headers.get("referer")
        from_referer = True
    try:
        parsed = urlsplit(source or "")
        if (role not in COOKIE_NAMES or parsed.scheme not in {"http", "https"}
                or not parsed.netloc or not parsed.hostname or parsed.username or parsed.password
                or (not from_referer and (parsed.path not in ("", "/") or parsed.query or parsed.fragment))):
            raise ValueError("Invalid origin")
        # Validate the port syntax without accepting credentials or opaque origins.
        _ = parsed.port
        origin = parsed.scheme + "://" + parsed.netloc
        values = settings.ADMIN_CORS_ORIGINS if role == "admin" else settings.STUDENT_CORS_ORIGINS
        if origin not in {value.rstrip("/") for value in values}:
            raise ValueError("Origin does not belong to this role")
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def issue_session(response: Response, request: Request, token: str, role: str) -> bool:
    cookie_mode = request.headers.get("x-session-mode", "").lower() == "cookie"
    if not cookie_mode:
        return False
    if not settings.SESSION_COOKIE_MODE_ENABLED:
        raise HTTPException(status_code=503, detail="Cookie sessions are unavailable")
    validate_session_origin(request, role)
    response.set_cookie(COOKIE_NAMES[role], token, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        httponly=True, secure=settings.ENVIRONMENT == "production", samesite="lax", path="/api")
    response.headers["Cache-Control"] = "no-store"
    return True


def clear_session(response: Response, role: str) -> None:
    response.delete_cookie(COOKIE_NAMES[role], path="/api",
                           secure=settings.ENVIRONMENT == "production", httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"


def _session_token(credentials: Optional[HTTPAuthorizationCredentials], request: Request | None, role: str) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    token = request.cookies.get(COOKIE_NAMES[role]) if request else None
    if token:
        validate_session_origin(request, role)
    return token


def _check_fingerprint(token_data: TokenPayload, stored_hash: str) -> None:
    supplied = getattr(token_data, "credential_version", None)
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, credential_fingerprint(stored_hash)):
        raise HTTPException(status_code=401, detail="Session is no longer valid", headers={"WWW-Authenticate": "Bearer"})


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db), request: Request = None,
) -> AdminUser:
    token = _session_token(credentials, request, "admin")
    if not token:
        raise HTTPException(status_code=401, detail="Administrator sign-in required", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(token)
    if claims.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    user = (await db.execute(select(AdminUser).where(AdminUser.username == claims.sub))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    if not user.is_active or user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access unavailable")
    _check_fingerprint(claims, user.hashed_password)
    return user


async def get_current_student(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db), request: Request = None,
) -> StudentUser:
    token = _session_token(credentials, request, "student")
    if not token:
        raise HTTPException(status_code=401, detail="Student sign-in required", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(token)
    if claims.role != "student":
        raise HTTPException(status_code=403, detail="A student session is required")
    student = (await db.execute(select(StudentUser).where(or_(
        StudentUser.id == claims.sub, StudentUser.roll_number == normalize_roll_number(claims.sub),
    )))).scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    if not student.is_active:
        raise HTTPException(status_code=403, detail="Student access unavailable")
    _check_fingerprint(claims, student.hashed_passcode)
    return student


async def get_optional_student(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: AsyncSession = Depends(get_db), request: Request = None,
) -> Optional[StudentUser]:
    if not _session_token(credentials, request, "student"):
        return None
    try:
        return await get_current_student(credentials=credentials, db=db, request=request)
    except HTTPException:
        return None
