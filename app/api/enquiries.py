"""Property and advertisement enquiries."""

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import crud
from auth import get_current_user, require_kyc_verified
from database import get_db
from models import AdvertisementEnquiry, Property, PropertyEnquiry, User
from services.activity import record_activity
from services import testimonials as testimonials_svc

router = APIRouter(prefix="/api/enquiries", tags=["Enquiries"])


class PropertyEnquiryCreate(BaseModel):
    property_id: int
    message: str = Field(..., min_length=5, max_length=2000)
    contact_method: str = Field(default="phone", pattern="^(phone|email|whatsapp)$")


class AdvertisementEnquiryCreate(BaseModel):
    advertisement_id: int
    message: str = Field(..., min_length=5, max_length=2000)
    contact_method: str = Field(default="phone", pattern="^(phone|email|whatsapp)$")


class EnquiryCloseRequest(BaseModel):
    source: Literal["property", "advertisement"] = "property"


class EnquiryResponse(BaseModel):
    id: int
    source: Literal["property", "advertisement"] = "property"
    property_id: Optional[int] = None
    advertisement_id: Optional[int] = None
    buyer_id: int
    message: str
    contact_method: str
    status: str
    created_at: datetime
    closed_at: Optional[datetime] = None
    title: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    can_close: bool = False
    can_feedback: bool = False
    has_feedback: bool = False
    feedback_status: Optional[str] = None
    feedback_category: Optional[str] = None

    class Config:
        from_attributes = True


def _buyer_fields(db: Session, buyer_id: int) -> tuple[Optional[str], Optional[str]]:
    buyer = crud.get_user_by_id(db, buyer_id)
    if not buyer:
        return None, None
    phone = buyer.phone or buyer.kyc_mobile
    return buyer.name, phone


def _property_title(prop: Optional[Property]) -> Optional[str]:
    if not prop:
        return None
    parts = [prop.bhk_type or prop.apartment_type, prop.locality or prop.city]
    title = " in ".join(p for p in parts if p)
    return title or f"Property #{prop.id}"


def _feedback_flags(
    db: Session,
    *,
    current_user: User,
    enquiry,
    kind: str,
    owner_id: Optional[int],
    is_rent: bool,
) -> dict:
    is_party = current_user.id in {enquiry.buyer_id, owner_id}
    closed = enquiry.status == "CLOSED"
    existing = testimonials_svc.get_feedback_for_enquiry(
        db, user_id=current_user.id, kind=kind, enquiry_id=enquiry.id
    )
    blocking = existing is not None and existing.status != "rejected"
    if current_user.id == owner_id:
        category = "owner"
    elif is_rent:
        category = "renter"
    else:
        category = "buyer"
    return {
        "can_close": is_party and not closed,
        "can_feedback": is_party and closed and not blocking,
        "has_feedback": existing is not None,
        "feedback_status": existing.status if existing else None,
        "feedback_category": category if is_party else None,
    }


def serialize_property_enquiry(
    db: Session, enquiry: PropertyEnquiry, current_user: User
) -> EnquiryResponse:
    prop = crud.get_property_by_id(db, enquiry.property_id)
    buyer_name, buyer_phone = _buyer_fields(db, enquiry.buyer_id)
    flags = _feedback_flags(
        db,
        current_user=current_user,
        enquiry=enquiry,
        kind="property",
        owner_id=prop.owner_id if prop else None,
        is_rent=bool(prop and "rent" in (prop.property_for or "").lower()),
    )
    return EnquiryResponse(
        id=enquiry.id,
        source="property",
        property_id=enquiry.property_id,
        buyer_id=enquiry.buyer_id,
        message=enquiry.message,
        contact_method=enquiry.contact_method,
        status=enquiry.status,
        created_at=enquiry.created_at,
        closed_at=enquiry.closed_at,
        title=_property_title(prop),
        buyer_name=buyer_name,
        buyer_phone=buyer_phone,
        **flags,
    )


def serialize_ad_enquiry(
    db: Session, enquiry: AdvertisementEnquiry, current_user: User
) -> EnquiryResponse:
    ad = crud.get_advertisement_by_id(db, enquiry.advertisement_id)
    buyer_name, buyer_phone = _buyer_fields(db, enquiry.buyer_id)
    flags = _feedback_flags(
        db,
        current_user=current_user,
        enquiry=enquiry,
        kind="advertisement",
        owner_id=enquiry.advertiser_id or (ad.user_id if ad else None),
        is_rent=bool(ad and "rent" in (ad.property_type or "").lower()),
    )
    return EnquiryResponse(
        id=enquiry.id,
        source="advertisement",
        advertisement_id=enquiry.advertisement_id,
        buyer_id=enquiry.buyer_id,
        message=enquiry.message,
        contact_method=enquiry.contact_method,
        status=enquiry.status,
        created_at=enquiry.created_at,
        closed_at=enquiry.closed_at,
        title=ad.title if ad else f"Advertisement #{enquiry.advertisement_id}",
        buyer_name=buyer_name,
        buyer_phone=buyer_phone,
        **flags,
    )


def _notify_other_party_closed(
    db: Session,
    *,
    closer: User,
    other_user_id: Optional[int],
    title: str,
    path: str,
    property_id: Optional[int] = None,
) -> None:
    if not other_user_id or other_user_id == closer.id:
        return
    crud.create_notification(
        db,
        user_id=other_user_id,
        type="enquiry_closed",
        title="Enquiry closed — share feedback?",
        body=title,
        property_id=property_id,
        payload={"path": path},
    )


