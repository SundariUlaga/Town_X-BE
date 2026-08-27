"""Admin audit logging."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import AuditLog


def log_admin_action(
    db: Session,
    *,
    admin_user_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        admin_user_id=admin_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
