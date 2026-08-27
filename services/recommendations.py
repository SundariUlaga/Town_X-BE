"""Rule-based property recommendations (no ML)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import crud
from models import Property, SavedSearch, User, UserActivity, UserFavourite

MIN_ACTIVITY_FOR_PERSONALIZATION = 3


def _location_scores(db: Session, user_id: int) -> Counter:
    scores: Counter = Counter()
    activities = (
        db.query(UserActivity)
        .filter(UserActivity.user_id == user_id)
        .order_by(UserActivity.created_at.desc())
        .limit(100)
        .all()
    )
    for act in activities:
        weight = {"SEARCH": 1, "VIEW_PROPERTY": 2, "FAVOURITE": 5, "CONTACT": 8, "SAVE_SEARCH": 7}.get(
            act.activity_type, 1
        )
        if act.location_text:
            scores[act.location_text.lower()] += weight
        if act.search_query:
            scores[act.search_query.lower()] += weight
    return scores


def _exclude_ids(db: Session, user_id: int) -> set[int]:
    own = {row[0] for row in db.query(Property.id).filter(Property.owner_id == user_id).all()}
    favs = {row[0] for row in db.query(UserFavourite.property_id).filter(UserFavourite.user_id == user_id).all()}
    return own | favs


def _score_property(prop: Property, location_scores: Counter, viewed_ids: set[int]) -> float:
    score = 0.0
    loc_key = f"{prop.locality}, {prop.city}".lower()
    score += location_scores.get(loc_key, 0) * 2
    score += location_scores.get(prop.city.lower(), 0)
    score += location_scores.get(prop.locality.lower(), 0)
    if prop.id not in viewed_ids:
        score += 1
    if prop.published_at and prop.published_at >= datetime.utcnow() - timedelta(days=14):
        score += 2
    return score


def get_home_recommendations(db: Session, user: User, *, limit: int = 12) -> dict:
    published = crud.get_published_properties(db, skip=0, limit=200)
    exclude = _exclude_ids(db, user.id)
    candidates = [p for p in published if p.id not in exclude]

    activity_count = db.query(UserActivity).filter(UserActivity.user_id == user.id).count()
    location_scores = _location_scores(db, user.id)
    viewed_ids = {
        row[0]
        for row in db.query(UserActivity.entity_id)
        .filter(
            UserActivity.user_id == user.id,
            UserActivity.activity_type == "VIEW_PROPERTY",
            UserActivity.entity_id.isnot(None),
        )
        .all()
    }

    personalized = activity_count >= MIN_ACTIVITY_FOR_PERSONALIZATION and bool(location_scores)

    if personalized:
        ranked = sorted(candidates, key=lambda p: _score_property(p, location_scores, viewed_ids), reverse=True)
        top_location = location_scores.most_common(1)[0][0] if location_scores else None
    else:
        ranked = sorted(candidates, key=lambda p: p.created_at, reverse=True)
        top_location = None

    items = ranked[:limit]
    sections = []

    if items:
        sections.append(
            {
                "key": "recommended_for_you" if personalized else "recently_added",
                "title": "Recommended for you" if personalized else "Recently added",
                "subtitle": None if personalized else "Popular new listings on Town-X",
                "properties": items,
            }
        )

    if personalized and top_location:
        location_matches = [
            p
            for p in candidates
            if top_location in f"{p.locality}, {p.city}".lower() or top_location in p.city.lower()
        ][:8]
        if location_matches:
            sections.append(
                {
                    "key": "because_you_searched",
                    "title": f"Because you searched {top_location.title()}",
                    "subtitle": "Properties in areas you explore often",
                    "properties": location_matches,
                }
            )

    saved = (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == user.id, SavedSearch.is_active == True)
        .limit(3)
        .all()
    )
    for search in saved:
        matches = [p for p in candidates if crud.property_matches_criteria(p, search.criteria)][:6]
        if matches:
            sections.append(
                {
                    "key": f"saved_search_{search.id}",
                    "title": search.label or "Matches your saved search",
                    "subtitle": "New listings matching your alert",
                    "properties": matches,
                }
            )

    return {
        "personalized": personalized,
        "sections": sections,
        "fallback": not personalized,
    }
