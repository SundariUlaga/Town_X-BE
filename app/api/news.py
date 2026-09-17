from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth import require_role
from database import get_db
from models import User
from schemas import NewsItemResponse, NewsRefreshResponse
from services import news_fetch

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("", response_model=list[NewsItemResponse])
def get_news(
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Approved headlines from DB cache (not a live third-party call)."""
    news_fetch.seed_curated_if_empty(db)
    return news_fetch.list_approved_news(db, limit=limit)


@router.post("/refresh", response_model=NewsRefreshResponse)
def refresh_news(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Admin/manual trigger — same path as the daily scheduler."""
    result = news_fetch.refresh_news_cache(db)
    return NewsRefreshResponse(**result)
