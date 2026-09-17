"""
Fetch + moderate real-estate headlines into NewsItem cache.

Providers (free tiers):
  - NewsAPI.org  (NEWS_PROVIDER=newsapi)
  - GNews        (NEWS_PROVIDER=gnews)

Without NEWS_API_KEY, seeds curated TN/Chennai RE headlines so the UI works locally.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy.orm import Session

from config import settings
from models import NewsItem

logger = logging.getLogger(__name__)

ALLOW_KEYWORDS = (
    "real estate",
    "property",
    "housing",
    "rera",
    "apartment",
    "flat",
    "villa",
    "plot",
    "land",
    "builder",
    "home loan",
    "housing loan",
    "emi",
    "chennai",
    "tamil nadu",
    "tamilnadu",
    "coimbatore",
    "madurai",
    "trichy",
    "tiruchi",
    "salem",
    "residential",
    "commercial property",
    "realty",
    "nri property",
    "stamp duty",
    "registration",
)

BLOCK_KEYWORDS = (
    "cricket",
    "bollywood",
    "horoscope",
    "recipe",
    "fashion week",
)

CURATED_SEED = [
    {
        "title": "Tamil Nadu RERA: what homebuyers should verify before booking",
        "summary": "Registration number, promoter details, and approved plans remain the basic checks for new launches.",
        "source_name": "Town-X Desk",
        "url": "https://www.rera.tn.gov.in/#verify-before-booking",
    },
    {
        "title": "Chennai residential asking prices: how to read locality averages",
        "summary": "Use price per sqft alongside carpet area — asking prices are not closed deals.",
        "source_name": "Town-X Desk",
        "url": "https://www.chennai.nic.in/#locality-averages",
    },
    {
        "title": "Home loan EMI planning: down payment, rate, and tenure trade-offs",
        "summary": "A higher down payment cuts interest cost; longer tenure lowers EMI but raises total interest.",
        "source_name": "Town-X Desk",
        "url": "https://www.rbi.org.in/#emi-planning",
    },
    {
        "title": "Under-construction vs ready-to-move: possession risk checklist",
        "summary": "Compare RERA possession dates, builder track record, and available units before committing.",
        "source_name": "Town-X Desk",
        "url": "https://www.rera.tn.gov.in/#possession-checklist",
    },
]


def _passes_moderation(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    if any(b in text for b in BLOCK_KEYWORDS):
        return False
    return any(a in text for a in ALLOW_KEYWORDS)


def _external_id(url: str, title: str) -> str:
    raw = (url or title).strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:40]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, IndexError):
        return None


def _http_get_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Town-X/1.0 (real-estate marketplace)",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_newsapi(api_key: str, query: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": api_key,
        }
    )
    data = _http_get_json(f"https://newsapi.org/v2/everything?{params}")
    out = []
    for art in data.get("articles") or []:
        title = (art.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        url = (art.get("url") or "").strip()
        if not url:
            continue
        summary = (art.get("description") or "").strip()
        out.append(
            {
                "title": title,
                "summary": summary,
                "source_name": (art.get("source") or {}).get("name"),
                "url": url,
                "image_url": art.get("urlToImage"),
                "published_at": _parse_dt(art.get("publishedAt")),
            }
        )
    return out


def _fetch_gnews(api_key: str, query: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "lang": "en",
            "max": 15,
            "apikey": api_key,
        }
    )
    data = _http_get_json(f"https://gnews.io/api/v4/search?{params}")
    out = []
    for art in data.get("articles") or []:
        title = (art.get("title") or "").strip()
        url = (art.get("url") or "").strip()
        if not title or not url:
            continue
        summary = (art.get("description") or "").strip()
        out.append(
            {
                "title": title,
                "summary": summary,
                "source_name": (art.get("source") or {}).get("name"),
                "url": url,
                "image_url": art.get("image"),
                "published_at": _parse_dt(art.get("publishedAt")),
            }
        )
    return out


def upsert_articles(db: Session, articles: list[dict]) -> tuple[int, int]:
    """Insert new headlines; skip duplicates by external_id. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    seen_batch: set[str] = set()
    for art in articles:
        title = art["title"]
        summary = art.get("summary") or ""
        if not _passes_moderation(title, summary):
            skipped += 1
            continue
        eid = _external_id(art["url"], title)
        if eid in seen_batch:
            skipped += 1
            continue
        exists = db.query(NewsItem).filter(NewsItem.external_id == eid).first()
        if exists:
            skipped += 1
            continue
        seen_batch.add(eid)
        db.add(
            NewsItem(
                external_id=eid,
                title=title[:500],
                summary=(summary[:2000] if summary else None),
                source_name=(art.get("source_name") or None),
                url=art["url"][:1000],
                image_url=(art.get("image_url") or None),
                published_at=art.get("published_at") or datetime.utcnow(),
                is_approved=True,
                fetched_at=datetime.utcnow(),
            )
        )
        inserted += 1
    if inserted:
        db.commit()
    return inserted, skipped


def seed_curated_if_empty(db: Session) -> int:
    if db.query(NewsItem).count() > 0:
        return 0
    now = datetime.utcnow()
    articles = []
    for i, row in enumerate(CURATED_SEED):
        articles.append(
            {
                **row,
                "published_at": now,
                "image_url": None,
            }
        )
    inserted, _ = upsert_articles(db, articles)
    return inserted


def refresh_news_cache(db: Session) -> dict:
    """
    Daily job entrypoint. Uses free API when keyed; otherwise seeds curated copy.
    Always safe to re-run.
    """
    seeded = seed_curated_if_empty(db)

    api_key = (settings.NEWS_API_KEY or "").strip()
    if not api_key:
        logger.info("News fetch skipped (no NEWS_API_KEY) — serving cached/curated items")
        return {"inserted": 0, "skipped": 0, "seeded": seeded, "source": "curated"}

    provider = (settings.NEWS_PROVIDER or "newsapi").lower().strip()
    query = settings.NEWS_QUERY or 'Chennai real estate OR RERA'
    try:
        if provider == "gnews":
            articles = _fetch_gnews(api_key, query)
        else:
            articles = _fetch_newsapi(api_key, query)
        inserted, skipped = upsert_articles(db, articles)
        logger.info(
            "News refresh (%s): inserted=%s skipped=%s fetched=%s",
            provider,
            inserted,
            skipped,
            len(articles),
        )
        return {
            "inserted": inserted,
            "skipped": skipped,
            "seeded": seeded,
            "source": provider,
            "fetched": len(articles),
        }
    except urllib.error.HTTPError as e:
        logger.error("News API HTTP error: %s %s", e.code, e.reason)
        return {"inserted": 0, "skipped": 0, "seeded": seeded, "error": str(e)}
    except Exception as e:
        logger.exception("News refresh failed: %s", e)
        return {"inserted": 0, "skipped": 0, "seeded": seeded, "error": str(e)}


def list_approved_news(db: Session, *, limit: int = 8) -> list[NewsItem]:
    return (
        db.query(NewsItem)
        .filter(NewsItem.is_approved.is_(True))
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
        .all()
    )
