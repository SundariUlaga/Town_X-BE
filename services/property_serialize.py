"""Build PropertyResponse payloads with favourites, project details, and review notes."""

from __future__ import annotations

from sqlalchemy.orm import Session

import crud
from models import Property
from schemas import PropertyResponse, PropertyReviewNoteResponse, ProjectDetailsResponse


def _review_notes_for(db: Session, property_id: int) -> list[PropertyReviewNoteResponse]:
    notes = crud.get_property_review_notes(db, property_id)
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
    return review_notes


def serialize_property(db: Session, prop: Property, user_id: int | None = None) -> PropertyResponse:
    crud.attach_favourite_flags(db, [prop], user_id)
    details = crud.get_project_details_by_property_id(db, prop.id)
    project_payload = (
        ProjectDetailsResponse.model_validate(details) if details is not None else None
    )
    data = PropertyResponse.model_validate(prop)
    return data.model_copy(
        update={
            "review_notes": _review_notes_for(db, prop.id),
            "project_details": project_payload,
        }
    )


def serialize_properties(
    db: Session, props: list[Property], user_id: int | None = None
) -> list[PropertyResponse]:
    if not props:
        return []
    crud.attach_favourite_flags(db, props, user_id)
    details_map = crud.get_project_details_map(db, [p.id for p in props])
    out: list[PropertyResponse] = []
    for prop in props:
        details = details_map.get(prop.id)
        data = PropertyResponse.model_validate(prop)
        out.append(
            data.model_copy(
                update={
                    "project_details": (
                        ProjectDetailsResponse.model_validate(details) if details else None
                    ),
                    # Skip heavy review-note fetch on list payloads
                    "review_notes": [],
                }
            )
        )
    return out
