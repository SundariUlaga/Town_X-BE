"""Admin in-app notifications for review-queue events."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import User
from schemas import NotificationListResponse, UnreadCountResponse

router = APIRouter(prefix="/notifications", tags=["Admin Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_admin_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    items, total = crud.get_user_notifications(
        db,
        admin.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
    )
    unread_count = crud.get_unread_notification_count(db, admin.id)
    return NotificationListResponse(items=items, total=total, unread_count=unread_count)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def admin_unread_count(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    return UnreadCountResponse(unread_count=crud.get_unread_notification_count(db, admin.id))


@router.post("/read-all")
async def mark_all_admin_notifications_read(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    updated = crud.mark_all_notifications_read(db, admin.id)
    return {"message": "All notifications marked as read", "updated": updated}
