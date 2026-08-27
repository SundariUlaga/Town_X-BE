"""Account profile, settings, and support Q&A — verified users only."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
from auth import hash_password, require_kyc_verified, verify_password
from database import get_db
from models import User
from schemas import (
    ChangePasswordRequest,
    ProfileUpdate,
    SupportQuestionCreate,
    SupportQuestionResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["Account"])


@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user: User = Depends(require_kyc_verified)):
    """Return the authenticated user's profile details."""
    return current_user


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    """Update editable profile fields (name)."""
    user = crud.update_user_profile(db, current_user, name=payload.name.strip())
    logger.info("Profile updated for user %s", user.email)
    return user


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    """Change the user's password after verifying the current one."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    logger.info("Password changed for user %s", current_user.email)
    return {"message": "Password updated successfully"}


@router.get("/questions", response_model=List[SupportQuestionResponse])
async def list_my_questions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    """List support questions submitted by the current user."""
    return crud.get_user_support_questions(db, current_user.id)


@router.post("/questions", response_model=SupportQuestionResponse, status_code=201)
async def submit_question(
    payload: SupportQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    """Submit a new support question."""
    question = crud.create_support_question(
        db,
        user_id=current_user.id,
        subject=payload.subject.strip(),
        message=payload.message.strip(),
    )
    logger.info("Support question #%s submitted by user %s", question.id, current_user.email)
    return question
