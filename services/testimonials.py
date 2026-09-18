"""Homepage testimonials: seed, queries, and public stats."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from sqlalchemy.orm import Session

from models import Advertisement, AdvertisementEnquiry, Property, PropertyEnquiry, Testimonial, User

logger = logging.getLogger(__name__)

CATEGORIES = ("buyer", "owner", "renter")
STATUSES = ("pending", "approved", "rejected")

DEFAULT_OUTCOME = {
    "buyer": "Found a home",
    "owner": "Listed a property",
    "renter": "Found a rental",
}

CURATED_SEED = [
    {
        "name": "Priya S.",
        "role": "Buyer",
        "location": "Chennai",
        "quote": (
            "Found a 2BHK in Neelankarai within a week — the locality filters "
            "and fresh listings made it easy."
        ),
        "rating": 5,
        "category": "buyer",
        "outcome": "Found a home",
        "is_verified": True,
        "is_featured": True,
        "status": "approved",
        "display_order": 1,
    },
    {
        "name": "Arjun M.",
        "role": "Owner",
        "location": "Bengaluru",
        "quote": (
            "Listed my flat and got serious enquiries the same day. "
            "The process felt clearer than the big portals."
        ),
        "rating": 5,
        "category": "owner",
        "outcome": "Listed a property",
        "is_verified": True,
        "is_featured": True,
        "status": "approved",
        "display_order": 2,
    },
    {
        "name": "Kavitha R.",
        "role": "First-time buyer",
        "location": None,
        "quote": (
            "EMI estimate on the listing page helped us budget before we even "
            "called the broker."
        ),
        "rating": 5,
        "category": "buyer",
        "outcome": "Used EMI calculator",
        "is_verified": False,
        "is_featured": True,
        "status": "approved",
        "display_order": 3,
    },
]


def normalize_category(value: str | None) -> str:
    raw = (value or "buyer").strip().lower()
    return raw if raw in CATEGORIES else "buyer"


def normalize_status(value: str | None) -> str:
    raw = (value or "approved").strip().lower()
    return raw if raw in STATUSES else "approved"


def clamp_rating(value: int | None) -> int:
    try:
        n = int(value if value is not None else 5)
    except (TypeError, ValueError):
        n = 5
    return max(1, min(5, n))


def format_count_label(n: int) -> str:
    if n >= 1000:
        return f"{n:,}+"
    return str(n)


def seed_if_empty(db: Session) -> int:
    if db.query(Testimonial).count() > 0:
        return 0
    for row in CURATED_SEED:
        db.add(Testimonial(**row))
    db.commit()
    logger.info("Seeded %s curated testimonials", len(CURATED_SEED))
    return len(CURATED_SEED)


def list_featured(db: Session, limit: int = 6) -> list[Testimonial]:
    return list_public(db, featured_only=True, limit=limit)


def list_public(
    db: Session,
    *,
    featured_only: bool = False,
    limit: int = 50,
) -> list[Testimonial]:
    query = db.query(Testimonial).filter(Testimonial.status == "approved")
    if featured_only:
        query = query.filter(Testimonial.is_featured.is_(True))
    return (
        query.order_by(
            Testimonial.is_featured.desc(),
            Testimonial.display_order.asc(),
            Testimonial.id.asc(),
        )
        .limit(limit)
        .all()
    )


def list_admin(
    db: Session,
    *,
    status: str | None = None,
    featured: bool | None = None,
) -> list[Testimonial]:
    query = db.query(Testimonial)
    if status:
        query = query.filter(Testimonial.status == normalize_status(status))
    if featured is True:
        query = query.filter(Testimonial.is_featured.is_(True))
    elif featured is False:
        query = query.filter(Testimonial.is_featured.is_(False))
    return query.order_by(Testimonial.display_order.asc(), Testimonial.id.asc()).all()


def get_by_id(db: Session, testimonial_id: int) -> Testimonial | None:
    return db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()


def next_display_order(db: Session) -> int:
    current = db.query(Testimonial.display_order).order_by(Testimonial.display_order.desc()).first()
    return (current[0] + 1) if current and current[0] is not None else 1


def public_stats(db: Session) -> dict:
    listings_live = db.query(Property).filter(Property.status == "PUBLISHED").count()
    cutoff = datetime.utcnow() - timedelta(hours=48)
    enquiries_48h = (
        db.query(PropertyEnquiry).filter(PropertyEnquiry.created_at >= cutoff).count()
    )
    verified_listings = (
        db.query(Property)
        .filter(Property.status == "PUBLISHED", Property.verification_tier == "verified")
        .count()
    )
    return {
        "listings_live": listings_live,
        "listings_live_label": format_count_label(listings_live),
        "enquiries_48h": enquiries_48h,
        "enquiries_48h_label": format_count_label(enquiries_48h),
        "verified_listings": verified_listings,
        "verified_listings_label": format_count_label(verified_listings),
    }


def apply_reorder(db: Session, ordered_ids: list[int]) -> list[Testimonial]:
    rows = db.query(Testimonial).filter(Testimonial.id.in_(ordered_ids)).all()
    by_id = {row.id: row for row in rows}
    missing = [item_id for item_id in ordered_ids if item_id not in by_id]
    if missing:
        raise ValueError(f"Unknown testimonial id(s): {missing}")
    for index, item_id in enumerate(ordered_ids, start=1):
        by_id[item_id].display_order = index
    db.commit()
    return list_admin(db)


def get_feedback_for_enquiry(
    db: Session, *, user_id: int, kind: str, enquiry_id: int
) -> Testimonial | None:
    return (
        db.query(Testimonial)
        .filter(
            Testimonial.submitted_by_user_id == user_id,
            Testimonial.source_enquiry_kind == kind,
            Testimonial.source_enquiry_id == enquiry_id,
        )
        .order_by(Testimonial.id.desc())
        .first()
    )


def submit_from_closed_enquiry(
    db: Session,
    *,
    user: User,
    kind: str,
    enquiry_id: int,
    quote: str,
    rating: int,
    outcome: str | None,
) -> Testimonial:
    kind_n = "advertisement" if kind == "advertisement" else "property"
    existing = get_feedback_for_enquiry(db, user_id=user.id, kind=kind_n, enquiry_id=enquiry_id)
    if existing and existing.status != "rejected":
        raise ValueError("Feedback already submitted for this enquiry")

    if kind_n == "property":
        enquiry = db.query(PropertyEnquiry).filter(PropertyEnquiry.id == enquiry_id).first()
        if not enquiry:
            raise LookupError("Enquiry not found")
        prop = db.query(Property).filter(Property.id == enquiry.property_id).first()
        owner_id = prop.owner_id if prop else None
        location = None
        if prop:
            location = prop.locality or prop.city
            if prop.locality and prop.city and prop.locality != prop.city:
                location = f"{prop.locality}"
        is_rent = bool(prop and "rent" in (prop.property_for or "").lower())
    else:
        enquiry = db.query(AdvertisementEnquiry).filter(AdvertisementEnquiry.id == enquiry_id).first()
        if not enquiry:
            raise LookupError("Enquiry not found")
        ad = db.query(Advertisement).filter(Advertisement.id == enquiry.advertisement_id).first()
        owner_id = enquiry.advertiser_id or (ad.user_id if ad else None)
        location = ad.location if ad else None
        is_rent = bool(ad and "rent" in (ad.property_type or ad.ad_type or "").lower())

    if enquiry.status != "CLOSED":
        raise PermissionError("Share feedback after this enquiry is closed")

    is_buyer = enquiry.buyer_id == user.id
    is_owner = owner_id == user.id
    if not is_buyer and not is_owner:
        raise PermissionError("You can only review an enquiry you were part of")

    if is_owner:
        category = "owner"
        role = "Owner"
        default_outcome = DEFAULT_OUTCOME["owner"]
    elif is_rent:
        category = "renter"
        role = "Renter"
        default_outcome = DEFAULT_OUTCOME["renter"]
    else:
        category = "buyer"
        role = "Buyer"
        default_outcome = DEFAULT_OUTCOME["buyer"]

    quote_n = quote.strip()
    outcome_n = (outcome or "").strip() or default_outcome
    if existing:
        existing.name = user.name
        existing.role = role
        existing.location = location
        existing.quote = quote_n
        existing.rating = clamp_rating(rating)
        existing.category = category
        existing.outcome = outcome_n
        existing.is_verified = True
        existing.is_featured = False
        existing.status = "pending"
        db.commit()
        db.refresh(existing)
        return existing

    row = Testimonial(
        name=user.name,
        role=role,
        location=location,
        quote=quote_n,
        rating=clamp_rating(rating),
        category=category,
        outcome=outcome_n,
        is_verified=True,
        is_featured=False,
        status="pending",
        display_order=next_display_order(db),
        submitted_by_user_id=user.id,
        source_enquiry_id=enquiry_id,
        source_enquiry_kind=kind_n,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

