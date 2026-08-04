"""Seed demo users for local development."""

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
    },
]


def seed_users() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for user in SEED_USERS:
            if crud.get_user_by_email(db, user["email"]):
                skipped += 1
                print(f"[skip] Already exists: {user['email']}")
                continue

            crud.create_user(
                db,
                name=user["name"],
                email=user["email"],
                password_hash=hash_password(user["password"]),
                role=user["role"],
            )
            created += 1
            print(f"[ok] Created {user['role']}: {user['email']}")

        print(f"\nDone — {created} created, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()
