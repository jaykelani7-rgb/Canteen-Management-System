"""Student authentication is separate from ordering and payment operations."""
import secrets
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (clear_session, create_access_token, credential_fingerprint, get_current_student,
                  get_password_hash, issue_session, normalize_roll_number, validate_session_origin, verify_password)
from database import get_db
from models import StudentUser
from rate_limit import enforce_rate_limit
from config import settings
from recovery_service import GENERIC_REQUEST_MESSAGE, INVALID_CODE_MESSAGE, request_recovery, reset_passcode
from schemas import (AuthResponse, ForgotPasscodeRequest, ResetPasscodeRequest,
                     StudentLoginRequest, StudentProfileResponse, StudentRegisterRequest)

student_auth_router = APIRouter(tags=["Student Authentication"])
_DUMMY_HASH = get_password_hash(secrets.token_urlsafe(32))


def _response(student: StudentUser, request: Request, response: Response, message: str) -> AuthResponse:
    token = create_access_token({"sub": student.id, "role": "student",
                                 "credential_version": credential_fingerprint(student.hashed_passcode)})
    cookie_mode = issue_session(response, request, token, "student")
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(success=True, message=message, user=StudentProfileResponse(**student.to_profile_dict()),
                        token=None if cookie_mode else token)


@student_auth_router.post("/auth/register", response_model=AuthResponse, status_code=201)
@student_auth_router.post("/student/register", response_model=AuthResponse, status_code=201, include_in_schema=False)
async def register_student(payload: StudentRegisterRequest, request: Request, response: Response,
                           db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(request, "register", limit=5, window=300)
    if request.headers.get("x-session-mode", "").lower() == "cookie":
        from config import settings
        if not settings.SESSION_COOKIE_MODE_ENABLED:
            raise HTTPException(status_code=503, detail="Cookie sessions are unavailable")
        validate_session_origin(request, "student")
    roll = normalize_roll_number(payload.rollNumber)
    name = payload.name.strip()
    if not name or not roll or len(roll) < 4:
        raise HTTPException(status_code=422, detail="Valid student name and roll number are required")
    email = (payload.email or (roll.lower() + "@campus.edu")).strip().lower()
    exists = (await db.execute(select(StudentUser.id).where(or_(StudentUser.roll_number == roll, StudentUser.email == email)).limit(1))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="An account already exists for those details")
    try:
        password_hash = get_password_hash(payload.passcode)
    except ValueError:
        raise HTTPException(status_code=422, detail="Passcode length is unsupported")
    student = StudentUser(id="usr_" + secrets.token_hex(12), roll_number=roll, name=name,
                          branch=(payload.branch or "").strip(), email=email, phone=(payload.phone or "").strip(),
                          hashed_passcode=password_hash, wallet_balance=0,
                          upi_id="", dietary_preference="all", favorites=[], total_orders=0,
                          total_spent=0, saved_minutes=0, is_active=True)
    db.add(student)
    try:
        await db.commit()
        await db.refresh(student)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An account already exists for those details")
    return _response(student, request, response, "Account created successfully")


@student_auth_router.post("/auth/login", response_model=AuthResponse)
@student_auth_router.post("/student/login", response_model=AuthResponse, include_in_schema=False)
async def login_student(payload: StudentLoginRequest, request: Request, response: Response,
                        db: AsyncSession = Depends(get_db)):
    roll = normalize_roll_number(payload.rollNumber)
    await enforce_rate_limit(request, "login", roll)
    if request.headers.get("x-session-mode", "").lower() == "cookie":
        from config import settings
        if not settings.SESSION_COOKIE_MODE_ENABLED:
            raise HTTPException(status_code=503, detail="Cookie sessions are unavailable")
        validate_session_origin(request, "student")
    student = (await db.execute(select(StudentUser).where(StudentUser.roll_number == roll))).scalar_one_or_none()
    valid = verify_password(payload.passcode, student.hashed_passcode if student else _DUMMY_HASH)
    if not student or not valid or not student.is_active:
        raise HTTPException(status_code=401, detail="Invalid roll number or passcode")
    return _response(student, request, response, "Signed in successfully")


@student_auth_router.get("/auth/me")
@student_auth_router.get("/student/profile", include_in_schema=False)
async def get_student_me(response: Response, student: StudentUser = Depends(get_current_student)) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {"success": True, "user": student.to_profile_dict()}


@student_auth_router.post("/auth/logout")
async def logout_student(request: Request, response: Response):
    if request.cookies.get("canteen_student"):
        validate_session_origin(request, "student")
    clear_session(response, "student")
    return {"success": True, "message": "Signed out"}


@student_auth_router.post("/auth/forgot-passcode")
async def forgot_passcode(payload: ForgotPasscodeRequest, request: Request, response: Response,
                          background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    roll = normalize_roll_number(payload.rollNumber)
    await enforce_rate_limit(request, "recovery-request", roll,
                             limit=settings.RECOVERY_REQUEST_LIMIT, window=settings.RECOVERY_RATE_WINDOW_SECONDS)
    if request.headers.get("x-session-mode", "").lower() == "cookie":
        validate_session_origin(request, "student")
    await request_recovery(db, roll, background)
    response.headers["Cache-Control"] = "no-store"
    return {"success": True, "message": GENERIC_REQUEST_MESSAGE}


@student_auth_router.post("/auth/reset-passcode")
async def reset_passcode_with_otp(payload: ResetPasscodeRequest, request: Request, response: Response,
                                  db: AsyncSession = Depends(get_db)):
    roll = normalize_roll_number(payload.rollNumber)
    await enforce_rate_limit(request, "recovery-reset", roll,
                             limit=settings.RECOVERY_RESET_LIMIT, window=settings.RECOVERY_RATE_WINDOW_SECONDS)
    if request.headers.get("x-session-mode", "").lower() == "cookie":
        validate_session_origin(request, "student")
    if not await reset_passcode(db, roll, payload.otp, payload.newPasscode):
        raise HTTPException(400, INVALID_CODE_MESSAGE)
    clear_session(response, "student")
    return {"success": True, "message": "Passcode updated. Sign in again."}


@student_auth_router.get("/auth/demo-users", include_in_schema=False)
async def get_demo_users():
    raise HTTPException(status_code=404, detail="Not found")
