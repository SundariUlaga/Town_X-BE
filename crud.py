import math
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Property, Story, StoryView
from typing import List, Optional

# Setup logging
logger = logging.getLogger(__name__)


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
        bhk_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        category: Optional[str] = None,
        furnishing_status: Optional[str] = None,
        favourites_only: bool = False
) -> List[Property]:
    """Get all properties with optional filters"""
    query = db.query(Property)

    # Filter favourites
    if favourites_only:
        query = query.filter(Property.is_favourite == True)

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


# ========================================
# FAVOURITE FUNCTIONS
# ========================================

def toggle_favourite(db: Session, property_id: int) -> Optional[Property]:
    """Toggle favourite status of a property"""
    property_data = get_property_by_id(db, property_id)

    if property_data:
        property_data.is_favourite = not property_data.is_favourite
        db.commit()
        db.refresh(property_data)
        logger.info(f"❤️ Property {property_id} favourite: {property_data.is_favourite}")

    return property_data


def get_favourite_properties(db: Session, skip: int = 0, limit: int = 100) -> List[Property]:
    """Get all favourite properties"""
    return db.query(Property).filter(
        Property.is_favourite == True
    ).order_by(Property.created_at.desc()).offset(skip).limit(limit).all()


def get_favourites_count(db: Session) -> int:
    """Get count of favourite properties"""
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
