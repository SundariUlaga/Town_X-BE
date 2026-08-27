"""Advertisement submission, review, and homepage slider API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import crud
from auth import get_current_user, require_kyc_verified, require_role
from config import settings
from database import get_db
from models import Advertisement, User
from schemas import (
    AdvertisementApproveRequest,
    AdvertisementChangesRequest,
    AdvertisementRejectRequest,
    AdvertisementResponse,
    AdvertisementTrackRequest,
)
from services.ad_lifecycle import (
    approve_and_schedule,
    notify_ad_changes_requested,
    notify_ad_rejected,
    notify_ad_submitted,
)
from utils.cloudinary_config import upload_image_to_cloudinary, delete_multiple_images

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/advertisements", tags=["Advertisements"])


def _serialize_ad(ad: Advertisement, db: Session) -> AdvertisementResponse:
    submitter_name = None
    if ad.user_id:
        user = crud.get_user_by_id(db, ad.user_id)
        submitter_name = user.name if user else None
    data = AdvertisementResponse.model_validate(ad)
    data.submitter_name = submitter_name
    return data


@router.get("/slider", response_model=List[AdvertisementResponse])
async def homepage_slider(db: Session = Depends(get_db)):
    ads = crud.get_homepage_slider_ads(db)
    return [_serialize_ad(ad, db) for ad in ads]


@router.get("/homepage", response_model=List[AdvertisementResponse])
async def homepage_ads(db: Session = Depends(get_db)):
    """Alias for homepage slider — returns currently eligible published ads."""
    ads = crud.get_homepage_slider_ads(db)
    return [_serialize_ad(ad, db) for ad in ads]


@router.post("/{ad_id}/track")
async def track_ad_event(
    ad_id: int,
    payload: AdvertisementTrackRequest,
    db: Session = Depends(get_db),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad or ad.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Advertisement not found")
    crud.track_advertisement_event(db, ad, payload.event)
    return {"ok": True}


@router.get("/mine", response_model=List[AdvertisementResponse])
async def my_advertisements(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    ads = crud.get_user_advertisements(db, current_user.id)
    return [_serialize_ad(ad, db) for ad in ads]


@router.get("/{ad_id}", response_model=AdvertisementResponse)
async def get_advertisement(
    ad_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Advertisement not found")
    if current_user.role != "admin" and ad.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return _serialize_ad(ad, db)


@router.post("", response_model=AdvertisementResponse, status_code=201)
async def submit_advertisement(
    title: str = Form(...),
    location: str = Form(...),
    property_type: str = Form(...),
    description: str = Form(...),
    price_text: Optional[str] = Form(None),
    contact_phone: str = Form(...),
    contact_email: Optional[str] = Form(None),
    ad_type: str = Form("property"),
    property_id: Optional[int] = Form(None),
    selling_point: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Banner image is required")

    uploaded = await upload_image_to_cloudinary(file, folder=settings.CLOUDINARY_FOLDER_ADS)

    ad = crud.create_advertisement(
        db,
        {
            "user_id": current_user.id,
            "property_id": property_id,
            "ad_type": ad_type,
            "title": title.strip(),
            "location": location.strip(),
            "property_type": property_type.strip(),
            "description": description.strip(),
            "price_text": price_text.strip() if price_text else None,
            "contact_phone": contact_phone.strip(),
            "contact_email": contact_email.strip() if contact_email else None,
            "selling_point": selling_point.strip() if selling_point else None,
            "banner_url": uploaded["url"],
            "banner_public_id": uploaded["public_id"],
            "status": "PENDING_REVIEW",
            "created_by_admin": False,
        },
    )
    notify_ad_submitted(db, ad)
    return _serialize_ad(ad, db)


@router.patch("/{ad_id}", response_model=AdvertisementResponse)
async def update_my_advertisement(
    ad_id: int,
    title: str = Form(...),
    location: str = Form(...),
    property_type: str = Form(...),
    description: str = Form(...),
    price_text: Optional[str] = Form(None),
    contact_phone: str = Form(...),
    contact_email: Optional[str] = Form(None),
    selling_point: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad or ad.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Advertisement not found")
    if ad.status not in ("CHANGES_REQUESTED", "DRAFT"):
        raise HTTPException(status_code=400, detail="This advertisement cannot be edited")

    update_data = {
        "title": title.strip(),
        "location": location.strip(),
        "property_type": property_type.strip(),
        "description": description.strip(),
        "price_text": price_text.strip() if price_text else None,
        "contact_phone": contact_phone.strip(),
        "contact_email": contact_email.strip() if contact_email else None,
        "selling_point": selling_point.strip() if selling_point else None,
        "status": "PENDING_REVIEW",
        "admin_notes": None,
    }

    if file and file.filename:
        uploaded = await upload_image_to_cloudinary(file, folder=settings.CLOUDINARY_FOLDER_ADS)
        if ad.banner_public_id:
            await delete_multiple_images([ad.banner_public_id])
        update_data["banner_url"] = uploaded["url"]
        update_data["banner_public_id"] = uploaded["public_id"]

    updated = crud.update_advertisement(db, ad, update_data)
    notify_ad_submitted(db, updated)
    return _serialize_ad(updated, db)


# ---- Admin routes ----

@router.get("/admin/all", response_model=List[AdvertisementResponse])
async def admin_list_advertisements(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    ads = crud.get_all_advertisements(db, status=status)
    return [_serialize_ad(ad, db) for ad in ads]


@router.post("/admin/create", response_model=AdvertisementResponse, status_code=201)
async def admin_create_advertisement(
    title: str = Form(...),
    location: str = Form(...),
    property_type: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price_text: Optional[str] = Form(None),
    contact_phone: Optional[str] = Form(None),
    ad_type: str = Form("general"),
    display_position: int = Form(1),
    show_on_homepage: bool = Form(True),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    status: str = Form("DRAFT"),
    button_text: str = Form("View Details"),
    selling_point: Optional[str] = Form(None),
    badge_text: Optional[str] = Form("FEATURED PROJECT"),
    property_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Banner image is required")

    content = await file.read()
    uploaded = await upload_image_to_cloudinary(file, folder=settings.CLOUDINARY_FOLDER_ADS)

    parsed_start = datetime.fromisoformat(start_date) if start_date else None
    parsed_end = datetime.fromisoformat(end_date) if end_date else None
    final_status = status
    if status == "PUBLISHED" and parsed_start and parsed_start > datetime.utcnow():
        final_status = "APPROVED"

    ad = crud.create_advertisement(
        db,
        {
            "user_id": admin.id,
            "property_id": property_id,
            "ad_type": ad_type,
            "title": title.strip(),
            "location": location.strip(),
            "property_type": property_type,
            "description": description,
            "price_text": price_text,
            "contact_phone": contact_phone,
            "button_text": button_text,
            "selling_point": selling_point,
            "badge_text": badge_text or "FEATURED PROJECT",
            "banner_url": uploaded["url"],
            "banner_public_id": uploaded["public_id"],
            "status": final_status,
            "created_by_admin": True,
            "display_position": display_position,
            "show_on_homepage": show_on_homepage,
            "start_date": parsed_start,
            "end_date": parsed_end,
            "approved_by": admin.id if final_status in ("APPROVED", "PUBLISHED") else None,
            "approved_at": datetime.utcnow() if final_status in ("APPROVED", "PUBLISHED") else None,
        },
    )
    crud.refresh_advertisement_statuses(db)
    return _serialize_ad(ad, db)


@router.post("/admin/{ad_id}/approve", response_model=AdvertisementResponse)
async def admin_approve_advertisement(
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
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    updated = approve_and_schedule(
        db,
        ad,
        admin,
        display_position=payload.display_position,
        start_date=payload.start_date,
        end_date=payload.end_date,
        show_on_homepage=payload.show_on_homepage,
    )
    crud.refresh_advertisement_statuses(db)
    return _serialize_ad(updated, db)


@router.post("/admin/{ad_id}/reject", response_model=AdvertisementResponse)
async def admin_reject_advertisement(
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


@router.post("/admin/{ad_id}/request-changes", response_model=AdvertisementResponse)
async def admin_request_changes(
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


@router.patch("/admin/{ad_id}/priority", response_model=AdvertisementResponse)
async def admin_update_priority(
    ad_id: int,
    display_position: int = Form(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    ad = crud.get_advertisement_by_id(db, ad_id)
    if not ad:
        raise HTTPException(status_code=404, detail="Advertisement not found")
    updated = crud.update_advertisement(db, ad, {"display_position": display_position})
    return _serialize_ad(updated, db)
