"""Cashfree Secure ID / DigiLocker eKYC client.

Demo mode (default when no API keys): simulates sandbox responses locally.
Sandbox mode: calls https://sandbox.cashfree.com/verification endpoints.

Docs: https://www.cashfree.com/docs/secure-id/digilocker/digilocker
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import settings

logger = logging.getLogger(__name__)

DEMO_MOBILE_OK = re.compile(r"^9988\d{6}$")
DEMO_AADHAAR_OK = re.compile(r"^\d{12}$")

# Set when sandbox credentials are configured but calls fall back to demo (e.g. IP whitelist).
_sandbox_fallback_active = False
_sandbox_fallback_reason: str | None = None


def sandbox_fallback_active() -> bool:
    return _sandbox_fallback_active


def sandbox_fallback_reason() -> str | None:
    return _sandbox_fallback_reason


def _mark_sandbox_fallback(reason: str) -> None:
    global _sandbox_fallback_active, _sandbox_fallback_reason
    if not _sandbox_fallback_active:
        logger.warning("Cashfree sandbox unavailable (%s) — using local demo fallback", reason)
    _sandbox_fallback_active = True
    _sandbox_fallback_reason = reason


def resolve_kyc_mode() -> str:
    if settings.KYC_MODE in {"demo", "sandbox"}:
        return settings.KYC_MODE
    return "sandbox" if settings.CASHFREE_CLIENT_ID else "demo"


def effective_kyc_mode() -> str:
    if resolve_kyc_mode() == "sandbox" and _sandbox_fallback_active:
        return "sandbox-fallback"
    return resolve_kyc_mode()


def new_verification_id(user_id: int) -> str:
    return f"TOWNX-{user_id}-{uuid.uuid4().hex[:8].upper()}"


def _normalize_mobile(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits


def _parse_cashfree_error(body: str) -> str:
    try:
        payload = json.loads(body)
        message = payload.get("message") or payload.get("error") or body
        code = payload.get("code")
        if code == "ip_validation_failed":
            return (
                "Cashfree sandbox blocked this server IP. Whitelist your IP in the "
                "Cashfree merchant dashboard (Secure ID → IP whitelisting), or keep "
                "KYC_DEV_FALLBACK_DEMO=true for local demo responses."
            )
        return str(message)
    except json.JSONDecodeError:
        return body or "Cashfree API error"


def _cashfree_request(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    url = f"{settings.CASHFREE_BASE_URL.rstrip('/')}{path}"
    headers = {
        "Content-Type": "application/json",
        "x-client-id": settings.CASHFREE_CLIENT_ID,
        "x-client-secret": settings.CASHFREE_CLIENT_SECRET,
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Cashfree HTTP %s for %s: %s", exc.code, path, detail)
        raise RuntimeError(_parse_cashfree_error(detail)) from exc
    except URLError as exc:
        logger.error("Cashfree network error for %s: %s", path, exc)
        raise RuntimeError("Unable to reach Cashfree verification service") from exc


def _with_sandbox_fallback(
    sandbox_fn: Callable[[], dict[str, Any]],
    demo_fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    mode = resolve_kyc_mode()
    if mode != "sandbox":
        return demo_fn()

    try:
        result = sandbox_fn()
        result["mode"] = "sandbox"
        return result
    except RuntimeError as exc:
        if settings.KYC_DEV_FALLBACK_DEMO:
            _mark_sandbox_fallback(str(exc))
            result = demo_fn()
            result["mode"] = "demo"
            result["sandbox_fallback"] = True
            return result
        raise


def demo_verify_account(
    verification_id: str,
    mobile_number: str | None = None,
    aadhaar_number: str | None = None,
) -> dict[str, Any]:
    """Simulates Cashfree verify-account using sandbox test-data rules."""
    mobile = _normalize_mobile(mobile_number) if mobile_number else None
    aadhaar = re.sub(r"\D", "", aadhaar_number) if aadhaar_number else None

    account_exists = bool(
        (mobile and DEMO_MOBILE_OK.match(mobile))
        or (aadhaar and DEMO_AADHAAR_OK.match(aadhaar))
    )

    result: dict[str, Any] = {
        "verification_id": verification_id,
        "reference_id": abs(hash(verification_id)) % 900000 + 10000,
        "status": "ACCOUNT_EXISTS" if account_exists else "ACCOUNT_NOT_FOUND",
    }
    if mobile:
        result["mobile_number"] = mobile
    if aadhaar:
        result["aadhaar_number"] = f"XXXX-XXXX-{aadhaar[-4:]}"
    if account_exists:
        result["digilocker_id"] = str(uuid.uuid4())
    return result


def demo_create_session(verification_id: str) -> dict[str, Any]:
    return {
        "verification_id": verification_id,
        "reference_id": abs(hash(verification_id + "session")) % 900000 + 10000,
        "url": f"/kyc/demo-consent?verification_id={verification_id}",
        "status": "PENDING",
        "user_flow": "signup",
        "document_requested": ["AADHAAR"],
        "redirect_url": settings.KYC_REDIRECT_URL,
    }


def demo_get_status(verification_id: str) -> dict[str, Any]:
    return {
        "verification_id": verification_id,
        "status": "PENDING",
    }


def verify_account(
    verification_id: str,
    mobile_number: str | None = None,
    aadhaar_number: str | None = None,
) -> dict[str, Any]:
    def sandbox_call() -> dict[str, Any]:
        payload: dict[str, str] = {"verification_id": verification_id}
        if mobile_number:
            payload["mobile_number"] = _normalize_mobile(mobile_number)
        if aadhaar_number:
            payload["aadhaar_number"] = re.sub(r"\D", "", aadhaar_number)
        return _cashfree_request("POST", "/digilocker/verify-account", payload)

    def demo_call() -> dict[str, Any]:
        return demo_verify_account(verification_id, mobile_number, aadhaar_number)

    return _with_sandbox_fallback(sandbox_call, demo_call)


def create_digilocker_session(verification_id: str) -> dict[str, Any]:
    def sandbox_call() -> dict[str, Any]:
        payload = {
            "verification_id": verification_id,
            "document_requested": ["AADHAAR"],
            "redirect_url": settings.KYC_REDIRECT_URL,
            "user_flow": "signup",
        }
        return _cashfree_request("POST", "/digilocker", payload)

    def demo_call() -> dict[str, Any]:
        return demo_create_session(verification_id)

    return _with_sandbox_fallback(sandbox_call, demo_call)


def get_verification_status(verification_id: str) -> dict[str, Any]:
    def sandbox_call() -> dict[str, Any]:
        return _cashfree_request("GET", f"/digilocker?verification_id={verification_id}")

    def demo_call() -> dict[str, Any]:
        return demo_get_status(verification_id)

    return _with_sandbox_fallback(sandbox_call, demo_call)
