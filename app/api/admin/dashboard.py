"""Admin dashboard aggregates."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import User
from schemas import AdminDashboardStatsResponse, AdvertisementResponse

router = APIRouter(prefix="/dashboard", tags=["Admin Dashboard"])


def _serialize_ad(ad, db: Session) -> AdvertisementResponse:
    submitter_name = None
    if ad.user_id:
        user = crud.get_user_by_id(db, ad.user_id)
        submitter_name = user.name if user else None
    data = AdvertisementResponse.model_validate(ad)
    data.submitter_name = submitter_name
    return data


@router.get("/stats", response_model=AdminDashboardStatsResponse)
async def dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    return crud.get_admin_dashboard_stats(db)


@router.get("/recent-advertisements", response_model=List[AdvertisementResponse])
async def recent_advertisements(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    items, _ = crud.search_advertisements_admin(db, skip=0, limit=8)
    return [_serialize_ad(ad, db) for ad in items]
