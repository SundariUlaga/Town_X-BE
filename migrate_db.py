"""
Lightweight schema sync for SQLite and PostgreSQL.

`create_all` only creates missing tables — it does not add new columns to
existing tables. This module patches common drift (e.g. owner_id on properties).
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from database import engine
from models import Base

logger = logging.getLogger(__name__)

# Logical type names — mapped per dialect in _sql_type()
PROPERTY_COLUMN_PATCHES: dict[str, str] = {
    "owner_id": "INTEGER",
    "status": "VARCHAR DEFAULT 'PUBLISHED'",
    "admin_notes": "TEXT",
    "published_at": "DATETIME",
    "title_deed_url": "VARCHAR",
    "survey_parcel_number": "VARCHAR",
    "encumbrance_certificate_status": "VARCHAR",
    "verification_tier": "VARCHAR DEFAULT 'unverified'",
    "commercial_subtype": "VARCHAR",
    "frontage_ft": "REAL",
    "floor_number": "INTEGER",
    "washroom_count": "INTEGER",
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


def _sql_type(dialect_name: str, logical: str) -> str:
    """Map SQLite-oriented type fragments to the active dialect."""
    if dialect_name == "postgresql":
        return logical.replace("DATETIME", "TIMESTAMP")
    return logical


def _existing_columns(conn: Connection, table: str) -> set[str]:
    inspector = inspect(conn)
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column_if_missing(
    conn: Connection, table: str, column: str, sql_type: str
) -> None:
    existing = _existing_columns(conn, table)
    if column in existing:
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
    logger.info("Added missing column %s.%s", table, column)


def ensure_schema(db_engine: Engine | None = None) -> None:
    """Create tables and apply additive column patches."""
    db_engine = db_engine or engine
    dialect = db_engine.dialect.name

    Base.metadata.create_all(bind=db_engine)

    inspector = inspect(db_engine)
    if not inspector.has_table("properties"):
        return

    with db_engine.begin() as conn:
        for column, logical in PROPERTY_COLUMN_PATCHES.items():
            _add_column_if_missing(
                conn, "properties", column, _sql_type(dialect, logical)
            )

        if inspector.has_table("users"):
            for column, logical in USER_COLUMN_PATCHES.items():
                _add_column_if_missing(
                    conn, "users", column, _sql_type(dialect, logical)
                )


def create_tables() -> None:
    ensure_schema()
    print("Database schema is up to date.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_tables()
