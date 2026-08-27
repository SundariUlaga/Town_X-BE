"""User activity tracking for personalization."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import crud
from models import Property, User, UserActivity

VIEW_COOLDOWN_MINUTES = 30

ACTIVITY_WEIGHTS = {
    "SEARCH": 1,
    "VIEW_PROPERTY": 2,
    "FAVOURITE": 5,
    "UNFAVOURITE": -2,
    "CONTACT": 8,
    "SAVE_SEARCH": 7,
}


def record_activity(
    db: Session,
    user: User,
    *,
    activity_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    location_text: str | None = None,
    property_type: str | None = None,
    transaction_type: str | None = None,
    search_query: str | None = None,
    metadata: dict | None = None,
) -> UserActivity | None:
    if activity_type == "VIEW_PROPERTY" and entity_id is not None:
        cutoff = datetime.utcnow() - timedelta(minutes=VIEW_COOLDOWN_MINUTES)
        recent = (
            db.query(UserActivity)
            .filter(
                UserActivity.user_id == user.id,
                UserActivity.activity_type == "VIEW_PROPERTY",
                UserActivity.entity_id == entity_id,
                UserActivity.created_at >= cutoff,
            )
            .first()
        )
        if recent:
            return None

    activity = UserActivity(
        user_id=user.id,
        activity_type=activity_type,
        entity_type=entity_type,
        entity_id=entity_id,
        location_text=location_text,
        property_type=property_type,
        transaction_type=transaction_type,
        search_query=search_query,
        metadata_json=metadata,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def record_property_view(db: Session, user: User, prop: Property) -> UserActivity | None:
    return record_activity(
        db,
        user,
        activity_type="VIEW_PROPERTY",
        entity_type="property",
        entity_id=prop.id,
        location_text=f"{prop.locality}, {prop.city}",
        property_type=prop.property_type,
        transaction_type=prop.property_for,
    )


def record_search(
    db: Session,
    user: User,
    *,
    search_query: str | None = None,
    location_text: str | None = None,
    property_type: str | None = None,
    transaction_type: str | None = None,
    metadata: dict | None = None,
) -> UserActivity:
    return record_activity(
        db,
        user,
        activity_type="SEARCH",
        entity_type="search",
        search_query=search_query,
        location_text=location_text,
        property_type=property_type,
        transaction_type=transaction_type,
        metadata=metadata,
    ) or UserActivity()
