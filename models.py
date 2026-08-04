from sqlalchemy import Column, Integer, String, Float, JSON, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime, timedelta

Base = declarative_base()


class User(Base):
    """
    Registered user account.

    Roles are deliberately just three flat strings (not a separate table) —
    matches the "prototype the flow first" scope: enough to route a user to
    the right screen after login, without building out a full permissions
    system yet.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="buyer")  # 'buyer' | 'owner' | 'admin'

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.id}: {self.email} ({self.role})>"


class Property(Base):
    """Property listing model"""
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)

    # Owner (nullable — existing rows and manually-created listings predate
    # accounts, so this can't be required without breaking them)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Basic Information
    property_for = Column(String, nullable=False)
    property_type = Column(String, nullable=False)
    user_type = Column(String, nullable=False)

    # Property Details
    bhk_type = Column(String, nullable=False)
    apartment_type = Column(String, nullable=False)
    apartment_name = Column(String, nullable=True)

    # Location
    locality = Column(String, nullable=False)
    city = Column(String, nullable=False, index=True)
    address = Column(String, nullable=False)

    # Geolocation fields
    latitude = Column(Float, nullable=True, index=True)
    longitude = Column(Float, nullable=True, index=True)

    # Area Details
    built_up_area = Column(Float, nullable=True)
    carpet_area = Column(Float, nullable=False)
    floor = Column(Integer, nullable=False)
    total_floors = Column(Integer, nullable=False)

    # Additional Details
    property_age = Column(String, nullable=False)
    furnishing_status = Column(String, nullable=False)
    parking = Column(Integer, default=0)
    bathrooms = Column(Integer, default=0)
    balconies = Column(Integer, default=0)

    # Pricing
    expected_price = Column(Float, nullable=False, index=True)
    maintenance_charges = Column(Float, nullable=True)
    security_deposit = Column(Float, nullable=True)

    # Availability
    available_from = Column(String, nullable=False)

    # Description & Amenities
    description = Column(String, nullable=True)
    amenities = Column(JSON, nullable=True)

    # Images (stored as JSON array from Cloudinary)
    images = Column(JSON, nullable=True)

    # Favourite Status
    is_favourite = Column(Boolean, default=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Property {self.id}: {self.bhk_type} in {self.city}>"


class Story(Base):
    """
    Story model for temporary 24-hour property stories (Instagram-style)
    Stories automatically expire after 24 hours
    """
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, index=True)

    # User & Property Association
    user_id = Column(String, nullable=True, index=True)  # Optional: link to user who posted
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True, index=True)  # Optional: link to property

    # Media Information
    media_url = Column(String, nullable=False)  # Cloudinary URL
    media_type = Column(String, nullable=False)  # 'image' or 'video'
    public_id = Column(String, nullable=False)  # Cloudinary public_id for deletion
    thumbnail_url = Column(String, nullable=True)  # For video thumbnails

    # Story Metadata
    caption = Column(Text, nullable=True)  # Optional caption/description
    location = Column(String, nullable=True)  # Optional location tag
    views_count = Column(Integer, default=0, index=True)  # Number of views

    # Status
    is_active = Column(Boolean, default=True, index=True)  # Soft delete flag

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)  # Auto-calculated: created_at + 24 hours
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Story {self.id}: {self.media_type} - {self.views_count} views>"

    @property
    def is_expired(self):
        """Check if story has expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def time_remaining(self):
        """Get remaining time in seconds"""
        if self.is_expired:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return int(delta.total_seconds())


class StoryView(Base):
    """
    Track individual story views (optional - for detailed analytics)
    Useful if you want to track who viewed each story
    """
    __tablename__ = "story_views"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False, index=True)
    viewer_id = Column(String, nullable=True, index=True)  # Optional: who viewed it
    viewer_ip = Column(String, nullable=True)  # Track by IP if no user ID
    viewed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<StoryView {self.id}: Story {self.story_id}>"