@router.post("", response_model=EnquiryResponse, status_code=201)
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
            payload={"path": "/owner/dashboard?tab=enquiries", "property_id": prop.id, "enquiry_id": enquiry.id},
        )

    return serialize_property_enquiry(db, enquiry, current_user)


@router.post("/advertisements", response_model=EnquiryResponse, status_code=201)
async def create_advertisement_enquiry(
    payload: AdvertisementEnquiryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    ad = crud.get_advertisement_by_id(db, payload.advertisement_id)
    if not ad or ad.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Advertisement not found")
    if ad.user_id and ad.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot enquire on your own advertisement")

    enquiry = AdvertisementEnquiry(
        advertisement_id=ad.id,
        advertiser_id=ad.user_id,
        buyer_id=current_user.id,
        message=payload.message.strip(),
        contact_method=payload.contact_method,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)

    crud.track_advertisement_event(db, ad, "enquiry")

    record_activity(
        db,
        current_user,
        activity_type="CONTACT",
        entity_type="advertisement",
        entity_id=ad.id,
        location_text=ad.location,
        property_type=ad.property_type,
    )

    if ad.user_id:
        crud.create_notification(
            db,
            user_id=ad.user_id,
            type="advertisement_enquiry",
            title="New enquiry on your advertisement",
            body=f"Someone is interested in {ad.title}.",
            payload={
                "path": "/owner/dashboard?tab=enquiries",
                "advertisement_id": ad.id,
                "enquiry_id": enquiry.id,
            },
        )

    return serialize_ad_enquiry(db, enquiry, current_user)


@router.post("/{enquiry_id}/close", response_model=EnquiryResponse)
async def close_enquiry(
    enquiry_id: int,
    payload: EnquiryCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.source == "advertisement":
        enquiry = db.query(AdvertisementEnquiry).filter(AdvertisementEnquiry.id == enquiry_id).first()
        if not enquiry:
            raise HTTPException(status_code=404, detail="Enquiry not found")
        owner_id = enquiry.advertiser_id
        if current_user.id not in {enquiry.buyer_id, owner_id}:
            raise HTTPException(status_code=403, detail="Not allowed to close this enquiry")
        if enquiry.status != "CLOSED":
            enquiry.status = "CLOSED"
            enquiry.closed_at = datetime.utcnow()
            db.commit()
            db.refresh(enquiry)
            other_id = owner_id if current_user.id == enquiry.buyer_id else enquiry.buyer_id
            other_path = "/owner/dashboard?tab=enquiries" if other_id == owner_id else "/enquiries"
            _notify_other_party_closed(
                db,
                closer=current_user,
                other_user_id=other_id,
                title="This conversation was marked closed. A short note about Town-X helps other buyers.",
                path=other_path,
            )
        return serialize_ad_enquiry(db, enquiry, current_user)

    enquiry = db.query(PropertyEnquiry).filter(PropertyEnquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    prop = crud.get_property_by_id(db, enquiry.property_id)
    owner_id = prop.owner_id if prop else None
    if current_user.id not in {enquiry.buyer_id, owner_id}:
        raise HTTPException(status_code=403, detail="Not allowed to close this enquiry")
    if enquiry.status != "CLOSED":
        enquiry.status = "CLOSED"
        enquiry.closed_at = datetime.utcnow()
        db.commit()
        db.refresh(enquiry)
        other_id = owner_id if current_user.id == enquiry.buyer_id else enquiry.buyer_id
        other_path = "/owner/dashboard?tab=enquiries" if other_id == owner_id else "/enquiries"
        _notify_other_party_closed(
            db,
            closer=current_user,
            other_user_id=other_id,
            title="This conversation was marked closed. A short note about Town-X helps other buyers.",
            path=other_path,
            property_id=enquiry.property_id,
        )
    return serialize_property_enquiry(db, enquiry, current_user)


@router.get("/mine", response_model=List[EnquiryResponse])
async def my_enquiries_as_buyer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_rows = (
        db.query(PropertyEnquiry)
        .filter(PropertyEnquiry.buyer_id == current_user.id)
        .all()
    )
    ad_rows = (
        db.query(AdvertisementEnquiry)
        .filter(AdvertisementEnquiry.buyer_id == current_user.id)
        .all()
    )
    combined = [serialize_property_enquiry(db, row, current_user) for row in property_rows]
    combined.extend(serialize_ad_enquiry(db, row, current_user) for row in ad_rows)
    combined.sort(key=lambda item: item.created_at, reverse=True)
    return combined


@router.get("/received", response_model=List[EnquiryResponse])
async def received_enquiries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_rows = (
        db.query(PropertyEnquiry)
        .join(Property, PropertyEnquiry.property_id == Property.id)
        .filter(Property.owner_id == current_user.id)
        .all()
    )
    ad_rows = (
        db.query(AdvertisementEnquiry)
        .filter(AdvertisementEnquiry.advertiser_id == current_user.id)
        .all()
    )
    combined = [serialize_property_enquiry(db, row, current_user) for row in property_rows]
    combined.extend(serialize_ad_enquiry(db, row, current_user) for row in ad_rows)
    combined.sort(key=lambda item: item.created_at, reverse=True)
    return combined
