"""
Password hashing + JWT issuance/validation + HttpOnly session cookies.

Session model:
- Login/OTP issues a short-lived **access** JWT and a longer-lived **refresh** JWT.
- Access token: ``Authorization: Bearer`` and HttpOnly ``townx_session`` cookie.
- Refresh token: HttpOnly ``townx_refresh`` cookie (body fallback for admin / tools).
- POST /api/auth/refresh rotates both tokens while the refresh token is valid.
- When refresh expires, clients must log in again.
"""
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User

security = HTTPBearer(auto_error=False)

SESSION_COOKIE_NAME = "townx_session"
REFRESH_COOKIE_NAME = "townx_refresh"

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

SESSION_EXPIRED_DETAIL = "Session expired, please log in again"
ACCESS_EXPIRED_DETAIL = "Access token expired"
INVALID_TOKEN_DETAIL = "Invalid authentication token"


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def access_token_ttl_seconds() -> int:
    return int(settings.JWT_ACCESS_EXPIRY_MINUTES * 60)


def refresh_token_ttl_seconds() -> int:
    return int(settings.JWT_EXPIRY_HOURS * 3600)


def _encode_token(user: User, token_type: str, ttl: timedelta) -> str:
    expire = datetime.utcnow() + ttl
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "typ": token_type,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    return _encode_token(
        user,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.JWT_ACCESS_EXPIRY_MINUTES),
    )


def create_refresh_token(user: User) -> str:
    return _encode_token(
        user,
        REFRESH_TOKEN_TYPE,
        timedelta(hours=settings.JWT_EXPIRY_HOURS),
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        if expected_type == REFRESH_TOKEN_TYPE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=SESSION_EXPIRED_DETAIL,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ACCESS_EXPIRED_DETAIL,
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
        )

    # Legacy tokens issued before typ was added are treated as access tokens.
    token_typ = payload.get("typ", ACCESS_TOKEN_TYPE)
    if token_typ != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
        )
    return payload


def decode_access_token(token: str) -> dict:
    return decode_token(token, ACCESS_TOKEN_TYPE)


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": bool(settings.SESSION_COOKIE_SECURE),
        "path": "/",
    }


def attach_session_cookie(response: Response, token: str) -> None:
    """Short-lived access cookie (survives tab close until access TTL)."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=access_token_ttl_seconds(),
        **_cookie_kwargs(),
    )


def attach_refresh_cookie(response: Response, token: str) -> None:
    """Longer-lived refresh cookie — this is the real session lifetime."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=refresh_token_ttl_seconds(),
        **_cookie_kwargs(),
    )


def clear_session_cookie(response: Response) -> None:
    opts = _cookie_kwargs()
    response.delete_cookie(key=SESSION_COOKIE_NAME, path=opts["path"], samesite=opts["samesite"], secure=opts["secure"])
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=opts["path"], samesite=opts["samesite"], secure=opts["secure"])


def clear_refresh_cookie(response: Response) -> None:
    clear_session_cookie(response)


def extract_access_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """Prefer Bearer header, then HttpOnly session cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie or None


def extract_refresh_token(request: Request, body_token: Optional[str] = None) -> Optional[str]:
    cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie:
        return cookie
    if body_token and body_token.strip():
        return body_token.strip()
    return None


def load_user_from_payload(db: Session, payload: dict) -> User:
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def issue_auth_session(response: Response, user: User) -> dict:
    """Mint access + refresh tokens, set cookies, return response fields."""
    access = create_access_token(user)
    refresh = create_refresh_token(user)
    attach_session_cookie(response, access)
    attach_refresh_cookie(response, refresh)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": access_token_ttl_seconds(),
        "user": user,
    }


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = extract_access_token(request, credentials)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(token)
    return load_user_from_payload(db, payload)


def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user, but returns None instead of 401 when no/invalid
    token is present — used on routes that stay usable without an account."""
    token = extract_access_token(request, credentials)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


def require_role(*allowed_roles: str):
    """Dependency factory: require_role('admin') restricts a route to admins."""

    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this action")
        return user

    return _check


def require_kyc_verified(user: User = Depends(get_current_user)) -> User:
    """Require a logged-in user who has completed eKYC verification."""
    if user.kyc_status != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete identity verification to access this section",
        )
    return user
