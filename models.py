from sqlalchemy import Column, Integer, String, Float, JSON, DateTime, Boolean, Text, ForeignKey, Date
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

    # eKYC / DigiLocker (Cashfree Secure ID)
    kyc_status = Column(String, nullable=False, default="pending")  # pending | in_progress | verified | failed
    kyc_verification_id = Column(String, nullable=True, index=True)
    kyc_reference_id = Column(Integer, nullable=True)
    kyc_mobile = Column(String, nullable=True)
    kyc_digilocker_id = Column(String, nullable=True)
    kyc_verified_at = Column(DateTime, nullable=True)

    phone = Column(String, nullable=True, unique=True, index=True)

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

    # Commercial (additive nullable — full CommercialDetails split later if volume warrants)
    commercial_subtype = Column(String, nullable=True)  # Shop | Office | Warehouse | Showroom
    frontage_ft = Column(Float, nullable=True)
    floor_number = Column(Integer, nullable=True)
    washroom_count = Column(Integer, nullable=True)

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

    # Favourite Status (legacy global flag — prefer UserFavourite)
    is_favourite = Column(Boolean, default=False, index=True)

    # Moderation lifecycle
    status = Column(String, nullable=False, default="PUBLISHED", index=True)
    admin_notes = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)

    # Document / land verification (independent of publish status)
    title_deed_url = Column(String, nullable=True)
    survey_parcel_number = Column(String, nullable=True)
    encumbrance_certificate_status = Column(String, nullable=True)
    verification_tier = Column(String, nullable=False, default="unverified", index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Property {self.id}: {self.bhk_type} in {self.city}>"


class ProjectDetails(Base):
    """
    Optional 1:1 extension for builder / new-project inventory.

    Presence of a row is the canonical "this is a New Project" signal.
    Resale listings stay on Property alone with no ProjectDetails row.
    Unit availability updates are self-service and do not re-enter
    Property.status moderation.
    """
    __tablename__ = "project_details"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(
        Integer, ForeignKey("properties.id"), unique=True, nullable=False, index=True
    )

    rera_id = Column(String, nullable=True, index=True)
    builder_name = Column(String, nullable=True)
    builder_logo_url = Column(String, nullable=True)

    possession_date = Column(Date, nullable=True)
    launch_date = Column(Date, nullable=True)

    total_units = Column(Integer, nullable=True)
    available_units = Column(Integer, nullable=True)

    # Source of truth going forward; property_age remains for legacy filters
    project_status = Column(String, nullable=True)
    # "New Launch" | "Under Construction" | "Nearing Possession" | "Ready to Move"

    total_towers = Column(Integer, nullable=True)
    total_floors = Column(Integer, nullable=True)

    price_starting_from = Column(Float, nullable=True)
    price_per_sqft_range_min = Column(Float, nullable=True)
    price_per_sqft_range_max = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ProjectDetails property_id={self.property_id} rera={self.rera_id}>"


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


class SupportQuestion(Base):
    """User-submitted support / Q&A ticket (verified users only)."""
    __tablename__ = "support_questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="open")  # open | answered | closed
    admin_reply = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<SupportQuestion {self.id}: user={self.user_id} status={self.status}>"


class SavedSearch(Base):
    """User saved property search — used for match alerts."""
    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    criteria = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SavedSearch {self.id}: user={self.user_id} label={self.label}>"


class Notification(Base):
    """In-app notification for a user."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True, index=True)
    saved_search_id = Column(Integer, ForeignKey("saved_searches.id"), nullable=True)
    payload = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<Notification {self.id}: user={self.user_id} type={self.type} read={self.is_read}>"


class Advertisement(Base):
    """Property/project advertisement with admin review lifecycle."""
    __tablename__ = "advertisements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True, index=True)

    ad_type = Column(String, nullable=False, default="property")  # property | project | general
    title = Column(String, nullable=False)
    location = Column(String, nullable=False)
    property_type = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    price_text = Column(String, nullable=True)
    selling_point = Column(String, nullable=True)
    badge_text = Column(String, nullable=True, default="FEATURED PROJECT")
    button_text = Column(String, nullable=False, default="View Details")
    contact_phone = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)

    banner_url = Column(String, nullable=True)
    banner_public_id = Column(String, nullable=True)

    status = Column(String, nullable=False, default="PENDING_REVIEW", index=True)
    admin_notes = Column(Text, nullable=True)
    created_by_admin = Column(Boolean, default=False)

    display_position = Column(Integer, nullable=False, default=99, index=True)
    show_on_homepage = Column(Boolean, default=True, index=True)
    start_date = Column(DateTime, nullable=True, index=True)
    end_date = Column(DateTime, nullable=True, index=True)

    impressions = Column(Integer, default=0)
    views = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    enquiries = Column(Integer, default=0)

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Advertisement {self.id}: {self.title} status={self.status}>"


class PropertyReviewNote(Base):
    """Historical admin feedback rounds on a property listing."""
    __tablename__ = "property_review_notes"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    note_type = Column(String, nullable=False, index=True)  # reject | changes_requested
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class UserFavourite(Base):
    __tablename__ = "user_favourites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class UserActivity(Base):
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    activity_type = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    location_text = Column(String, nullable=True)
    property_type = Column(String, nullable=True)
    transaction_type = Column(String, nullable=True)
    search_query = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PropertyEnquiry(Base):
    __tablename__ = "property_enquiries"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    contact_method = Column(String, nullable=False, default="phone")
    status = Column(String, nullable=False, default="NEW", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)


class AdvertisementEnquiry(Base):
    __tablename__ = "advertisement_enquiries"

    id = Column(Integer, primary_key=True, index=True)
    advertisement_id = Column(Integer, ForeignKey("advertisements.id"), nullable=False, index=True)
    advertiser_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    contact_method = Column(String, nullable=False, default="phone")
    status = Column(String, nullable=False, default="NEW", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)


class PropertyReport(Base):
    __tablename__ = "property_reports"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reason = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="OPEN", index=True)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Testimonial(Base):
    """Homepage social proof. Featured + approved rows are public."""
    __tablename__ = "testimonials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # Buyer, Owner, First-time buyer
    location = Column(String, nullable=True)
    quote = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False, default=5)
    category = Column(String, nullable=False, default="buyer", index=True)  # buyer | owner | renter
    outcome = Column(String, nullable=True)  # pill: Found a home / Listed a property / …
    avatar_url = Column(String, nullable=True)
    avatar_public_id = Column(String, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    is_featured = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String, nullable=False, default="approved", index=True)  # pending | approved | rejected
    display_order = Column(Integer, nullable=False, default=0, index=True)
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    source_enquiry_id = Column(Integer, nullable=True, index=True)
    source_enquiry_kind = Column(String, nullable=True)  # property | advertisement
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class NewsItem(Base):
    """
    Cached real-estate headlines from a free news API (or curated seed).
    Served from DB on page load — APScheduler refreshes periodically.
    """
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=True, unique=True, index=True)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    source_name = Column(String, nullable=True)
    url = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True, index=True)
    is_approved = Column(Boolean, default=True, index=True)
    category = Column(String, nullable=True, index=True)
    relevance_score = Column(Integer, nullable=False, default=0, index=True)
    provider = Column(String, nullable=True, index=True)  # rss | newsapi | gnews
    fetched_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
