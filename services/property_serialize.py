"""Build PropertyResponse payloads with favourites and review note history."""

from __future__ import annotations

from sqlalchemy.orm import Session

import crud
from models import Property
from schemas import PropertyResponse, PropertyReviewNoteResponse


def serialize_property(db: Session, prop: Property, user_id: int | None = None) -> PropertyResponse:
    crud.attach_favourite_flags(db, [prop], user_id)
    notes = crud.get_property_review_notes(db, prop.id)
    review_notes: list[PropertyReviewNoteResponse] = []
    for note in notes:
        admin_name = None
        if note.admin_user_id:
            admin = crud.get_user_by_id(db, note.admin_user_id)
            admin_name = admin.name if admin else None
        review_notes.append(
            PropertyReviewNoteResponse(
                id=note.id,
                property_id=note.property_id,
                admin_user_id=note.admin_user_id,
                admin_name=admin_name,
                note_type=note.note_type,
                note=note.note,
                created_at=note.created_at,
            )
        )
    data = PropertyResponse.model_validate(prop)
    return data.model_copy(update={"review_notes": review_notes})
