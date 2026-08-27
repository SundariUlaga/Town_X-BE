"""User activity tracking API."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_kyc_verified
from database import get_db
from models import User
from services.activity import record_activity, record_search

router = APIRouter(prefix="/api/activity", tags=["Activity"])


class ActivityTrackRequest(BaseModel):
    activity_type: str = Field(..., min_length=2, max_length=40)
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    location_text: Optional[str] = None
    property_type: Optional[str] = None
    transaction_type: Optional[str] = None
    search_query: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("")
async def track_activity(
    payload: ActivityTrackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    activity = record_activity(
        db,
        current_user,
        activity_type=payload.activity_type,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        location_text=payload.location_text,
        property_type=payload.property_type,
        transaction_type=payload.transaction_type,
        search_query=payload.search_query,
        metadata=payload.metadata,
    )
    return {"ok": True, "recorded": activity is not None}


@router.post("/search")
async def track_search(
    search_query: Optional[str] = None,
    location_text: Optional[str] = None,
    property_type: Optional[str] = None,
    transaction_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    record_search(
        db,
        current_user,
        search_query=search_query,
        location_text=location_text,
        property_type=property_type,
        transaction_type=transaction_type,
    )
    return {"ok": True}
