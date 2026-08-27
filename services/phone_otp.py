"""Prototype phone OTP auth — any number accepted, fixed demo OTP 000000."""

from __future__ import annotations

import re
import secrets

from auth import hash_password

DEMO_OTP = "000000"


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits


def phone_email(phone: str) -> str:
    return f"{phone}@phone.townx.local"


def default_display_name(phone: str) -> str:
    return f"User {phone[-4:]}"


def unusable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(24))
