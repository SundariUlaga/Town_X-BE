"""
Lightweight schema sync for SQLite.

`create_all` only creates missing tables — it does not add new columns to
existing tables. This module patches common drift (e.g. owner_id on properties).
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from database import engine
from models import Base

logger = logging.getLogger(__name__)

# column_name -> SQL type fragment for SQLite ALTER TABLE
PROPERTY_COLUMN_PATCHES: dict[str, str] = {
    "owner_id": "INTEGER",
    "status": "VARCHAR DEFAULT 'PUBLISHED'",
    "admin_notes": "TEXT",
    "published_at": "DATETIME",
    "title_deed_url": "VARCHAR",
    "survey_parcel_number": "VARCHAR",
    "encumbrance_certificate_status": "VARCHAR",
    "verification_tier": "VARCHAR DEFAULT 'unverified'",
}

USER_COLUMN_PATCHES: dict[str, str] = {
    "kyc_status": "VARCHAR DEFAULT 'pending'",
    "kyc_verification_id": "VARCHAR",
    "kyc_reference_id": "INTEGER",
    "kyc_mobile": "VARCHAR",
    "kyc_digilocker_id": "VARCHAR",
    "kyc_verified_at": "DATETIME",
    "phone": "VARCHAR",
}


def _existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _add_column_if_missing(conn, table: str, column: str, sql_type: str) -> None:
    existing = _existing_columns(conn, table)
    if column in existing:
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
    logger.info("Added missing column %s.%s", table, column)


def ensure_schema(db_engine: Engine | None = None) -> None:
    """Create tables and apply additive column patches."""
    db_engine = db_engine or engine

    Base.metadata.create_all(bind=db_engine)

    inspector = inspect(db_engine)
    if not inspector.has_table("properties"):
        return

    with db_engine.begin() as conn:
        for column, sql_type in PROPERTY_COLUMN_PATCHES.items():
            _add_column_if_missing(conn, "properties", column, sql_type)

        if inspector.has_table("users"):
            for column, sql_type in USER_COLUMN_PATCHES.items():
                _add_column_if_missing(conn, "users", column, sql_type)


def create_tables() -> None:
    ensure_schema()
    print("Database schema is up to date.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_tables()
