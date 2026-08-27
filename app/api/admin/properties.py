"""Admin property moderation."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import crud
from auth import require_role
from database import get_db
from models import User
from schemas import (
    AdminPropertyListResponse,
    AdminPropertySummary,
    PropertyChangesRequest,
    PropertyRejectRequest,
    PropertyResponse,
    PropertyVerificationUpdateRequest,
)
from services.audit import log_admin_action
from services.property_lifecycle import approve_property, reject_property, request_property_changes
from services.property_serialize import serialize_property

router = APIRouter(prefix="/properties", tags=["Admin Properties"])


def _serialize_property(prop, db: Session) -> AdminPropertySummary:
    owner_name = None
    if prop.owner_id:
        owner = crud.get_user_by_id(db, prop.owner_id)
        owner_name = owner.name if owner else None
    return AdminPropertySummary(
        id=prop.id,
        property_for=prop.property_for,
        property_type=prop.property_type,
        bhk_type=prop.bhk_type,
        city=prop.city,
        locality=prop.locality,
        expected_price=prop.expected_price,
        status=prop.status,
        verification_tier=getattr(prop, "verification_tier", "unverified") or "unverified",
        owner_id=prop.owner_id,
        owner_name=owner_name,
        created_at=prop.created_at,
    )


@router.get("", response_model=AdminPropertyListResponse)
async def list_properties(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    owner_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    items, total = crud.search_properties_admin(
        db,
        skip=skip,
        limit=limit,
        search=search,
        city=city,
        owner_id=owner_id,
        status=status,
    )
    return AdminPropertyListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_serialize_property(item, db) for item in items],
    )


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property_detail(
    property_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    prop = crud.get_property_by_id(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize_property(db, prop, admin.id)


@router.post("/{property_id}/approve", response_model=PropertyResponse)
async def approve_property_endpoint(
    property_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    prop = crud.get_property_by_id(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    if prop.status not in ("PENDING_REVIEW", "CHANGES_REQUESTED"):
        raise HTTPException(status_code=400, detail=f"Cannot approve property in status {prop.status}")
    updated = approve_property(db, prop, admin)
    return serialize_property(db, updated, admin.id)


@router.post("/{property_id}/reject", response_model=PropertyResponse)
async def reject_property_endpoint(
    property_id: int,
    payload: PropertyRejectRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    prop = crud.get_property_by_id(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    updated = reject_property(db, prop, admin, payload.reason)
    return serialize_property(db, updated, admin.id)


@router.post("/{property_id}/request-changes", response_model=PropertyResponse)
async def request_property_changes_endpoint(
    property_id: int,
    payload: PropertyChangesRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    prop = crud.get_property_by_id(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    updated = request_property_changes(db, prop, admin, payload.notes)
    return serialize_property(db, updated, admin.id)


@router.patch("/{property_id}/verification", response_model=PropertyResponse)
async def update_property_verification(
    property_id: int,
    payload: PropertyVerificationUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    prop = crud.get_property_by_id(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    old = {
        "verification_tier": getattr(prop, "verification_tier", "unverified"),
        "survey_parcel_number": prop.survey_parcel_number,
        "encumbrance_certificate_status": prop.encumbrance_certificate_status,
    }
    updates = {"verification_tier": payload.verification_tier}
    if payload.survey_parcel_number is not None:
        updates["survey_parcel_number"] = payload.survey_parcel_number.strip() or None
    if payload.encumbrance_certificate_status is not None:
        updates["encumbrance_certificate_status"] = payload.encumbrance_certificate_status.strip() or None
    updated = crud.update_property_fields(db, prop, updates)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="property_verification_updated",
        entity_type="property",
        entity_id=updated.id,
        old_value=old,
        new_value=updates,
    )
    return serialize_property(db, updated, admin.id)
