"""In-app notifications and saved search alerts."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import crud
from auth import require_kyc_verified
from database import get_db
from models import User
from schemas import (
    NotificationListResponse,
    NotificationResponse,
    SavedSearchCreate,
    SavedSearchResponse,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    items, total = crud.get_user_notifications(
        db,
        current_user.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
    )
    unread_count = crud.get_unread_notification_count(db, current_user.id)
    return NotificationListResponse(items=items, total=total, unread_count=unread_count)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    return UnreadCountResponse(
        unread_count=crud.get_unread_notification_count(db, current_user.id)
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    note = crud.mark_notification_read(db, current_user.id, notification_id)
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    return note


@router.post("/read-all")
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    updated = crud.mark_all_notifications_read(db, current_user.id)
    return {"message": "All notifications marked as read", "updated": updated}


@router.get("/saved-searches", response_model=List[SavedSearchResponse])
async def list_saved_searches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    return crud.get_user_saved_searches(db, current_user.id)


@router.post("/saved-searches", response_model=SavedSearchResponse, status_code=201)
async def save_search(
    payload: SavedSearchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    criteria = payload.criteria.model_dump(exclude_none=True)
    if not criteria:
        raise HTTPException(status_code=400, detail="Search criteria cannot be empty")

    search = crud.upsert_saved_search(
        db,
        user_id=current_user.id,
        criteria=criteria,
        label=(payload.label or "").strip() or None,
        is_active=payload.is_active,
    )
    logger.info("Saved search #%s for user %s", search.id, current_user.email)
    return search


@router.delete("/saved-searches/{search_id}")
async def delete_saved_search(
    search_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    deleted = crud.delete_saved_search(db, current_user.id, search_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"message": "Saved search removed"}
