"""User property reports."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import crud
from auth import require_kyc_verified
from database import get_db
from models import PropertyReport, User

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class PropertyReportCreate(BaseModel):
    property_id: int
    reason: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)


class PropertyReportResponse(BaseModel):
    id: int
    property_id: int
    reported_by: int
    reason: str
    description: Optional[str] = None
    status: str
    created_at: str

    class Config:
        from_attributes = True


@router.post("/properties", response_model=PropertyReportResponse, status_code=201)
async def report_property(
    payload: PropertyReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    prop = crud.get_property_by_id(db, payload.property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    report = PropertyReport(
        property_id=payload.property_id,
        reported_by=current_user.id,
        reason=payload.reason.strip(),
        description=(payload.description or "").strip() or None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
