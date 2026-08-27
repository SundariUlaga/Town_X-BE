"""Property moderation lifecycle and notifications."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

import crud
from models import Property, User
from services.audit import log_admin_action
from services.notifications import dispatch_property_published_notifications


def _notify_property(db: Session, user_id: int, type: str, title: str, body: str, property_id: int) -> None:
    crud.create_notification(
        db,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        property_id=property_id,
        payload={"path": f"/property/{property_id}", "property_id": property_id},
    )


def approve_property(db: Session, prop: Property, admin: User) -> Property:
    now = datetime.utcnow()
    old = {"status": prop.status}
    updated = crud.update_property_fields(
        db,
        prop,
        {"status": "PUBLISHED", "published_at": now, "admin_notes": None},
    )
    if updated.owner_id:
        _notify_property(
            db,
            updated.owner_id,
            "property_approved",
            "Property approved",
            f"Your listing in {updated.locality}, {updated.city} is now live.",
            updated.id,
        )
        dispatch_property_published_notifications(db, updated)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="property_approved",
        entity_type="property",
        entity_id=updated.id,
        old_value=old,
        new_value={"status": updated.status},
    )
    return updated


def reject_property(db: Session, prop: Property, admin: User, reason: str) -> Property:
    old = {"status": prop.status}
    reason = reason.strip()
    updated = crud.update_property_fields(
        db,
        prop,
        {"status": "REJECTED", "admin_notes": reason},
    )
    crud.create_property_review_note(
        db,
        property_id=updated.id,
        note_type="reject",
        note=reason,
        admin_user_id=admin.id,
    )
    if updated.owner_id:
        _notify_property(
            db,
            updated.owner_id,
            "property_rejected",
            "Property rejected",
            f"Your listing was not approved. {reason}",
            updated.id,
        )
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="property_rejected",
        entity_type="property",
        entity_id=updated.id,
        old_value=old,
        new_value={"status": updated.status, "reason": reason},
    )
    return updated


def request_property_changes(db: Session, prop: Property, admin: User, notes: str) -> Property:
    old = {"status": prop.status}
    notes = notes.strip()
    updated = crud.update_property_fields(
        db,
        prop,
        {"status": "CHANGES_REQUESTED", "admin_notes": notes},
    )
    crud.create_property_review_note(
        db,
        property_id=updated.id,
        note_type="changes_requested",
        note=notes,
        admin_user_id=admin.id,
    )
    if updated.owner_id:
        _notify_property(
            db,
            updated.owner_id,
            "property_changes_requested",
            "Changes requested",
            f"Please update your listing: {notes}",
            updated.id,
        )
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="property_changes_requested",
        entity_type="property",
        entity_id=updated.id,
        old_value=old,
        new_value={"status": updated.status, "notes": notes},
    )
    return updated
