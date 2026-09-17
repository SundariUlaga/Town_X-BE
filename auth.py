"""
Password hashing + JWT issuance/validation + HttpOnly session cookie.

Session model (prototype):
- Login/OTP issues a JWT and sets HttpOnly cookie ``townx_session``.
- Clients may also send ``Authorization: Bearer`` (legacy / same-tab cache).
- Close tab → cookie remains until max-age or logout.
- No refresh rotation / revocation list yet.
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


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")


def attach_session_cookie(response: Response, token: str) -> None:
    """Persist session for later visits (survives tab close)."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=bool(settings.SESSION_COOKIE_SECURE),
        max_age=int(settings.JWT_EXPIRY_HOURS * 3600),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=bool(settings.SESSION_COOKIE_SECURE),
    )


def extract_access_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """Prefer Bearer header, then HttpOnly session cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie or None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = extract_access_token(request, credentials)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(token)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


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
