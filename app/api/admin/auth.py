"""Admin authentication — reuses existing User table and JWT."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

import crud
from auth import get_current_user, issue_auth_session, verify_password
from database import get_db
from models import User
from schemas import TokenResponse, UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


@router.post("/login", response_model=TokenResponse)
async def admin_login(payload: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return TokenResponse(**issue_auth_session(response, user))


@router.get("/me", response_model=UserResponse)
async def admin_me(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
