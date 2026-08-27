"""Admin property reports management."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import PropertyReport, User
from services.audit import log_admin_action

router = APIRouter(prefix="/reports", tags=["Admin Reports"])


class AdminReportResponse(BaseModel):
    id: int
    property_id: int
    reported_by: int
    reason: str
    description: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class ReportActionRequest(BaseModel):
    admin_notes: Optional[str] = Field(None, max_length=2000)


@router.get("", response_model=List[AdminReportResponse])
async def list_reports(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    query = db.query(PropertyReport)
    if status:
        query = query.filter(PropertyReport.status == status.upper())
    return query.order_by(PropertyReport.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/{report_id}/resolve")
async def resolve_report(
    report_id: int,
    payload: ReportActionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    report = db.query(PropertyReport).filter(PropertyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    old = {"status": report.status}
    report.status = "RESOLVED"
    report.admin_notes = payload.admin_notes
    db.commit()
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="report_resolved",
        entity_type="property_report",
        entity_id=report.id,
        old_value=old,
        new_value={"status": report.status},
    )
    return {"ok": True}


@router.post("/{report_id}/dismiss")
async def dismiss_report(
    report_id: int,
    payload: ReportActionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    report = db.query(PropertyReport).filter(PropertyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    old = {"status": report.status}
    report.status = "DISMISSED"
    report.admin_notes = payload.admin_notes
    db.commit()
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="report_dismissed",
        entity_type="property_report",
        entity_id=report.id,
        old_value=old,
        new_value={"status": report.status},
    )
    return {"ok": True}
