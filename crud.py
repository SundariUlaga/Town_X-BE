import math
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Property, Story, StoryView, SupportQuestion, User, SavedSearch, Notification, Advertisement, UserFavourite, UserActivity, PropertyEnquiry, PropertyReport, AuditLog, PropertyReviewNote
from typing import List, Optional

# Setup logging
logger = logging.getLogger(__name__)


# ========================================
# USER / AUTH CRUD OPERATIONS
# ========================================

def create_user(
    db: Session,
    name: str,
    email: str,
    password_hash: str,
    role: str,
    phone: str | None = None,
) -> User:
    db_user = User(
        name=name,
        email=email,
        password_hash=password_hash,
        role=role,
        phone=phone,
        kyc_mobile=phone,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"✅ User created - ID: {db_user.id}, role: {role}")
    return db_user


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_user_by_phone(db: Session, phone: str) -> Optional[User]:
    return db.query(User).filter(User.phone == phone).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def update_user_kyc(
    db: Session,
    user: User,
    *,
    kyc_status: str,
    kyc_verification_id: str | None = None,
    kyc_reference_id: int | None = None,
    kyc_mobile: str | None = None,
    kyc_digilocker_id: str | None = None,
    kyc_verified_at=None,
) -> User:
    user.kyc_status = kyc_status
    if kyc_verification_id is not None:
        user.kyc_verification_id = kyc_verification_id
    if kyc_reference_id is not None:
        user.kyc_reference_id = kyc_reference_id
    if kyc_mobile is not None:
        user.kyc_mobile = kyc_mobile
    if kyc_digilocker_id is not None:
        user.kyc_digilocker_id = kyc_digilocker_id
    if kyc_verified_at is not None:
        user.kyc_verified_at = kyc_verified_at
    db.commit()
    db.refresh(user)
    return user


def update_user_profile(db: Session, user: User, *, name: str) -> User:
    user.name = name
    db.commit()
    db.refresh(user)
    return user


def create_support_question(
    db: Session,
    *,
    user_id: int,
    subject: str,
    message: str,
) -> SupportQuestion:
    question = SupportQuestion(user_id=user_id, subject=subject, message=message)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def get_user_support_questions(db: Session, user_id: int) -> List[SupportQuestion]:
    return (
        db.query(SupportQuestion)
        .filter(SupportQuestion.user_id == user_id)
        .order_by(SupportQuestion.created_at.desc())
        .all()
    )


# ========================================
# PROPERTY CRUD OPERATIONS
# ========================================

def create_property(db: Session, property_data: dict, images: List[dict]) -> Property:
    """Create a new property in the database"""
    db_property = Property(**property_data, images=images)
    db.add(db_property)
    db.commit()
    db.refresh(db_property)
    logger.info(f"✅ Property created - ID: {db_property.id}, City: {db_property.city}")
    return db_property


def get_properties(
        db: Session,
        skip: int = 0,
        limit: int = 20,
        city: Optional[str] = None,
        property_for: Optional[str] = None,
        property_type: Optional[str] = None,
        bhk_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        category: Optional[str] = None,
        furnishing_status: Optional[str] = None,
        favourites_only: bool = False,
        published_only: bool = True,
        owner_id: Optional[int] = None,
        status: Optional[str] = None,
) -> List[Property]:
    """Get all properties with optional filters"""
    query = db.query(Property)

    if published_only and status is None:
        query = query.filter(Property.status == "PUBLISHED")
    elif status:
        query = query.filter(Property.status == status)

    if owner_id is not None:
        query = query.filter(Property.owner_id == owner_id)

    # Category-based filtering
    if category:
        if category == "Rent/Lease":
            query = query.filter(Property.property_for == "Rent/Lease")
        elif category == "Buy Land/Homes":
            query = query.filter(Property.property_for == "Sell")
        elif category == "New Project":
            query = query.filter(Property.property_age.in_(["Under Construction", "0-1 Years"]))
        elif category == "Ready To Move/Resale":
            query = query.filter(
                Property.property_for == "Sell",
                ~Property.property_age.in_(["Under Construction"])
            )

    # Apply other filters
    if city:
        query = query.filter(Property.city.ilike(f"%{city}%"))
    if property_for:
        query = query.filter(Property.property_for == property_for)
    if property_type:
        query = query.filter(Property.property_type == property_type)
    if bhk_type:
        query = query.filter(Property.bhk_type == bhk_type)
    if min_price:
        query = query.filter(Property.expected_price >= min_price)
    if max_price:
        query = query.filter(Property.expected_price <= max_price)
    if furnishing_status:
        query = query.filter(Property.furnishing_status == furnishing_status)

    # Order by newest first
    query = query.order_by(Property.created_at.desc())

    return query.offset(skip).limit(limit).all()


