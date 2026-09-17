"""Admin advertisement management."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import Advertisement, User
from schemas import (
    AdminAdvertisementListResponse,
    AdvertisementApproveRequest,
    AdvertisementChangesRequest,
    AdvertisementRejectRequest,
    AdvertisementResponse,
)
from services.ad_lifecycle import (
    approve_and_schedule,
    notify_ad_changes_requested,
    notify_ad_rejected,
)

router = APIRouter(prefix="/advertisements", tags=["Admin Advertisements"])


def _serialize_ad(ad: Advertisement, db: Session) -> AdvertisementResponse:
    submitter_name = None
    if ad.user_id:
        user = crud.get_user_by_id(db, ad.user_id)
        submitter_name = user.name if user else None
    data = AdvertisementResponse.model_validate(ad)
    data.submitter_name = submitter_name
    return data


@router.get("", response_model=AdminAdvertisementListResponse)
async def list_advertisements(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    property_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    items, total = crud.search_advertisements_admin(
        db,
        skip=skip,
        limit=limit,
        status=status,
        search=search,
        user_id=user_id,
        property_id=property_id,
        date_from=date_from,
        date_to=date_to,
    )
    return AdminAdvertisementListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_serialize_ad(ad, db) for ad in items],
    )


@router.get("/{ad_id}", response_model=AdvertisementResponse)
async def get_advertisement(
    ad_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Advertisement not found")
    return _serialize_ad(ad, db)


@router.post("/{ad_id}/approve", response_model=AdvertisementResponse)
async def approve_advertisement(
    ad_id: int,
    payload: AdvertisementApproveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Advertisement not found")
    if ad.status not in ("PENDING_REVIEW", "CHANGES_REQUESTED", "APPROVED"):
        raise HTTPException(status_code=400, detail=f"Cannot approve ad in status {ad.status}")
    # Compare as naive UTC so ISO-Z payloads from the admin UI do not 500
    from services.ad_lifecycle import _to_naive_utc

    start = _to_naive_utc(payload.start_date)
    end = _to_naive_utc(payload.end_date)
    if end < start:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    updated = approve_and_schedule(
        db,
        ad,
        admin,
        display_position=payload.display_position,
        start_date=start,
        end_date=end,
        show_on_homepage=payload.show_on_homepage,
    )
    crud.refresh_advertisement_statuses(db)
    return _serialize_ad(updated, db)


@router.post("/{ad_id}/reject", response_model=AdvertisementResponse)
async def reject_advertisement(
    ad_id: int,
    payload: AdvertisementRejectRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Advertisement not found")

    updated = crud.update_advertisement(
        db,
        ad,
        {"status": "REJECTED", "admin_notes": payload.reason.strip()},
    )
    notify_ad_rejected(db, updated, payload.reason.strip())
    return _serialize_ad(updated, db)


@router.post("/{ad_id}/request-changes", response_model=AdvertisementResponse)
async def request_changes(
    ad_id: int,
    payload: AdvertisementChangesRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Advertisement not found")

    updated = crud.update_advertisement(
        db,
        ad,
        {"status": "CHANGES_REQUESTED", "admin_notes": payload.notes.strip()},
    )
    notify_ad_changes_requested(db, updated, payload.notes.strip())
    return _serialize_ad(updated, db)
