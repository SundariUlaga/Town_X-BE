"""Admin authentication — reuses existing User table and JWT."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import crud
from auth import create_access_token, get_current_user, verify_password
from database import get_db
from models import User
from schemas import TokenResponse, UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


@router.post("/login", response_model=TokenResponse)
async def admin_login(payload: UserLogin, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    token = create_access_token(user)
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserResponse)
async def admin_me(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
