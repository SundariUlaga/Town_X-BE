"""Tamil Nadu location hierarchy API (District → Taluk → Village).

Data sourced from india-village-finder (LGD / GODL-India):
https://github.com/mchittineni/india-village-finder
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query

from schemas import LocationItem, LocationMeta, LocationSearchResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locations", tags=["Locations"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tamil_nadu"


@lru_cache(maxsize=1)
def _load_districts() -> List[dict]:
    path = DATA_DIR / "districts.json"
    if not path.exists():
        raise FileNotFoundError(f"Location data missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_taluks() -> List[dict]:
    path = DATA_DIR / "taluks.json"
    if not path.exists():
        raise FileNotFoundError(f"Location data missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_villages() -> List[dict]:
    path = DATA_DIR / "villages.json"
    if not path.exists():
        raise FileNotFoundError(f"Location data missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _taluk_index_by_district() -> dict[int, List[dict]]:
    index: dict[int, List[dict]] = {}
    for taluk in _load_taluks():
        index.setdefault(taluk["district_id"], []).append(taluk)
    for items in index.values():
        items.sort(key=lambda item: item["name"].lower())
    return index


@lru_cache(maxsize=1)
def _village_index_by_taluk() -> dict[int, List[dict]]:
    index: dict[int, List[dict]] = {}
    for village in _load_villages():
        index.setdefault(village["taluk_id"], []).append(village)
    for items in index.values():
        items.sort(key=lambda item: item["name"].lower())
    return index


@lru_cache(maxsize=1)
def _district_by_id() -> dict[int, dict]:
    return {district["id"]: district for district in _load_districts()}


@lru_cache(maxsize=1)
def _taluk_by_id() -> dict[int, dict]:
    return {taluk["id"]: taluk for taluk in _load_taluks()}


@router.get("/search", response_model=List[LocationSearchResult])
async def search_locations(
    q: str = Query(..., min_length=2, description="Search districts, taluks, or villages"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search across the full Tamil Nadu location hierarchy."""
    try:
        districts = _load_districts()
        taluks = _load_taluks()
        villages = _load_villages()
        district_lookup = _district_by_id()
        taluk_lookup = _taluk_by_id()
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=503, detail="Location data is not available") from exc

    needle = q.casefold()
    results: List[dict] = []

    for district in districts:
        if needle in district["name"].casefold():
            results.append(
                {
                    "id": district["id"],
                    "name": district["name"],
                    "type": "district",
                    "label": district["name"],
                    "district_id": district["id"],
                    "district_name": district["name"],
                }
            )
        if len(results) >= limit:
            return results[:limit]

    for taluk in taluks:
        if needle in taluk["name"].casefold():
            district = district_lookup[taluk["district_id"]]
            results.append(
                {
                    "id": taluk["id"],
                    "name": taluk["name"],
                    "type": "taluk",
                    "label": f"{taluk['name']} · {district['name']}",
                    "district_id": district["id"],
                    "district_name": district["name"],
                    "taluk_id": taluk["id"],
                    "taluk_name": taluk["name"],
                }
            )
        if len(results) >= limit:
            return results[:limit]

    for village in villages:
        if needle in village["name"].casefold():
            taluk = taluk_lookup[village["taluk_id"]]
            district = district_lookup[taluk["district_id"]]
            pincode = village.get("pincode")
            suffix = f" · {pincode}" if pincode else ""
            results.append(
                {
                    "id": village["id"],
                    "name": village["name"],
                    "type": "village",
                    "label": f"{village['name']} · {taluk['name']} · {district['name']}{suffix}",
                    "district_id": district["id"],
                    "district_name": district["name"],
                    "taluk_id": taluk["id"],
                    "taluk_name": taluk["name"],
                    "pincode": pincode,
                }
            )
        if len(results) >= limit:
            break

    return results[:limit]


@router.get("/meta", response_model=LocationMeta)
async def get_location_meta():
    """Dataset metadata and counts."""
    meta_path = DATA_DIR / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))

    return {
        "state": "Tamil Nadu",
        "state_code": 33,
        "source": "india-village-finder / LGD (GODL-India)",
        "district_count": len(_load_districts()),
        "taluk_count": len(_load_taluks()),
        "village_count": len(_load_villages()),
    }


@router.get("/districts", response_model=List[LocationItem])
async def get_districts():
    """All Tamil Nadu districts (LGD)."""
    try:
        return _load_districts()
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=503, detail="Location data is not available") from exc


@router.get("/taluks/{district_id}", response_model=List[LocationItem])
async def get_taluks(district_id: int):
    """Taluks for a district (district_id = LGD district code)."""
    try:
        districts = {d["id"] for d in _load_districts()}
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=503, detail="Location data is not available") from exc

    if district_id not in districts:
        raise HTTPException(status_code=404, detail=f"District {district_id} not found")

    return _taluk_index_by_district().get(district_id, [])


@router.get("/villages/{taluk_id}", response_model=List[LocationItem])
async def get_villages(
    taluk_id: int,
    q: str | None = Query(None, min_length=2, description="Optional name filter"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Villages for a taluk (taluk_id = LGD taluk code)."""
    try:
        taluk_ids = {t["id"] for t in _load_taluks()}
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=503, detail="Location data is not available") from exc

    if taluk_id not in taluk_ids:
        raise HTTPException(status_code=404, detail=f"Taluk {taluk_id} not found")

    villages = _village_index_by_taluk().get(taluk_id, [])

    if q:
        needle = q.casefold()
        villages = [v for v in villages if needle in v["name"].casefold()]

    return villages[:limit]
