"""Admin testimonial CRUD — approve, feature, reorder, optional Cloudinary avatar."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from auth import require_role
from config import settings
from database import get_db
from models import Testimonial, User
from schemas import (
    MessageResponse,
    TestimonialAdminItem,
    TestimonialFeatureRequest,
    TestimonialReorderRequest,
)
from services.audit import log_admin_action
from services import testimonials as testimonials_svc
from utils.cloudinary_config import delete_image_from_cloudinary, upload_image_to_cloudinary

router = APIRouter(prefix="/testimonials", tags=["Admin Testimonials"])


def _form_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _serialize(row: Testimonial) -> TestimonialAdminItem:
    return TestimonialAdminItem.model_validate(row)


async def _maybe_upload_avatar(file: Optional[UploadFile]) -> tuple[str | None, str | None]:
    if not file or not file.filename:
        return None, None
    uploaded = await upload_image_to_cloudinary(
        file, folder=settings.CLOUDINARY_FOLDER_TESTIMONIALS
    )
    return uploaded.get("url"), uploaded.get("public_id")


async def _replace_avatar(row: Testimonial, file: Optional[UploadFile]) -> None:
    url, public_id = await _maybe_upload_avatar(file)
    if not url:
        return
    if row.avatar_public_id:
        await delete_image_from_cloudinary(row.avatar_public_id)
    row.avatar_url = url
    row.avatar_public_id = public_id


@router.get("", response_model=List[TestimonialAdminItem])
async def list_testimonials(
    status: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    testimonials_svc.seed_if_empty(db)
    return [_serialize(row) for row in testimonials_svc.list_admin(db, status=status, featured=featured)]


@router.post("", response_model=TestimonialAdminItem)
async def create_testimonial(
    name: str = Form(...),
    quote: str = Form(...),
    role: str = Form("Buyer"),
    location: Optional[str] = Form(None),
    rating: int = Form(5),
    category: str = Form("buyer"),
    outcome: Optional[str] = Form(None),
    is_verified: str = Form("true"),
    is_featured: str = Form("true"),
    status: str = Form("approved"),
    display_order: Optional[int] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    category_n = testimonials_svc.normalize_category(category)
    row = Testimonial(
        name=name.strip(),
        role=(role or "Buyer").strip(),
        location=(location or "").strip() or None,
        quote=quote.strip(),
        rating=testimonials_svc.clamp_rating(rating),
        category=category_n,
        outcome=(outcome or "").strip() or testimonials_svc.DEFAULT_OUTCOME.get(category_n),
        is_verified=_form_bool(is_verified, True),
        is_featured=_form_bool(is_featured, True),
        status=testimonials_svc.normalize_status(status),
        display_order=display_order if display_order is not None else testimonials_svc.next_display_order(db),
    )
    await _replace_avatar(row, avatar)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_created",
        entity_type="testimonial",
        entity_id=row.id,
        new_value={"name": row.name, "is_featured": row.is_featured},
    )
    return _serialize(row)


@router.put("/reorder", response_model=List[TestimonialAdminItem])
async def reorder_testimonials(
    payload: TestimonialReorderRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    try:
        rows = testimonials_svc.apply_reorder(db, payload.ordered_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_reordered",
        entity_type="testimonial",
        entity_id=payload.ordered_ids[0],
        new_value={"ordered_ids": payload.ordered_ids},
    )
    return [_serialize(row) for row in rows]


@router.put("/{testimonial_id}", response_model=TestimonialAdminItem)
async def update_testimonial(
    testimonial_id: int,
    name: Optional[str] = Form(None),
    quote: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    rating: Optional[int] = Form(None),
    category: Optional[str] = Form(None),
    outcome: Optional[str] = Form(None),
    is_verified: Optional[str] = Form(None),
    is_featured: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    display_order: Optional[int] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    row = testimonials_svc.get_by_id(db, testimonial_id)
    if not row:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    old = {"is_featured": row.is_featured, "status": row.status}
    if name is not None:
        row.name = name.strip()
    if quote is not None:
        row.quote = quote.strip()
    if role is not None:
        row.role = role.strip()
    if location is not None:
        row.location = location.strip() or None
    if rating is not None:
        row.rating = testimonials_svc.clamp_rating(rating)
    if category is not None:
        row.category = testimonials_svc.normalize_category(category)
    if outcome is not None:
        row.outcome = outcome.strip() or None
    if is_verified is not None:
        row.is_verified = _form_bool(is_verified, row.is_verified)
    if is_featured is not None:
        row.is_featured = _form_bool(is_featured, row.is_featured)
    if status is not None:
        row.status = testimonials_svc.normalize_status(status)
    if display_order is not None:
        row.display_order = display_order
    await _replace_avatar(row, avatar)
    db.commit()
    db.refresh(row)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_updated",
        entity_type="testimonial",
        entity_id=row.id,
        old_value=old,
        new_value={"is_featured": row.is_featured, "status": row.status},
    )
    return _serialize(row)


@router.post("/{testimonial_id}/feature", response_model=TestimonialAdminItem)
async def feature_testimonial(
    testimonial_id: int,
    payload: TestimonialFeatureRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    row = testimonials_svc.get_by_id(db, testimonial_id)
    if not row:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    old = {"is_featured": row.is_featured, "status": row.status}
    row.is_featured = payload.is_featured
    if payload.is_featured:
        row.status = "approved"
    db.commit()
    db.refresh(row)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_featured" if payload.is_featured else "testimonial_unfeatured",
        entity_type="testimonial",
        entity_id=row.id,
        old_value=old,
        new_value={"is_featured": row.is_featured, "status": row.status},
    )
    return _serialize(row)


@router.post("/{testimonial_id}/approve", response_model=TestimonialAdminItem)
async def approve_testimonial(
    testimonial_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    row = testimonials_svc.get_by_id(db, testimonial_id)
    if not row:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    old = {"status": row.status, "is_featured": row.is_featured}
    row.status = "approved"
    db.commit()
    db.refresh(row)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_approved",
        entity_type="testimonial",
        entity_id=row.id,
        old_value=old,
        new_value={"status": row.status},
    )
    return _serialize(row)


@router.post("/{testimonial_id}/reject", response_model=TestimonialAdminItem)
async def reject_testimonial(
    testimonial_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    row = testimonials_svc.get_by_id(db, testimonial_id)
    if not row:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    old = {"status": row.status, "is_featured": row.is_featured}
    row.status = "rejected"
    row.is_featured = False
    db.commit()
    db.refresh(row)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_rejected",
        entity_type="testimonial",
        entity_id=row.id,
        old_value=old,
        new_value={"status": row.status, "is_featured": False},
    )
    return _serialize(row)


@router.delete("/{testimonial_id}", response_model=MessageResponse)
async def delete_testimonial(
    testimonial_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    row = testimonials_svc.get_by_id(db, testimonial_id)
    if not row:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    if row.avatar_public_id:
        await delete_image_from_cloudinary(row.avatar_public_id)
    db.delete(row)
    db.commit()
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="testimonial_deleted",
        entity_type="testimonial",
        entity_id=testimonial_id,
        old_value={"name": row.name},
    )
    return MessageResponse(message="Testimonial deleted")
