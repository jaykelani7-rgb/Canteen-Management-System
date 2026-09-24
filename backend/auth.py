from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import AdminUser, StudentUser
from schemas import TokenPayload

# HTTP Bearer Scheme for Swagger UI & Header Extraction
security = HTTPBearer(
    scheme_name="JWT Bearer Token",
    description="Enter JWT token with 'Bearer <token>' or just the token in Swagger UI.",
    auto_error=True,
)

optional_security = HTTPBearer(
    scheme_name="Optional JWT Bearer Token",
    description="Optional JWT token.",
    auto_error=False,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify raw password against bcrypt hash."""
    try:
        if not plain_password or not hashed_password:
            return False
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72],
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate bcrypt hash for a plaintext password."""
    # Truncate to 72 bytes per bcrypt specification
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def normalize_roll_number(roll: str) -> str:
    """Standardizes roll numbers to uppercase without whitespace (e.g., '21cs 1042' -> '21CS1042')."""
    return roll.strip().upper().replace(" ", "") if roll else ""


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT token containing payload data and expiration timestamp."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        role: str = payload.get("role")
        exp: int = payload.get("exp")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing subject identifier",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenPayload(sub=username, role=role, exp=exp)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """
    Security Dependency:
    Extracts and validates the JWT Bearer token, then queries database
    to confirm the user exists, is active, and possesses the 'admin' role.
    """
    token = credentials.credentials
    token_data = decode_access_token(token)

    # Query DB to verify active admin user
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == token_data.sub)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator account is disabled",
        )

    if user.role != "admin" or token_data.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges required to access this endpoint",
        )

    return user


async def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> StudentUser:
    """
    Security Dependency:
    Extracts and validates the JWT Bearer token for students, queries the database
    to confirm the student exists, is active, and returns the StudentUser record.
    """
    token = credentials.credentials
    token_data = decode_access_token(token)

    # Query DB to verify active student user by id or roll_number
    result = await db.execute(
        select(StudentUser).where(
            or_(
                StudentUser.id == token_data.sub,
                StudentUser.roll_number == normalize_roll_number(token_data.sub),
            )
        )
    )
    student = result.scalar_one_or_none()

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student account not found or session expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not student.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student account is deactivated",
        )

    return student


async def get_optional_student(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: AsyncSession = Depends(get_db),
) -> Optional[StudentUser]:
    """
    Optional Security Dependency:
    Returns StudentUser if a valid bearer token is provided, or None otherwise.
    """
    if not credentials or not credentials.credentials:
        return None

    try:
        token = credentials.credentials
        token_data = decode_access_token(token)
        result = await db.execute(
            select(StudentUser).where(
                or_(
                    StudentUser.id == token_data.sub,
                    StudentUser.roll_number == normalize_roll_number(token_data.sub),
                )
            )
        )
        return result.scalar_one_or_none()
    except Exception:
        return None
