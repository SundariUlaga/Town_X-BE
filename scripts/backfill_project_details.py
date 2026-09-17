"""
One-off backfill: create ProjectDetails for legacy "New Project" properties.

Infers possession_date from available_from and builder_name from apartment_name
when user_type is Builder. Safe to re-run (skips properties that already have a row).

Usage (from Town_X-BE with venv active):
  python scripts/backfill_project_details.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import SessionLocal
from models import Property
from crud import (
    LEGACY_NEW_PROJECT_AGES,
    get_project_details_by_property_id,
    create_project_details_stub,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_project_details")


def main() -> None:
    db = SessionLocal()
    created = 0
    skipped = 0
    try:
        candidates = (
            db.query(Property)
            .filter(
                (Property.property_age.in_(LEGACY_NEW_PROJECT_AGES))
                | (Property.user_type == "Builder")
            )
            .all()
        )
        logger.info("Found %s candidate properties", len(candidates))
        for prop in candidates:
            if get_project_details_by_property_id(db, prop.id):
                skipped += 1
                continue
            create_project_details_stub(db, prop, commit=True)
            created += 1
            logger.info("Created ProjectDetails for property %s (%s)", prop.id, prop.city)
        logger.info("Done. created=%s skipped=%s", created, skipped)
    finally:
        db.close()


if __name__ == "__main__":
    main()
