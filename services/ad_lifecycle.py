"""Advertisement status transitions and user notifications."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

import crud
from models import Advertisement, User

logger = logging.getLogger(__name__)


def _to_naive_utc(dt: datetime) -> datetime:
    """Normalize API datetimes (often offset-aware) for comparison with utcnow()."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _notify(db: Session, user_id: int, type: str, title: str, body: str, payload: dict | None = None) -> None:
    if crud.notification_exists(db, user_id=user_id, type=type, property_id=None):
        return
    crud.create_notification(
        db,
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        payload=payload or {"path": "/advertise/my"},
    )


def notify_ad_submitted(db: Session, ad: Advertisement) -> None:
    if not ad.user_id:
        return
    _notify(
        db,
        ad.user_id,
        "ad_submitted",
        "Advertisement submitted",
        f"“{ad.title}” is pending admin review.",
        {"path": "/advertise/my", "ad_id": ad.id},
    )


def notify_ad_rejected(db: Session, ad: Advertisement, reason: str) -> None:
    if not ad.user_id:
        return
    _notify(
        db,
        ad.user_id,
        "ad_rejected",
        "Advertisement rejected",
        f"“{ad.title}” was not approved. {reason}",
        {"path": "/advertise/my", "ad_id": ad.id},
    )


def notify_ad_changes_requested(db: Session, ad: Advertisement, notes: str) -> None:
    if not ad.user_id:
        return
    _notify(
        db,
        ad.user_id,
        "ad_changes_requested",
        "Changes requested",
        f"Please update “{ad.title}”: {notes}",
        {"path": f"/advertise/edit/{ad.id}", "ad_id": ad.id},
    )


def notify_ad_published(db: Session, ad: Advertisement) -> None:
    if not ad.user_id:
        return
    _notify(
        db,
        ad.user_id,
        "ad_published",
        "Advertisement is live",
        f"“{ad.title}” is now on the homepage slider.",
        {"path": "/advertise/my", "ad_id": ad.id},
    )


def notify_ad_expired(db: Session, ad: Advertisement) -> None:
    if not ad.user_id:
        return
    _notify(
        db,
        ad.user_id,
        "ad_expired",
        "Advertisement expired",
        f"“{ad.title}” has expired and is no longer on the homepage.",
        {"path": "/advertise/my", "ad_id": ad.id},
    )


def approve_and_schedule(
    db: Session,
    ad: Advertisement,
    admin: User,
    *,
    display_position: int,
    start_date: datetime,
    end_date: datetime,
    show_on_homepage: bool,
) -> Advertisement:
    now = datetime.utcnow()
    start_date = _to_naive_utc(start_date)
    end_date = _to_naive_utc(end_date)
    next_status = "PUBLISHED"
    if start_date > now:
        next_status = "APPROVED"

    if end_date < now:
        next_status = "EXPIRED"

    updated = crud.update_advertisement(
        db,
        ad,
        {
            "status": next_status,
            "display_position": display_position,
            "start_date": start_date,
            "end_date": end_date,
            "show_on_homepage": show_on_homepage,
            "approved_by": admin.id,
            "approved_at": now,
            "admin_notes": None,
        },
    )

    if updated.user_id:
        if next_status == "PUBLISHED":
            notify_ad_published(db, updated)
        else:
            _notify(
                db,
                updated.user_id,
                "ad_approved",
                "Advertisement approved",
                f"“{updated.title}” is scheduled to go live on {start_date.strftime('%d %b %Y')}.",
                {"path": "/advertise/my", "ad_id": updated.id},
            )

    return updated
