"""Admin user read-only management."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import User
from schemas import AdminUserListResponse, AdminUserSummary

router = APIRouter(prefix="/users", tags=["Admin Users"])


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None),
    kyc_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    items, total = crud.list_users_admin(
        db,
        skip=skip,
        limit=limit,
        role=role,
        kyc_status=kyc_status,
        search=search,
    )
    return AdminUserListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[AdminUserSummary.model_validate(u) for u in items],
    )


@router.get("/{user_id}", response_model=AdminUserSummary)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserSummary.model_validate(user)
