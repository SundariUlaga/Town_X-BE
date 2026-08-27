"""Seed demo users for local development."""

from datetime import datetime

from auth import hash_password
from database import SessionLocal, engine
from models import Base
import crud

SEED_USERS = [
    {
        "name": "Arjun Kumar",
        "email": "buyer@townx.demo",
        "password": "Buyer@123",
        "role": "buyer",
    },
    {
        "name": "Priya Menon",
        "email": "owner@townx.demo",
        "password": "Owner@123",
        "role": "owner",
    },
    {
        "name": "Platform Admin",
        "email": "admin@townx.demo",
        "password": "Admin@123",
        "role": "admin",
        "phone": "9999888877",
    },
]


def seed_users() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for user in SEED_USERS:
            existing = crud.get_user_by_email(db, user["email"])
            if existing:
                if existing.kyc_status != "verified":
                    crud.update_user_kyc(
                        db,
                        existing,
                        kyc_status="verified",
                        kyc_verified_at=datetime.utcnow(),
                    )
                    print(f"[ok] Marked KYC verified: {user['email']}")
                if user.get("phone") and not existing.phone:
                    existing.phone = user["phone"]
                    db.commit()
                    print(f"[ok] Set phone for: {user['email']}")
                else:
                    skipped += 1
                    print(f"[skip] Already exists: {user['email']}")
                continue

            created_user = crud.create_user(
                db,
                name=user["name"],
                email=user["email"],
                password_hash=hash_password(user["password"]),
                role=user["role"],
                phone=user.get("phone"),
            )
            crud.update_user_kyc(
                db,
                created_user,
                kyc_status="verified",
                kyc_verified_at=datetime.utcnow(),
            )
            created += 1
            print(f"[ok] Created {user['role']}: {user['email']}")

        print(f"\nDone — {created} created, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()
