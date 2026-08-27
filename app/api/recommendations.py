"""Personalized recommendations."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
from auth import require_kyc_verified
from database import get_db
from models import User
from schemas import PropertyResponse, RecommendationsHomeResponse
from services.recommendations import get_home_recommendations

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


def _serialize_sections(db: Session, user: User, payload: dict) -> dict:
    sections = []
    for section in payload.get("sections", []):
        props = crud.attach_favourite_flags(db, section["properties"], user.id)
        sections.append(
            {
                "key": section["key"],
                "title": section["title"],
                "subtitle": section.get("subtitle"),
                "properties": [PropertyResponse.model_validate(p) for p in props],
            }
        )
    return {
        "personalized": payload["personalized"],
        "fallback": payload["fallback"],
        "sections": sections,
    }


@router.get("/home", response_model=RecommendationsHomeResponse)
async def home_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_kyc_verified),
):
    payload = get_home_recommendations(db, current_user)
    return _serialize_sections(db, current_user, payload)
