"""Admin audit log read API."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import AuditLog, User

router = APIRouter(prefix="/audit-logs", tags=["Admin Audit Logs"])


class AuditLogResponse(BaseModel):
    id: int
    admin_user_id: int
    admin_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: int
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AuditLogResponse]


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    admin_user_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type.strip().lower())
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if admin_user_id is not None:
        query = query.filter(AuditLog.admin_user_id == admin_user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at <= date_to)

    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    items: list[AuditLogResponse] = []
    for row in rows:
        admin = crud.get_user_by_id(db, row.admin_user_id)
        items.append(
            AuditLogResponse(
                id=row.id,
                admin_user_id=row.admin_user_id,
                admin_name=admin.name if admin else None,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                old_value=row.old_value,
                new_value=row.new_value,
                created_at=row.created_at,
            )
        )
    return AuditLogListResponse(total=total, skip=skip, limit=limit, items=items)
