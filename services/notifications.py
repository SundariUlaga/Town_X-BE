"""In-app notification dispatch for property and search events."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

import crud
from models import Property, User

logger = logging.getLogger(__name__)


def _format_price(amount: float) -> str:
    return f"₹{amount:,.0f}"


def _property_summary(property_row: Property) -> str:
    parts = [property_row.bhk_type, property_row.apartment_type]
    if property_row.apartment_name:
        parts.append(f"in {property_row.apartment_name}")
    parts.append(f"— {property_row.locality}, {property_row.city}")
    return " ".join(parts)


def dispatch_property_created_notifications(db: Session, property_row: Property) -> int:
    """Create notifications when a new listing is published."""
    created = 0
    summary = _property_summary(property_row)
    price_text = _format_price(property_row.expected_price)

    if property_row.owner_id:
        if not crud.notification_exists(
            db,
            user_id=property_row.owner_id,
            type="listing_live",
            property_id=property_row.id,
        ):
            crud.create_notification(
                db,
                user_id=property_row.owner_id,
                type="listing_live",
                title="Your listing is live",
                body=f"{summary} is now visible to buyers at {price_text}.",
                property_id=property_row.id,
                payload={"path": f"/property/{property_row.id}"},
            )
            created += 1

    saved_searches = crud.get_active_saved_searches(db)
    for saved in saved_searches:
        if property_row.owner_id and saved.user_id == property_row.owner_id:
            continue
        if not crud.property_matches_criteria(property_row, saved.criteria or {}):
            continue
        if crud.notification_exists(
            db,
            user_id=saved.user_id,
            type="search_match",
            property_id=property_row.id,
            saved_search_id=saved.id,
        ):
            continue

        crud.create_notification(
            db,
            user_id=saved.user_id,
            type="search_match",
            title="New match for your search",
            body=f"{summary} at {price_text} matches “{saved.label}”.",
            property_id=property_row.id,
            saved_search_id=saved.id,
            payload={
                "path": f"/property/{property_row.id}",
                "saved_search_label": saved.label,
            },
        )
        created += 1

    if created:
        logger.info(
            "Created %s notification(s) for property #%s",
            created,
            property_row.id,
        )
    return created


def dispatch_property_published_notifications(db: Session, property_row: Property) -> int:
    """Notify owner and saved-search subscribers when a listing is published."""
    return dispatch_property_created_notifications(db, property_row)
