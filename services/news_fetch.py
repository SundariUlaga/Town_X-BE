"""
Marketplace news pipeline — free tiers only, no LLM.

1. RSS ingest (no key, no daily cap)
2. NewsAPI.org ingest (optional, 100 req/day)
3. GNews ingest (optional, 100 req/day)
4. Keyword categorize + score
5. Persist to news_items; homepage reads the cache

Page views never call providers. Daily cron + admin POST /api/news/refresh do.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from sqlalchemy.orm import Session

from config import settings
from models import NewsItem

logger = logging.getLogger(__name__)

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

USER_AGENT = "Town-X/1.0 (real-estate marketplace; +https://townexchange.in)"

ALLOW_KEYWORDS = (
    "real estate",
    "property",
    "housing",
    "rera",
    "apartment",
    "flat",
    "villa",
    "plot",
    "builder",
    "home loan",
    "housing loan",
    "emi",
    "residential",
    "commercial property",
    "realty",
    "nri property",
    "stamp duty",
    "possession",
    "carpet area",
    "sqft",
    "sq ft",
)

BLOCK_KEYWORDS = (
    "cricket",
    "bollywood",
    "horoscope",
    "recipe",
    "fashion week",
    "ipl",
    "stock tips",
)

CATEGORY_RULES = (
    ("rera", ("rera", "occupancy certificate", "promoter")),
    ("loans", ("home loan", "housing loan", "emi", "interest rate", "repo rate")),
    ("policy", ("stamp duty", "registration", "gst", "budget", "circle rate")),
    ("launches", ("new launch", "under construction", "possession", "builder")),
    ("local", ("chennai", "omr", "ecr", "tamil nadu", "tamilnadu", "coimbatore")),
    ("market", ("price", "psf", "sqft", "sq ft", "demand", "supply", "realty")),
)

# Public RSS — no key. Google News search + a couple of publisher feeds.
RSS_FEEDS = (
    (
        "Google News",
        "https://news.google.com/rss/search?q=Chennai+real+estate+OR+RERA&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    (
        "Google News",
        "https://news.google.com/rss/search?q=%22Tamil+Nadu%22+(housing+OR+RERA+OR+property)&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    (
        "Google News",
        "https://news.google.com/rss/search?q=India+(home+loan+OR+EMI)+housing&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    (
        "Economic Times",
        "https://economictimes.indiatimes.com/industry/services/property-/-construction/rssfeeds/13352306.cms",
    ),
    (
        "The Hindu",
        "https://www.thehindu.com/news/cities/chennai/feeder/default.rss",
    ),
)


def newsapi_key() -> str:
    return (settings.NEWSAPI_KEY or settings.NEWS_API_KEY or "").strip()


def gnews_key() -> str:
    return (settings.GNEWS_KEY or "").strip()


def _passes_moderation(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    if any(b in text for b in BLOCK_KEYWORDS):
        return False
    return any(a in text for a in ALLOW_KEYWORDS)


def categorize(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    for name, needles in CATEGORY_RULES:
        if any(n in text for n in needles):
            return name
    return "market"


def relevance_score(title: str, summary: str = "", published_at: datetime | None = None) -> int:
    text = f"{title} {summary}".lower()
    score = 0
    if "chennai" in text:
        score += 4
    if "tamil nadu" in text or "tamilnadu" in text:
        score += 3
    if "rera" in text:
        score += 4
    if any(k in text for k in ("real estate", "property", "housing", "realty")):
        score += 2
    if any(k in text for k in ("home loan", "emi", "housing loan")):
        score += 2
    if published_at:
        age = datetime.utcnow() - published_at
        if age <= timedelta(days=3):
            score += 3
        elif age <= timedelta(days=14):
            score += 2
        elif age <= timedelta(days=45):
            score += 1
    return score


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
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean_text(value: str | None, limit: int | None = None) -> str:
    text = unescape(value or "")
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit:
        return text[:limit]
    return text


def _article(
    *,
    title: str,
    url: str,
    summary: str = "",
    source_name: str | None = None,
    image_url: str | None = None,
    published_at: datetime | None = None,
    provider: str,
) -> dict | None:
    title = _clean_text(title, 500)
    url = (url or "").strip()
    if not title or not url or title == "[Removed]":
        return None
    summary = _clean_text(summary, 400)
    if not _passes_moderation(title, summary):
        return None
    published = published_at or datetime.utcnow()
    return {
        "title": title,
        "summary": summary or None,
        "source_name": source_name,
        "url": url[:1000],
        "image_url": image_url,
        "published_at": published,
        "provider": provider,
        "category": categorize(title, summary),
        "relevance_score": relevance_score(title, summary, published),
    }


def _entry_image(entry) -> str | None:
    media = entry.get("media_content") or entry.get("media_thumbnail") or []
    if isinstance(media, list) and media:
        url = media[0].get("url")
        if url:
            return url
    if entry.get("image", {}).get("href"):
        return entry["image"]["href"]
    return None


def fetch_rss() -> list[dict]:
    """Piece 1 — RSS ingest. No key, no quota."""
    if feedparser is None:
        logger.warning("feedparser not installed — RSS ingest skipped")
        return []
    feedparser.USER_AGENT = USER_AGENT
    out: list[dict] = []
    for fallback_source, url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
        except Exception:
            logger.exception("RSS fetch failed: %s", url)
            continue
        feed_title = (parsed.feed.get("title") or fallback_source).strip()
        for entry in parsed.entries[:20]:
            source = fallback_source
            if entry.get("source") and entry.source.get("title"):
                source = entry.source.title
            elif feed_title and "google" not in feed_title.lower():
                source = feed_title
            art = _article(
                title=entry.get("title") or "",
                url=entry.get("link") or "",
                summary=entry.get("summary") or entry.get("description") or "",
                source_name=source,
                image_url=_entry_image(entry),
                published_at=_parse_dt(entry.get("published") or entry.get("updated")),
                provider="rss",
            )
            if art:
                out.append(art)
    logger.info("RSS ingest: %s articles after filters", len(out))
    return out


def fetch_newsapi() -> list[dict]:
    """Piece 2 — NewsAPI.org (optional). One request per refresh (free tier)."""
    key = newsapi_key()
    if not key:
        return []
    query = settings.NEWS_QUERY or "Chennai real estate OR RERA"
    articles: list[dict] = []
    everything = urllib.parse.urlencode(
        {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": key,
        }
    )
    try:
        data = _http_get_json(f"https://newsapi.org/v2/everything?{everything}")
        articles = data.get("articles") or []
    except urllib.error.HTTPError as e:
        # Developer (free) plan often blocks /everything — fall back to India business headlines.
        logger.warning("NewsAPI /everything %s — falling back to top-headlines", e.code)
        headlines = urllib.parse.urlencode(
            {
                "country": "in",
                "category": "business",
                "pageSize": 20,
                "apiKey": key,
            }
        )
        data = _http_get_json(f"https://newsapi.org/v2/top-headlines?{headlines}")
        articles = data.get("articles") or []

    out = []
    for art in articles:
        mapped = _article(
            title=art.get("title") or "",
            url=art.get("url") or "",
            summary=art.get("description") or "",
            source_name=(art.get("source") or {}).get("name"),
            image_url=art.get("urlToImage"),
            published_at=_parse_dt(art.get("publishedAt")),
            provider="newsapi",
        )
        if mapped:
            out.append(mapped)
    logger.info("NewsAPI ingest: %s articles after filters", len(out))
    return out


def fetch_gnews() -> list[dict]:
    """Piece 3 — GNews (optional). One request per refresh."""
    key = gnews_key()
    if not key:
        return []
    query = settings.NEWS_QUERY or "Chennai real estate OR RERA"
    params = urllib.parse.urlencode(
        {"q": query, "lang": "en", "max": 15, "apikey": key, "country": "in"}
    )
    data = _http_get_json(f"https://gnews.io/api/v4/search?{params}")
    out = []
    for art in data.get("articles") or []:
        mapped = _article(
            title=art.get("title") or "",
            url=art.get("url") or "",
            summary=art.get("description") or "",
            source_name=(art.get("source") or {}).get("name"),
            image_url=art.get("image"),
            published_at=_parse_dt(art.get("publishedAt")),
            provider="gnews",
        )
        if mapped:
            out.append(mapped)
    logger.info("GNews ingest: %s articles after filters", len(out))
    return out


def upsert_articles(db: Session, articles: list[dict]) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    seen_batch: set[str] = set()
    for art in articles:
        eid = _external_id(art["url"], art["title"])
        if eid in seen_batch:
            skipped += 1
            continue
        exists = db.query(NewsItem).filter(NewsItem.external_id == eid).first()
        if exists:
            exists.title = art["title"]
            exists.summary = art.get("summary")
            exists.category = art.get("category") or exists.category
            if art.get("relevance_score") is not None:
                exists.relevance_score = art["relevance_score"]
            exists.provider = art.get("provider") or exists.provider
            exists.is_approved = True
            skipped += 1
            seen_batch.add(eid)
            continue
        seen_batch.add(eid)
        db.add(
            NewsItem(
                external_id=eid,
                title=art["title"],
                summary=art.get("summary"),
                source_name=art.get("source_name"),
                url=art["url"],
                image_url=art.get("image_url"),
                published_at=art.get("published_at") or datetime.utcnow(),
                is_approved=True,
                category=art.get("category"),
                relevance_score=art.get("relevance_score") or 0,
                provider=art.get("provider"),
                fetched_at=datetime.utcnow(),
            )
        )
        inserted += 1
    if inserted or skipped:
        db.commit()
    return inserted, skipped


def scrub_html_summaries(db: Session) -> int:
    rows = db.query(NewsItem).filter(NewsItem.summary.isnot(None)).all()
    changed = 0
    for row in rows:
        cleaned = _clean_text(row.summary, 400) or None
        if cleaned != row.summary:
            row.summary = cleaned
            changed += 1
    if changed:
        db.commit()
    return changed


def retire_offtopic(db: Session) -> int:
    rows = db.query(NewsItem).filter(NewsItem.is_approved.is_(True)).all()
    hidden = 0
    for row in rows:
        if not _passes_moderation(row.title, row.summary or ""):
            row.is_approved = False
            hidden += 1
    if hidden:
        db.commit()
    return hidden


def retire_curated_desk(db: Session) -> int:
    """Hide seeded Town-X Desk placeholders once real provider URLs exist."""
    rows = (
        db.query(NewsItem)
        .filter(NewsItem.source_name == "Town-X Desk", NewsItem.is_approved.is_(True))
        .all()
    )
    for row in rows:
        row.is_approved = False
    if rows:
        db.commit()
    return len(rows)


def list_approved_news(db: Session, *, limit: int = 8) -> list[NewsItem]:
    return (
        db.query(NewsItem)
        .filter(NewsItem.is_approved.is_(True))
        .order_by(NewsItem.relevance_score.desc(), NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
        .all()
    )


def refresh_news_cache(db: Session, *, include_apis: bool = True) -> dict:
    """
    Piece 5 — persist. RSS always; NewsAPI/GNews when keys are set.
    Safe to re-run. Does not seed placeholder desk copy.
    """
    errors: list[str] = []
    rss_articles: list[dict] = []
    newsapi_articles: list[dict] = []
    gnews_articles: list[dict] = []

    try:
        rss_articles = fetch_rss()
    except Exception as e:
        logger.exception("RSS ingest failed")
        errors.append(f"rss: {e}")

    if include_apis:
        try:
            newsapi_articles = fetch_newsapi()
        except urllib.error.HTTPError as e:
            logger.error("NewsAPI HTTP error: %s %s", e.code, e.reason)
            errors.append(f"newsapi: {e.code}")
        except Exception as e:
            logger.exception("NewsAPI ingest failed")
            errors.append(f"newsapi: {e}")
        try:
            gnews_articles = fetch_gnews()
        except urllib.error.HTTPError as e:
            logger.error("GNews HTTP error: %s %s", e.code, e.reason)
            errors.append(f"gnews: {e.code}")
        except Exception as e:
            logger.exception("GNews ingest failed")
            errors.append(f"gnews: {e}")

    combined = rss_articles + newsapi_articles + gnews_articles
    inserted, skipped = upsert_articles(db, combined)
    has_real = (
        db.query(NewsItem)
        .filter(NewsItem.is_approved.is_(True), NewsItem.provider.isnot(None))
        .first()
        is not None
    )
    retired = retire_curated_desk(db) if has_real else 0
    offtopic = retire_offtopic(db)
    scrub_html_summaries(db)

    sources = []
    if rss_articles:
        sources.append("rss")
    if newsapi_articles:
        sources.append("newsapi")
    if gnews_articles:
        sources.append("gnews")

    result = {
        "inserted": inserted,
        "skipped": skipped,
        "seeded": 0,
        "retired": retired + offtopic,
        "rss": len(rss_articles),
        "newsapi": len(newsapi_articles),
        "gnews": len(gnews_articles),
        "source": "+".join(sources) or "none",
        "fetched": len(combined),
        "error": "; ".join(errors) if errors else None,
    }
    logger.info("News refresh: %s", result)
    return result


def refresh_news() -> dict:
    """CLI/startup helper: `python -c "from services.news_fetch import refresh_news; print(refresh_news())"`"""
    from database import SessionLocal
    from migrate_db import ensure_schema

    ensure_schema()
    db = SessionLocal()
    try:
        return refresh_news_cache(db, include_apis=True)
    finally:
        db.close()


def seed_curated_if_empty(db: Session) -> int:
    """Deprecated: RSS backfill replaces desk seed. Kept so old imports don't break."""
    if db.query(NewsItem).filter(NewsItem.is_approved.is_(True)).count() > 0:
        return 0
    result = refresh_news_cache(db, include_apis=False)
    return int(result.get("inserted") or 0)
