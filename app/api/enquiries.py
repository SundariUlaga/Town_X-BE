"""Property enquiries."""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import crud
from auth import get_current_user, require_kyc_verified
from database import get_db
from models import Property, PropertyEnquiry, User
from services.activity import record_activity

router = APIRouter(prefix="/api/enquiries", tags=["Enquiries"])


class PropertyEnquiryCreate(BaseModel):
    property_id: int
    message: str = Field(..., min_length=5, max_length=2000)
    contact_method: str = Field(default="phone", pattern="^(phone|email|whatsapp)$")


class PropertyEnquiryResponse(BaseModel):
    id: int
    property_id: int
    buyer_id: int
    message: str
    contact_method: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=PropertyEnquiryResponse, status_code=201)
async def create_enquiry(
    payload: PropertyEnquiryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    prop = crud.get_property_by_id(db, payload.property_id)
    if not prop or prop.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Property not found")
    if prop.owner_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot enquire on your own listing")

    enquiry = PropertyEnquiry(
        property_id=payload.property_id,
        buyer_id=current_user.id,
        message=payload.message.strip(),
        contact_method=payload.contact_method,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)

    record_activity(
        db,
        current_user,
        activity_type="CONTACT",
        entity_type="property",
        entity_id=prop.id,
        location_text=f"{prop.locality}, {prop.city}",
        property_type=prop.property_type,
        transaction_type=prop.property_for,
    )

    if prop.owner_id:
        crud.create_notification(
            db,
            user_id=prop.owner_id,
            type="property_enquiry",
            title="New enquiry on your listing",
            body=f"Someone is interested in your property in {prop.locality}, {prop.city}.",
            property_id=prop.id,
            payload={"path": f"/owner/dashboard", "property_id": prop.id, "enquiry_id": enquiry.id},
        )

    return enquiry


@router.get("/mine", response_model=List[PropertyEnquiryResponse])
async def my_enquiries_as_buyer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(PropertyEnquiry)
        .filter(PropertyEnquiry.buyer_id == current_user.id)
        .order_by(PropertyEnquiry.created_at.desc())
        .all()
    )
    return rows


@router.get("/received", response_model=List[PropertyEnquiryResponse])
async def received_enquiries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(PropertyEnquiry)
        .join(Property, PropertyEnquiry.property_id == Property.id)
        .filter(Property.owner_id == current_user.id)
        .order_by(PropertyEnquiry.created_at.desc())
        .all()
    )
    return rows
