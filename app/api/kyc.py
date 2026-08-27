"""eKYC endpoints — Cashfree DigiLocker integration with demo mode."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
from auth import get_current_user
from config import settings
from database import get_db
from models import User
from schemas import (
    KycCreateSessionResponse,
    KycStatusResponse,
    KycVerifyAccountRequest,
    KycVerifyAccountResponse,
    UserResponse,
)
from services.cashfree_kyc import (
    create_digilocker_session,
    effective_kyc_mode,
    get_verification_status,
    new_verification_id,
    resolve_kyc_mode,
    sandbox_fallback_active,
    sandbox_fallback_reason,
    verify_account,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kyc", tags=["KYC"])


@router.get("/config")
async def get_kyc_config():
    """Public config so the frontend knows demo vs sandbox behaviour."""
    mode = resolve_kyc_mode()
    effective = effective_kyc_mode()
    fallback = sandbox_fallback_active()
    return {
        "mode": mode,
        "effective_mode": effective,
        "sandbox_fallback": fallback,
        "redirect_url": settings.KYC_REDIRECT_URL,
        "demo_hint": "Use mobile numbers starting with 9988 (e.g. 9988776655)",
        "sandbox_hint": (
            "Cashfree sandbox is configured. Whitelist your server IP in the merchant "
            "dashboard for live sandbox calls, or use demo fallback locally."
        ),
        "fallback_message": sandbox_fallback_reason(),
    }


@router.get("/status", response_model=KycStatusResponse)
async def get_kyc_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current user's KYC state; polls Cashfree when a session is in progress."""
    mode = resolve_kyc_mode()
    digilocker_status = None
    message = None

    if current_user.kyc_status == "verified":
        return KycStatusResponse(
            kyc_status="verified",
            verification_id=current_user.kyc_verification_id,
            reference_id=current_user.kyc_reference_id,
            mode=mode,
            message="Identity verified",
        )

    if current_user.kyc_verification_id and current_user.kyc_status == "in_progress":
        try:
            remote = get_verification_status(current_user.kyc_verification_id)
            digilocker_status = remote.get("status")
            if digilocker_status == "AUTHENTICATED":
                crud.update_user_kyc(
                    db,
                    current_user,
                    kyc_status="verified",
                    kyc_verified_at=datetime.utcnow(),
                )
                return KycStatusResponse(
                    kyc_status="verified",
                    verification_id=current_user.kyc_verification_id,
                    reference_id=current_user.kyc_reference_id,
                    digilocker_status=digilocker_status,
                    mode=mode,
                    message="DigiLocker consent granted",
                )
            message = f"DigiLocker status: {digilocker_status}"
        except RuntimeError as exc:
            logger.warning("KYC status poll failed: %s", exc)
            message = "Unable to refresh verification status"

    return KycStatusResponse(
        kyc_status=current_user.kyc_status,
        verification_id=current_user.kyc_verification_id,
        reference_id=current_user.kyc_reference_id,
        digilocker_status=digilocker_status,
        mode=mode,
        message=message,
    )


@router.post("/verify-account", response_model=KycVerifyAccountResponse)
async def kyc_verify_account(
    payload: KycVerifyAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 1 — Check if mobile/Aadhaar is registered with DigiLocker."""
    if current_user.kyc_status == "verified":
        raise HTTPException(status_code=400, detail="KYC already completed")

    verification_id = current_user.kyc_verification_id or new_verification_id(current_user.id)

    try:
        result = verify_account(
            verification_id,
            mobile_number=payload.mobile_number,
            aadhaar_number=payload.aadhaar_number,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if result.get("status") != "ACCOUNT_EXISTS":
        crud.update_user_kyc(
            db,
            current_user,
            kyc_status="failed",
            kyc_verification_id=verification_id,
            kyc_mobile=payload.mobile_number,
        )
        raise HTTPException(
            status_code=422,
            detail="No DigiLocker account found for this mobile/Aadhaar. Use demo mobile 9988776655.",
        )

    crud.update_user_kyc(
        db,
        current_user,
        kyc_status="pending",
        kyc_verification_id=verification_id,
        kyc_reference_id=result.get("reference_id"),
        kyc_mobile=payload.mobile_number,
        kyc_digilocker_id=result.get("digilocker_id"),
    )

    return KycVerifyAccountResponse(
        verification_id=verification_id,
        reference_id=result.get("reference_id"),
        status=result["status"],
        mobile_number=result.get("mobile_number"),
        aadhaar_number=result.get("aadhaar_number"),
        digilocker_id=result.get("digilocker_id"),
        mode=result.get("mode", resolve_kyc_mode()),
    )


@router.post("/create-session", response_model=KycCreateSessionResponse)
async def kyc_create_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 2 — Create DigiLocker consent URL after account verification."""
    if current_user.kyc_status == "verified":
        raise HTTPException(status_code=400, detail="KYC already completed")
    if not current_user.kyc_verification_id or not current_user.kyc_digilocker_id:
        raise HTTPException(status_code=400, detail="Complete account verification first")

    try:
        result = create_digilocker_session(current_user.kyc_verification_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    crud.update_user_kyc(
        db,
        current_user,
        kyc_status="in_progress",
        kyc_reference_id=result.get("reference_id"),
    )

    return KycCreateSessionResponse(
        verification_id=current_user.kyc_verification_id,
        reference_id=result.get("reference_id"),
        url=result["url"],
        status=result.get("status", "PENDING"),
        mode=result.get("mode", resolve_kyc_mode()),
    )


@router.post("/demo/complete", response_model=UserResponse)
async def kyc_demo_complete(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Demo / dev fallback — simulate DigiLocker consent without external redirect."""
    mode = resolve_kyc_mode()
    if mode == "sandbox" and not sandbox_fallback_active() and not settings.KYC_DEV_FALLBACK_DEMO:
        raise HTTPException(status_code=403, detail="Demo completion is only available in demo mode")
    if current_user.kyc_status == "verified":
        return current_user
    if not current_user.kyc_verification_id:
        raise HTTPException(status_code=400, detail="Start KYC verification first")

    user = crud.update_user_kyc(
        db,
        current_user,
        kyc_status="verified",
        kyc_verified_at=datetime.utcnow(),
    )
    logger.info("Demo KYC completed for user %s", user.email)
    return user
