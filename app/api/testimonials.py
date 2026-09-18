from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Testimonial, User
from schemas import (
    EnquiryFeedbackCreate,
    EnquiryFeedbackResponse,
    TestimonialPublicItem,
    TestimonialPublicResponse,
    TestimonialStats,
)
from services import testimonials as testimonials_svc
from services.notifications import notify_admins_review_queue

router = APIRouter(prefix="/api/testimonials", tags=["testimonials"])


@router.get("", response_model=TestimonialPublicResponse)
def get_testimonials(
    featured: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public homepage feed — all approved quotes (featured first)."""
    testimonials_svc.seed_if_empty(db)
    rows = testimonials_svc.list_public(db, featured_only=featured, limit=limit)
    return TestimonialPublicResponse(
        items=[TestimonialPublicItem.model_validate(row) for row in rows],
        stats=TestimonialStats(**testimonials_svc.public_stats(db)),
    )


@router.post("/from-enquiry", response_model=EnquiryFeedbackResponse)
def submit_enquiry_feedback(
    payload: EnquiryFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        row = testimonials_svc.submit_from_closed_enquiry(
            db,
            user=current_user,
            kind=payload.source,
            enquiry_id=payload.enquiry_id,
            quote=payload.quote,
            rating=payload.rating,
            outcome=payload.outcome,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    notify_admins_review_queue(
        db,
        type="testimonial_pending",
        title="New testimonial to review",
        body=f"{row.name} submitted feedback after a closed enquiry.",
        path="/testimonials",
    )
    return EnquiryFeedbackResponse(id=row.id, status=row.status)