def get_property_by_id(db: Session, property_id: int) -> Optional[Property]:
    """Get a single property by ID"""
    return db.query(Property).filter(Property.id == property_id).first()


def get_properties_by_owner(db: Session, owner_id: int, skip: int = 0, limit: int = 100) -> List[Property]:
    """Get all properties listed by a specific owner, newest first"""
    return (
        db.query(Property)
        .filter(Property.owner_id == owner_id)
        .order_by(Property.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_property(
        db: Session,
        property_id: int,
        property_data: dict
) -> Optional[Property]:
    """Update a property's information"""
    db_property = get_property_by_id(db, property_id)

    if db_property:
        for key, value in property_data.items():
            if hasattr(db_property, key):
                setattr(db_property, key, value)

        db.commit()
        db.refresh(db_property)
        logger.info(f"✅ Property updated - ID: {property_id}")

    return db_property


def delete_property(db: Session, property_id: int) -> bool:
    """Delete a property from database"""
    db_property = get_property_by_id(db, property_id)

    if db_property:
        db.delete(db_property)
        db.commit()
        logger.info(f"🗑️ Property deleted - ID: {property_id}")
        return True

    return False


def get_properties_count(db: Session) -> int:
    """Get total count of properties"""
    return db.query(Property).count()


def search_properties(db: Session, search_term: str, limit: int = 20) -> List[Property]:
    """Search properties by locality, city, or apartment name"""
    query = db.query(Property).filter(
        (Property.city.ilike(f"%{search_term}%")) |
        (Property.locality.ilike(f"%{search_term}%")) |
        (Property.apartment_name.ilike(f"%{search_term}%"))
    )

    results = query.order_by(Property.created_at.desc()).limit(limit).all()
    logger.info(f"🔍 Search '{search_term}' returned {len(results)} results")
    return results


def get_category_counts(db: Session) -> dict:
    """Get count of properties in each category"""
    return {
        "rent_lease": db.query(Property).filter(Property.property_for == "Rent/Lease").count(),
        "buy": db.query(Property).filter(Property.property_for == "Sell").count(),
        "new_projects": db.query(Property).filter(
            Property.property_age.in_(["Under Construction", "0-1 Years"])
        ).count(),
        "ready_to_move": db.query(Property).filter(
            Property.property_for == "Sell",
            ~Property.property_age.in_(["Under Construction"])
        ).count()
    }


def update_property_fields(db: Session, prop: Property, data: dict) -> Property:
    for key, value in data.items():
        if hasattr(prop, key):
            setattr(prop, key, value)
    prop.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prop)
    return prop


def create_property_review_note(
    db: Session,
    *,
    property_id: int,
    note_type: str,
    note: str,
    admin_user_id: int | None = None,
) -> PropertyReviewNote:
    entry = PropertyReviewNote(
        property_id=property_id,
        admin_user_id=admin_user_id,
        note_type=note_type,
        note=note.strip(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_property_review_notes(db: Session, property_id: int) -> list[PropertyReviewNote]:
    return (
        db.query(PropertyReviewNote)
        .filter(PropertyReviewNote.property_id == property_id)
        .order_by(PropertyReviewNote.created_at.desc())
        .all()
    )


def get_published_properties(db: Session, skip: int = 0, limit: int = 20) -> List[Property]:
    return (
        db.query(Property)
        .filter(Property.status == "PUBLISHED")
        .order_by(Property.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_user_favourite_ids(db: Session, user_id: int) -> set[int]:
    rows = db.query(UserFavourite.property_id).filter(UserFavourite.user_id == user_id).all()
    return {row[0] for row in rows}


def attach_favourite_flags(db: Session, properties: List[Property], user_id: int | None) -> List[Property]:
    if not user_id:
        for prop in properties:
            prop.is_favourite = False
        return properties
    fav_ids = get_user_favourite_ids(db, user_id)
    for prop in properties:
        prop.is_favourite = prop.id in fav_ids
    return properties


# ========================================
# FAVOURITE FUNCTIONS
# ========================================

def toggle_user_favourite(db: Session, user_id: int, property_id: int) -> tuple[bool, Property | None]:
    prop = get_property_by_id(db, property_id)
    if not prop:
        return False, None

    existing = (
        db.query(UserFavourite)
        .filter(UserFavourite.user_id == user_id, UserFavourite.property_id == property_id)
        .first()
    )
    if existing:
        db.delete(existing)
        is_favourite = False
    else:
        db.add(UserFavourite(user_id=user_id, property_id=property_id))
        is_favourite = True
    db.commit()
    prop.is_favourite = is_favourite
    return is_favourite, prop


def get_user_favourite_properties(
    db: Session, user_id: int, skip: int = 0, limit: int = 100
) -> List[Property]:
    rows = (
        db.query(Property)
        .join(UserFavourite, UserFavourite.property_id == Property.id)
        .filter(UserFavourite.user_id == user_id)
        .order_by(UserFavourite.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    for prop in rows:
        prop.is_favourite = True
    return rows


def get_user_favourites_count(db: Session, user_id: int) -> int:
    return db.query(UserFavourite).filter(UserFavourite.user_id == user_id).count()


def toggle_favourite(db: Session, property_id: int) -> Optional[Property]:
    """Deprecated global toggle — kept for backward compatibility."""
    property_data = get_property_by_id(db, property_id)
    if property_data:
        property_data.is_favourite = not property_data.is_favourite
        db.commit()
        db.refresh(property_data)
    return property_data


def get_favourite_properties(db: Session, skip: int = 0, limit: int = 100) -> List[Property]:
    """Deprecated global favourites list."""
    return db.query(Property).filter(Property.is_favourite == True).order_by(Property.created_at.desc()).offset(skip).limit(limit).all()


def get_favourites_count(db: Session) -> int:
    return db.query(Property).filter(Property.is_favourite == True).count()


# ========================================
# LOCATION-BASED FUNCTIONS
# ========================================

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula
    Returns distance in kilometers

    Args:
        lat1: Latitude of point 1
        lon1: Longitude of point 1
        lat2: Latitude of point 2
        lon2: Longitude of point 2

    Returns:
        float: Distance in kilometers
    """
    R = 6371  # Earth's radius in kilometers

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    return distance


def get_properties_by_location(
        db: Session,
        user_lat: float,
        user_lon: float,
        radius_km: float = 10,
        skip: int = 0,
        limit: int = 20
) -> List[Property]:
    """
    Get properties within a radius of user's location

    Args:
        db: Database session
        user_lat: User's latitude
        user_lon: User's longitude
        radius_km: Search radius in kilometers
        skip: Pagination offset
        limit: Maximum results

    Returns:
        List[Property]: Properties within radius, sorted by distance
    """
    # Get all properties with lat/long
    properties = db.query(Property).filter(
        Property.latitude.isnot(None),
        Property.longitude.isnot(None)
    ).all()

    # Calculate distances and filter
    properties_with_distance = []
    for prop in properties:
        distance = calculate_distance(user_lat, user_lon, prop.latitude, prop.longitude)
        if distance <= radius_km:
            # Add distance as a temporary attribute (not stored in DB)
            prop.distance_km = round(distance, 2)
            properties_with_distance.append(prop)

    # Sort by distance (closest first)
    properties_with_distance.sort(key=lambda x: x.distance_km)

    logger.info(f"📍 Found {len(properties_with_distance)} properties within {radius_km}km")

    # Apply pagination
    return properties_with_distance[skip:skip + limit]


# ========================================
# STORY CRUD OPERATIONS
# ========================================

def create_story(db: Session, story_data: dict, media_info: dict) -> Story:
    """
    Create a new story that expires in 24 hours

    Args:
        db: Database session
        story_data: Dict with optional fields (user_id, property_id, caption, location)
        media_info: Dict with required fields (url, type, public_id) and optional (thumbnail_url)

    Returns:
        Story: Created story object
    """
    from config import settings

    # Calculate expiry time (configurable hours from settings)
    expires_at = datetime.utcnow() + timedelta(hours=settings.STORY_EXPIRY_HOURS)

    db_story = Story(
        user_id=story_data.get("user_id"),
        property_id=story_data.get("property_id"),
        media_url=media_info["url"],
        media_type=media_info["type"],
        public_id=media_info["public_id"],
        thumbnail_url=media_info.get("thumbnail_url"),
        caption=story_data.get("caption"),
        location=story_data.get("location"),
        expires_at=expires_at,
        is_active=True,
        views_count=0
    )

    db.add(db_story)
    db.commit()
    db.refresh(db_story)

    logger.info(f"✅ Story created - ID: {db_story.id}, Type: {db_story.media_type}, Expires: {expires_at}")

    return db_story


def get_active_stories(db: Session, limit: int = 50) -> List[Story]:
    """
    Get all active stories that haven't expired

    Args:
        db: Database session
        limit: Maximum number of stories to return

    Returns:
        List[Story]: List of active stories
    """
    current_time = datetime.utcnow()

    stories = db.query(Story).filter(
        Story.is_active == True,
        Story.expires_at > current_time
    ).order_by(Story.created_at.desc()).limit(limit).all()

    logger.info(f"📖 Retrieved {len(stories)} active stories")

    return stories


def get_story_by_id(db: Session, story_id: int) -> Optional[Story]:
    """
    Get a single story by ID

    Args:
        db: Database session
        story_id: Story ID

    Returns:
        Story or None: Story object if found and active
    """
    return db.query(Story).filter(
        Story.id == story_id,
        Story.is_active == True
    ).first()


def increment_story_views(
        db: Session,
        story_id: int,
        viewer_id: Optional[str] = None,
        viewer_ip: Optional[str] = None
) -> Optional[Story]:
    """
    Increment view count and optionally track who viewed it

    Args:
        db: Database session
        story_id: Story ID
        viewer_id: Optional viewer user ID
        viewer_ip: Optional viewer IP address

    Returns:
        Story or None: Updated story object
    """
    story = db.query(Story).filter(Story.id == story_id).first()

    if story and not story.is_expired:
        story.views_count += 1

        # Optionally track individual views
        if viewer_id or viewer_ip:
            story_view = StoryView(
                story_id=story_id,
                viewer_id=viewer_id,
                viewer_ip=viewer_ip
            )
            db.add(story_view)

        db.commit()
        db.refresh(story)

        logger.info(f"👁️ Story {story_id} view count: {story.views_count}")

    return story


def delete_expired_stories(db: Session) -> int:
    """
    Delete expired stories and their media from Cloudinary
    This should be run by a background job every hour

    Args:
        db: Database session

    Returns:
        int: Number of stories deleted
    """
    current_time = datetime.utcnow()

    expired_stories = db.query(Story).filter(
        Story.expires_at <= current_time,
        Story.is_active == True
    ).all()

    if not expired_stories:
        logger.info("✅ No expired stories to clean up")
        return 0

    deleted_count = 0
    public_ids = []

    for story in expired_stories:
        public_ids.append(story.public_id)
        story.is_active = False
        deleted_count += 1

    # Delete from Cloudinary in batch
    if public_ids:
        try:
            logger.info(f"☁️ Deleting {len(public_ids)} media files from Cloudinary...")

            # Import here to avoid circular dependency
            from utils.cloudinary_config import delete_multiple_images
            import asyncio

            # Check if event loop is already running (in async context)
            try:
                loop = asyncio.get_running_loop()
                # If we're in an async context, create a task
                future = asyncio.ensure_future(delete_multiple_images(public_ids))
                # This will be handled by the existing event loop
            except RuntimeError:
                # No event loop running, create new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(delete_multiple_images(public_ids))
                finally:
                    loop.close()

            logger.info(f"✅ Deleted {len(public_ids)} media files from Cloudinary")

        except Exception as e:
            logger.error(f"❌ Error deleting media from Cloudinary: {e}")
            # Continue even if Cloudinary deletion fails
            pass

    db.commit()
    logger.info(f"✅ Marked {deleted_count} expired stories as inactive")

    return deleted_count


def delete_story(db: Session, story_id: int) -> bool:
    """
    Delete a specific story (soft delete)

    Args:
        db: Database session
        story_id: Story ID

    Returns:
        bool: True if deleted, False if not found
    """
    story = get_story_by_id(db, story_id)

    if story:
        # Soft delete
        story.is_active = False
        db.commit()
        logger.info(f"🗑️ Story {story_id} soft deleted")
        return True

    logger.warning(f"⚠️ Story {story_id} not found for deletion")
    return False


def delete_story_permanently(db: Session, story_id: int) -> bool:
    """
    Permanently delete a story from database

    Args:
        db: Database session
        story_id: Story ID

    Returns:
        bool: True if deleted, False if not found
    """
    story = db.query(Story).filter(Story.id == story_id).first()

    if story:
        db.delete(story)
        db.commit()
        logger.info(f"🗑️ Story {story_id} permanently deleted from database")
        return True

    return False


def get_property_stories(db: Session, property_id: int) -> List[Story]:
    """
    Get all active stories for a specific property

    Args:
        db: Database session
        property_id: Property ID

    Returns:
        List[Story]: List of stories for the property
    """
    current_time = datetime.utcnow()

    stories = db.query(Story).filter(
        Story.property_id == property_id,
        Story.is_active == True,
        Story.expires_at > current_time
    ).order_by(Story.created_at.desc()).all()

    logger.info(f"📖 Retrieved {len(stories)} stories for property {property_id}")

    return stories


def get_user_stories(db: Session, user_id: str) -> List[Story]:
    """
    Get all active stories by a specific user

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List[Story]: List of user's stories
    """
    current_time = datetime.utcnow()

    stories = db.query(Story).filter(
        Story.user_id == user_id,
        Story.is_active == True,
        Story.expires_at > current_time
    ).order_by(Story.created_at.desc()).all()

    logger.info(f"📖 Retrieved {len(stories)} stories for user {user_id}")

    return stories


def get_story_stats(db: Session) -> dict:
    """
    Get statistics about stories

    Args:
        db: Database session

    Returns:
        dict: Statistics including total, active, expired stories and views
    """
    current_time = datetime.utcnow()

    total_stories = db.query(Story).count()
    active_stories = db.query(Story).filter(
        Story.is_active == True,
        Story.expires_at > current_time
    ).count()
    expired_stories = db.query(Story).filter(
        Story.expires_at <= current_time
    ).count()
    total_views = db.query(func.sum(Story.views_count)).scalar() or 0

    stats = {
        "total_stories": total_stories,
        "active_stories": active_stories,
        "expired_stories": expired_stories,
        "total_views": int(total_views),
        "average_views": round(total_views / total_stories, 2) if total_stories > 0 else 0
    }

    logger.info(f"📊 Story stats - Total: {total_stories}, Active: {active_stories}, Views: {total_views}")

    return stats


def get_trending_stories(db: Session, limit: int = 10) -> List[Story]:
    """
    Get trending stories (most viewed) that are still active

    Args:
        db: Database session
        limit: Number of stories to return

    Returns:
        List[Story]: List of trending stories
    """
    current_time = datetime.utcnow()

    stories = db.query(Story).filter(
        Story.is_active == True,
        Story.expires_at > current_time
    ).order_by(Story.views_count.desc()).limit(limit).all()

    logger.info(f"🔥 Retrieved {len(stories)} trending stories")

    return stories


def get_recent_story_views(db: Session, story_id: int, limit: int = 50) -> List[StoryView]:
    """
    Get recent views for a story

    Args:
        db: Database session
        story_id: Story ID
        limit: Number of views to return

    Returns:
        List[StoryView]: List of story views
    """
    views = db.query(StoryView).filter(
        StoryView.story_id == story_id
    ).order_by(StoryView.viewed_at.desc()).limit(limit).all()

    logger.info(f"👁️ Retrieved {len(views)} views for story {story_id}")

    return views


def cleanup_old_story_views(db: Session, days: int = 7) -> int:
    """
    Delete story views older than specified days

    Args:
        db: Database session
        days: Number of days to keep views

    Returns:
        int: Number of views deleted
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    deleted_count = db.query(StoryView).filter(
        StoryView.viewed_at < cutoff_date
    ).delete()

    db.commit()

    logger.info(f"🧹 Cleaned up {deleted_count} old story views (older than {days} days)")

    return deleted_count


# ========================================
# BULK OPERATIONS (BONUS)
# ========================================

def bulk_delete_stories(db: Session, story_ids: List[int]) -> int:
    """
    Bulk delete multiple stories (soft delete)

    Args:
        db: Database session
        story_ids: List of story IDs to delete

    Returns:
        int: Number of stories deleted
    """
    deleted_count = db.query(Story).filter(
        Story.id.in_(story_ids),
        Story.is_active == True
    ).update({"is_active": False}, synchronize_session=False)

    db.commit()
    logger.info(f"🗑️ Bulk deleted {deleted_count} stories")

    return deleted_count


def get_stories_expiring_soon(db: Session, hours: int = 1, limit: int = 50) -> List[Story]:
    """
    Get stories that will expire within specified hours

    Args:
        db: Database session
        hours: Number of hours to look ahead
        limit: Maximum stories to return

    Returns:
        List[Story]: Stories expiring soon
    """
    current_time = datetime.utcnow()
    expiry_threshold = current_time + timedelta(hours=hours)

    stories = db.query(Story).filter(
        Story.is_active == True,
        Story.expires_at > current_time,
        Story.expires_at <= expiry_threshold
    ).order_by(Story.expires_at.asc()).limit(limit).all()

    logger.info(f"⏰ Found {len(stories)} stories expiring within {hours} hour(s)")

    return stories


# ========================================
# SAVED SEARCH & NOTIFICATION CRUD
# ========================================

def _criteria_key(criteria: dict) -> str:
    """Stable key for deduplicating saved searches."""
    parts = []
    for key in sorted(criteria.keys()):
        value = criteria.get(key)
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    return "|".join(parts).lower()


def build_saved_search_label(criteria: dict) -> str:
    if criteria.get("q"):
        return str(criteria["q"]).strip()[:120]
    bits = [criteria.get("city"), criteria.get("locality"), criteria.get("bhk_type")]
    label = ", ".join([b for b in bits if b])
    if criteria.get("property_for"):
        label = f"{label} · {criteria['property_for']}" if label else str(criteria["property_for"])
    return (label or "Property search")[:120]


def upsert_saved_search(
    db: Session,
    *,
    user_id: int,
    criteria: dict,
    label: str | None = None,
    is_active: bool = True,
) -> SavedSearch:
    normalized = {k: v for k, v in criteria.items() if v is not None and v != ""}
    key = _criteria_key(normalized)
    existing = get_user_saved_searches(db, user_id)
    for row in existing:
        if _criteria_key(row.criteria or {}) == key:
            row.label = label or row.label
            row.criteria = normalized
            row.is_active = is_active
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return row

    if len(existing) >= 20:
        oldest = sorted(existing, key=lambda r: r.updated_at or r.created_at)[0]
        db.delete(oldest)
        db.commit()

    search = SavedSearch(
        user_id=user_id,
        label=label or build_saved_search_label(normalized),
        criteria=normalized,
        is_active=is_active,
    )
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


def get_user_saved_searches(db: Session, user_id: int) -> List[SavedSearch]:
    return (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == user_id)
        .order_by(SavedSearch.updated_at.desc())
        .all()
    )


def delete_saved_search(db: Session, user_id: int, search_id: int) -> bool:
    row = (
        db.query(SavedSearch)
        .filter(SavedSearch.id == search_id, SavedSearch.user_id == user_id)
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def get_active_saved_searches(db: Session) -> List[SavedSearch]:
    return (
        db.query(SavedSearch)
        .filter(SavedSearch.is_active == True)
        .order_by(SavedSearch.updated_at.desc())
        .all()
    )


def property_matches_criteria(property_row: Property, criteria: dict) -> bool:
    if not criteria:
        return False

    if criteria.get("city"):
        if criteria["city"].lower() not in (property_row.city or "").lower():
            return False

    if criteria.get("locality"):
        if criteria["locality"].lower() not in (property_row.locality or "").lower():
            return False

    if criteria.get("property_for") and property_row.property_for != criteria["property_for"]:
        return False

    if criteria.get("property_type") and property_row.property_type != criteria["property_type"]:
        return False

    if criteria.get("bhk_type") and property_row.bhk_type != criteria["bhk_type"]:
        return False

    if criteria.get("furnishing_status") and property_row.furnishing_status != criteria["furnishing_status"]:
        return False

    min_price = criteria.get("min_price")
    if min_price is not None and property_row.expected_price < float(min_price):
        return False

    max_price = criteria.get("max_price")
    if max_price is not None and property_row.expected_price > float(max_price):
        return False

    category = criteria.get("category")
    if category == "Rent/Lease" and property_row.property_for != "Rent/Lease":
        return False
    if category == "Buy Land/Homes" and property_row.property_for != "Sell":
        return False

    q = (criteria.get("q") or "").strip().lower()
    if q:
        haystack = " ".join(
            filter(
                None,
                [property_row.locality, property_row.city, property_row.apartment_name or ""],
            )
        ).lower()
        if q not in haystack:
            return False

    return True


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: str,
    title: str,
    body: str,
    property_id: int | None = None,
    saved_search_id: int | None = None,
    payload: dict | None = None,
) -> Notification:
    note = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        property_id=property_id,
        saved_search_id=saved_search_id,
        payload=payload,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def notification_exists(
    db: Session,
    *,
    user_id: int,
    type: str,
    property_id: int | None = None,
    saved_search_id: int | None = None,
) -> bool:
    query = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == type,
    )
    if property_id is not None:
        query = query.filter(Notification.property_id == property_id)
    if saved_search_id is not None:
        query = query.filter(Notification.saved_search_id == saved_search_id)
    return query.first() is not None


def get_user_notifications(
    db: Session,
    user_id: int,
    *,
    skip: int = 0,
    limit: int = 30,
    unread_only: bool = False,
) -> tuple[List[Notification], int]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    total = query.count()
    items = (
        query.order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def get_unread_notification_count(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .count()
    )


def mark_notification_read(db: Session, user_id: int, notification_id: int) -> Optional[Notification]:
    note = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not note:
        return None
    note.is_read = True
    db.commit()
    db.refresh(note)
    return note


def mark_all_notifications_read(db: Session, user_id: int) -> int:
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .update({Notification.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return updated


# ========================================
# ADVERTISEMENT CRUD
# ========================================

def create_advertisement(db: Session, data: dict) -> Advertisement:
    ad = Advertisement(**data)
    db.add(ad)
    db.commit()
    db.refresh(ad)
    logger.info("Advertisement created #%s — %s", ad.id, ad.title)
    return ad


def get_advertisement_by_id(db: Session, ad_id: int) -> Optional[Advertisement]:
    return db.query(Advertisement).filter(Advertisement.id == ad_id).first()


def get_user_advertisements(db: Session, user_id: int) -> List[Advertisement]:
    return (
        db.query(Advertisement)
        .filter(Advertisement.user_id == user_id)
        .order_by(Advertisement.created_at.desc())
        .all()
    )


def get_all_advertisements(db: Session, status: Optional[str] = None) -> List[Advertisement]:
    query = db.query(Advertisement)
    if status:
        query = query.filter(Advertisement.status == status)
    return query.order_by(Advertisement.display_position.asc(), Advertisement.created_at.desc()).all()


def update_advertisement(db: Session, ad: Advertisement, data: dict) -> Advertisement:
    for key, value in data.items():
        if hasattr(ad, key):
            setattr(ad, key, value)
    ad.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ad)
    return ad


def refresh_advertisement_statuses(db: Session) -> int:
    """Expire published ads past end_date; publish approved ads past start_date."""
    from services.ad_lifecycle import notify_ad_expired, notify_ad_published

    now = datetime.utcnow()
    changed = 0

    expired = (
        db.query(Advertisement)
        .filter(
            Advertisement.status == "PUBLISHED",
            Advertisement.end_date.isnot(None),
            Advertisement.end_date < now,
        )
        .all()
    )
    for ad in expired:
        ad.status = "EXPIRED"
        notify_ad_expired(db, ad)
        changed += 1

    to_publish = (
        db.query(Advertisement)
        .filter(
            Advertisement.status == "APPROVED",
            Advertisement.show_on_homepage == True,
            Advertisement.start_date.isnot(None),
            Advertisement.start_date <= now,
            (Advertisement.end_date.is_(None)) | (Advertisement.end_date >= now),
        )
        .all()
    )
    for ad in to_publish:
        ad.status = "PUBLISHED"
        notify_ad_published(db, ad)
        changed += 1

    if changed:
        db.commit()
    return changed


def get_homepage_slider_ads(db: Session) -> List[Advertisement]:
    refresh_advertisement_statuses(db)
    now = datetime.utcnow()
    return (
        db.query(Advertisement)
        .filter(
            Advertisement.status == "PUBLISHED",
            Advertisement.show_on_homepage == True,
            (Advertisement.start_date.is_(None)) | (Advertisement.start_date <= now),
            (Advertisement.end_date.is_(None)) | (Advertisement.end_date >= now),
        )
        .order_by(Advertisement.display_position.asc(), Advertisement.created_at.desc())
        .all()
    )


def track_advertisement_event(db: Session, ad: Advertisement, event: str) -> Advertisement:
    if event == "impression":
        ad.impressions += 1
    elif event == "view":
        ad.views += 1
    elif event == "click":
        ad.clicks += 1
    elif event == "enquiry":
        ad.enquiries += 1
    db.commit()
    db.refresh(ad)
    return ad


def count_advertisements_by_status(db: Session, status: str) -> int:
    return db.query(Advertisement).filter(Advertisement.status == status).count()


def get_admin_dashboard_stats(db: Session) -> dict:
    return {
        "total_users": db.query(User).count(),
        "total_properties": db.query(Property).count(),
        "pending_advertisements": count_advertisements_by_status(db, "PENDING_REVIEW"),
        "pending_properties": db.query(Property).filter(Property.status == "PENDING_REVIEW").count(),
        "published_properties": db.query(Property).filter(Property.status == "PUBLISHED").count(),
        "open_reports": db.query(PropertyReport).filter(PropertyReport.status == "OPEN").count(),
        "changes_requested_advertisements": count_advertisements_by_status(db, "CHANGES_REQUESTED"),
        "scheduled_advertisements": count_advertisements_by_status(db, "APPROVED"),
        "published_advertisements": count_advertisements_by_status(db, "PUBLISHED"),
        "expired_advertisements": count_advertisements_by_status(db, "EXPIRED"),
        "rejected_advertisements": count_advertisements_by_status(db, "REJECTED"),
    }


def _normalize_admin_ad_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    normalized = status.strip().upper()
    if normalized == "SCHEDULED":
        return "APPROVED"
    return normalized


def search_advertisements_admin(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user_id: Optional[int] = None,
    property_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> tuple[list[Advertisement], int]:
    query = db.query(Advertisement)
    db_status = _normalize_admin_ad_status(status)
    if db_status:
        query = query.filter(Advertisement.status == db_status)
    if user_id is not None:
        query = query.filter(Advertisement.user_id == user_id)
    if property_id is not None:
        query = query.filter(Advertisement.property_id == property_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (Advertisement.title.ilike(term))
            | (Advertisement.location.ilike(term))
            | (Advertisement.description.ilike(term))
        )
    if date_from is not None:
        query = query.filter(Advertisement.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Advertisement.created_at <= date_to)

    total = query.count()
    items = (
        query.order_by(Advertisement.created_at.desc(), Advertisement.display_position.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def list_users_admin(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
    role: Optional[str] = None,
    kyc_status: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list[User], int]:
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if kyc_status:
        query = query.filter(User.kyc_status == kyc_status)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (User.name.ilike(term))
            | (User.email.ilike(term))
            | (User.phone.ilike(term))
        )
    total = query.count()
    items = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def search_properties_admin(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    city: Optional[str] = None,
    owner_id: Optional[int] = None,
    status: Optional[str] = None,
) -> tuple[list[Property], int]:
    query = db.query(Property)
    if status:
        query = query.filter(Property.status == status.strip().upper())
    if city:
        query = query.filter(Property.city.ilike(f"%{city.strip()}%"))
    if owner_id is not None:
        query = query.filter(Property.owner_id == owner_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (Property.locality.ilike(term))
            | (Property.city.ilike(term))
            | (Property.address.ilike(term))
            | (Property.apartment_name.ilike(term))
        )
    total = query.count()
    items = query.order_by(Property.created_at.desc()).offset(skip).limit(limit).all()
    return items, total
