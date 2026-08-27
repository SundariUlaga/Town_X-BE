from pydantic import BaseModel, EmailStr, Field, model_validator, validator
from typing import List, Literal, Optional
from datetime import datetime


# ========================================
# AUTH / USER SCHEMAS
# ========================================

UserRole = Literal["buyer", "owner", "admin"]


class UserSignup(BaseModel):
    """Schema for account creation"""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, description="At least 8 characters")
    role: UserRole = "buyer"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class SendOtpRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15, description="Mobile number")


class SendOtpResponse(BaseModel):
    message: str = "OTP sent successfully"
    phone: str
    is_existing_user: bool = False


class VerifyOtpRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=6, max_length=6)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: UserRole = "buyer"


class UserResponse(BaseModel):
    """Public-facing user shape — never includes password_hash"""
    id: int
    name: str
    email: str
    role: UserRole
    phone: Optional[str] = None
    kyc_status: Literal["pending", "in_progress", "verified", "failed"] = "pending"
    kyc_verified_at: Optional[datetime] = None
    kyc_mobile: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="At least 8 characters")


class SupportQuestionCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)


class SupportQuestionResponse(BaseModel):
    id: int
    subject: str
    message: str
    status: Literal["open", "answered", "closed"]
    admin_reply: Optional[str] = None
    created_at: datetime
    answered_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========================================
# NOTIFICATIONS & SAVED SEARCHES
# ========================================

NotificationType = Literal[
    "search_match",
    "new_property",
    "listing_live",
    "question_answered",
    "ad_submitted",
    "ad_approved",
    "ad_rejected",
    "ad_changes_requested",
    "ad_published",
    "property_approved",
    "property_rejected",
    "property_changes_requested",
    "property_enquiry",
    "property_submitted",
    "ad_expired",
]


class SavedSearchCriteria(BaseModel):
    q: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    property_for: Optional[str] = None
    property_type: Optional[str] = None
    bhk_type: Optional[str] = None
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    category: Optional[str] = None
    furnishing_status: Optional[str] = None


class SavedSearchCreate(BaseModel):
    label: Optional[str] = Field(None, max_length=120)
    criteria: SavedSearchCriteria
    is_active: bool = True


class SavedSearchResponse(BaseModel):
    id: int
    label: str
    criteria: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    id: int
    type: NotificationType
    title: str
    body: str
    property_id: Optional[int] = None
    saved_search_id: Optional[int] = None
    payload: Optional[dict] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


AdStatus = Literal[
    "DRAFT",
    "PENDING_REVIEW",
    "CHANGES_REQUESTED",
    "APPROVED",
    "PUBLISHED",
    "REJECTED",
    "EXPIRED",
]

AdType = Literal["property", "project", "general"]


class AdvertisementResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    property_id: Optional[int] = None
    ad_type: AdType
    title: str
    location: str
    property_type: Optional[str] = None
    description: Optional[str] = None
    price_text: Optional[str] = None
    selling_point: Optional[str] = None
    badge_text: Optional[str] = None
    button_text: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    banner_url: Optional[str] = None
    status: AdStatus
    admin_notes: Optional[str] = None
    created_by_admin: bool = False
    display_position: int
    show_on_homepage: bool
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    impressions: int = 0
    views: int = 0
    clicks: int = 0
    enquiries: int = 0
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    submitter_name: Optional[str] = None

    class Config:
        from_attributes = True


class AdvertisementApproveRequest(BaseModel):
    display_position: int = Field(1, ge=1, le=50)
    start_date: datetime
    end_date: datetime
    show_on_homepage: bool = True


class AdvertisementRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class AdvertisementChangesRequest(BaseModel):
    notes: str = Field(..., min_length=3, max_length=2000)


class AdvertisementTrackRequest(BaseModel):
    event: Literal["impression", "view", "click", "enquiry"]


class AdminDashboardStatsResponse(BaseModel):
    total_users: int
    total_properties: int
    pending_advertisements: int
    pending_properties: int = 0
    published_properties: int = 0
    open_reports: int = 0
    changes_requested_advertisements: int
    scheduled_advertisements: int
    published_advertisements: int
    expired_advertisements: int
    rejected_advertisements: int


class AdminAdvertisementListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AdvertisementResponse]


class AdminUserSummary(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    kyc_status: Literal["pending", "in_progress", "verified", "failed"]
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AdminUserSummary]


class AdminPropertySummary(BaseModel):
    id: int
    property_for: str
    property_type: str
    bhk_type: str
    city: str
    locality: str
    expected_price: float
    status: str = "PUBLISHED"
    verification_tier: str = "unverified"
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminPropertyListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AdminPropertySummary]


class PropertyRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class PropertyChangesRequest(BaseModel):
    notes: str = Field(..., min_length=3, max_length=2000)


class PropertyVerificationUpdateRequest(BaseModel):
    verification_tier: Literal["unverified", "pending", "verified"]
    survey_parcel_number: Optional[str] = Field(None, max_length=100)
    encumbrance_certificate_status: Optional[str] = Field(None, max_length=100)


class PropertyReviewNoteResponse(BaseModel):
    id: int
    property_id: int
    admin_user_id: Optional[int] = None
    admin_name: Optional[str] = None
    note_type: str
    note: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ========================================
# KYC SCHEMAS (Cashfree DigiLocker)
# ========================================

KycStatus = Literal["pending", "in_progress", "verified", "failed"]


class KycVerifyAccountRequest(BaseModel):
    mobile_number: Optional[str] = Field(None, min_length=10, max_length=15)
    aadhaar_number: Optional[str] = Field(None, min_length=12, max_length=12)

    @model_validator(mode="after")
    def require_one_identifier(self):
        if not self.mobile_number and not self.aadhaar_number:
            raise ValueError("Provide mobile_number or aadhaar_number")
        if self.aadhaar_number and not self.aadhaar_number.isdigit():
            raise ValueError("Aadhaar must contain digits only")
        return self


class KycVerifyAccountResponse(BaseModel):
    verification_id: str
    reference_id: Optional[int] = None
    status: str
    mobile_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    digilocker_id: Optional[str] = None
    mode: str


class KycCreateSessionResponse(BaseModel):
    verification_id: str
    reference_id: Optional[int] = None
    url: str
    status: str
    mode: str


class KycStatusResponse(BaseModel):
    kyc_status: KycStatus
    verification_id: Optional[str] = None
    reference_id: Optional[int] = None
    digilocker_status: Optional[str] = None
    mode: str
    message: Optional[str] = None


# ========================================
# PROPERTY SCHEMAS
# ========================================

class PropertyResponse(BaseModel):
    """Pydantic schema for Property API responses"""

    # Primary Key
    id: int
    owner_id: Optional[int] = None

    # Property Basic Info
    property_for: str
    property_type: str
    user_type: str
    bhk_type: str
    apartment_type: str

    # Location Details
    apartment_name: Optional[str] = None
    locality: str
    city: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Property Specifications
    built_up_area: Optional[float] = None
    carpet_area: float
    floor: int
    total_floors: int
    property_age: str
    furnishing_status: str

    # Additional Features
    parking: int = 0
    bathrooms: int = 0
    balconies: int = 0

    # Pricing Details
    expected_price: float
    maintenance_charges: Optional[float] = None
    security_deposit: Optional[float] = None

    # Availability
    available_from: str

    # Description & Amenities
    description: Optional[str] = None
    amenities: List[str] = []

    # Cloudinary Images
    images: List[dict] = []

    # Favourite Status
    is_favourite: bool = False

    # Moderation
    status: str = "PUBLISHED"
    admin_notes: Optional[str] = None
    published_at: Optional[datetime] = None
    review_notes: List["PropertyReviewNoteResponse"] = []

    # Document verification
    title_deed_url: Optional[str] = None
    survey_parcel_number: Optional[str] = None
    encumbrance_certificate_status: Optional[str] = None
    verification_tier: str = "unverified"

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # For Pydantic v2
        # orm_mode = True  # Use this for Pydantic v1


class RecommendationSection(BaseModel):
    key: str
    title: str
    subtitle: Optional[str] = None
    properties: List[PropertyResponse]


class RecommendationsHomeResponse(BaseModel):
    personalized: bool
    fallback: bool
    sections: List[RecommendationSection]


class PropertyCreate(BaseModel):
    """Schema for creating a new property"""
    property_for: str
    property_type: str
    user_type: str
    bhk_type: str
    apartment_type: str
    apartment_name: Optional[str] = None
    locality: str
    city: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    built_up_area: Optional[float] = None
    carpet_area: float
    floor: int
    total_floors: int
    property_age: str
    furnishing_status: str
    parking: int = 0
    bathrooms: int = 0
    balconies: int = 0
    expected_price: float
    maintenance_charges: Optional[float] = None
    security_deposit: Optional[float] = None
    available_from: str
    description: Optional[str] = None
    amenities: List[str] = []


class PropertyUpdate(BaseModel):
    """Schema for updating property (all fields optional)"""
    property_for: Optional[str] = None
    property_type: Optional[str] = None
    bhk_type: Optional[str] = None
    apartment_type: Optional[str] = None
    apartment_name: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    carpet_area: Optional[float] = None
    expected_price: Optional[float] = None
    furnishing_status: Optional[str] = None
    description: Optional[str] = None
    is_favourite: Optional[bool] = None


# ========================================
# STORY SCHEMAS (NEW)
# ========================================

class StoryCreate(BaseModel):
    """Schema for creating a new story"""
    caption: Optional[str] = Field(None, max_length=200, description="Story caption (max 200 characters)")
    location: Optional[str] = Field(None, max_length=100, description="Location tag")
    property_id: Optional[int] = Field(None, description="Link to property (optional)")
    user_id: Optional[str] = Field(None, description="User who created the story")

    class Config:
        json_schema_extra = {
            "example": {
                "caption": "Beautiful 3BHK apartment available!",
                "location": "Your Town, Tamil Nadu",
                "property_id": 1,
                "user_id": "user123"
            }
        }


class StoryResponse(BaseModel):
    """Schema for Story API responses"""
    id: int
    user_id: Optional[str] = None
    property_id: Optional[int] = None

    # Media info
    media_url: str
    media_type: str  # 'image' or 'video'
    public_id: str
    thumbnail_url: Optional[str] = None

    # Story metadata
    caption: Optional[str] = None
    location: Optional[str] = None
    views_count: int

    # Status and timestamps
    is_active: bool
    created_at: datetime
    expires_at: datetime
    updated_at: datetime

    # Computed fields
    is_expired: bool = False
    time_remaining_seconds: int = 0

    class Config:
        from_attributes = True

    @validator('is_expired', always=True)
    def check_if_expired(cls, v, values):
        """Calculate if story is expired"""
        if 'expires_at' in values:
            return datetime.utcnow() > values['expires_at']
        return False

    @validator('time_remaining_seconds', always=True)
    def calculate_time_remaining(cls, v, values):
        """Calculate remaining time in seconds"""
        if 'expires_at' in values and 'is_expired' in values:
            if not values['is_expired']:
                delta = values['expires_at'] - datetime.utcnow()
                return max(0, int(delta.total_seconds()))
        return 0


class StoryWithProperty(StoryResponse):
    """Story response with property details included"""
    property: Optional[PropertyResponse] = None

    class Config:
        from_attributes = True


class StoryStats(BaseModel):
    """Schema for story statistics"""
    total_stories: int
    active_stories: int
    expired_stories: int
    total_views: int
    average_views: float

    class Config:
        json_schema_extra = {
            "example": {
                "total_stories": 150,
                "active_stories": 45,
                "expired_stories": 105,
                "total_views": 12500,
                "average_views": 83.33
            }
        }


class StoryViewCreate(BaseModel):
    """Schema for tracking a story view"""
    story_id: int
    viewer_id: Optional[str] = None
    viewer_ip: Optional[str] = None


class StoryViewResponse(BaseModel):
    """Schema for story view response"""
    id: int
    story_id: int
    viewer_id: Optional[str] = None
    viewer_ip: Optional[str] = None
    viewed_at: datetime

    class Config:
        from_attributes = True


# ========================================
# RESPONSE WRAPPERS
# ========================================

class MessageResponse(BaseModel):
    """Generic success message response"""
    message: str
    status: str = "success"

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Operation completed successfully",
                "status": "success"
            }
        }


class ErrorResponse(BaseModel):
    """Generic error response"""
    detail: str
    status: str = "error"

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Resource not found",
                "status": "error"
            }
        }


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    total: int
    skip: int
    limit: int
    items: List

    class Config:
        json_schema_extra = {
            "example": {
                "total": 100,
                "skip": 0,
                "limit": 20,
                "items": []
            }
        }


# ========================================
# UTILITY SCHEMAS
# ========================================

class CategoryStats(BaseModel):
    """Schema for category statistics"""
    rent_lease: int
    buy: int
    new_projects: int
    ready_to_move: int
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "rent_lease": 45,
                "buy": 30,
                "new_projects": 12,
                "ready_to_move": 18,
                "total": 105
            }
        }


class HealthCheckResponse(BaseModel):
    """Schema for health check endpoint"""
    status: str
    cloudinary_configured: bool
    database: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "cloudinary_configured": True,
                "database": "connected",
                "timestamp": "2025-10-29T12:30:00"
            }
        }


class LocationSearch(BaseModel):
    """Schema for location-based search"""
    latitude: float = Field(..., ge=-90, le=90, description="User latitude")
    longitude: float = Field(..., ge=-180, le=180, description="User longitude")
    radius_km: float = Field(10, ge=1, le=50, description="Search radius in kilometers")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")

    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 13.0827,
                "longitude": 80.2707,
                "radius_km": 10,
                "limit": 20
            }
        }


# ========================================
# BULK OPERATIONS SCHEMAS
# ========================================

class BulkDeleteRequest(BaseModel):
    """Schema for bulk delete operations"""
    ids: List[int] = Field(..., min_items=1, description="List of IDs to delete")

    class Config:
        json_schema_extra = {
            "example": {
                "ids": [1, 2, 3, 4, 5]
            }
        }


class BulkDeleteResponse(BaseModel):
    """Schema for bulk delete response"""
    deleted_count: int
    failed_ids: List[int] = []
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "deleted_count": 5,
                "failed_ids": [],
                "message": "Successfully deleted 5 items"
            }
        }


# ========================================
# LOCATION SCHEMAS (Tamil Nadu — LGD)
# ========================================

class LocationItem(BaseModel):
    """District, taluk, or village entry from LGD-derived data."""
    id: int
    name: str
    code: int
    district_id: Optional[int] = None
    taluk_id: Optional[int] = None
    pincode: Optional[str] = None


class LocationMeta(BaseModel):
    """Metadata about the loaded location dataset."""
    state: str
    state_code: Optional[int] = None
    source: str
    district_count: int
    taluk_count: int
    village_count: int


class LocationSearchResult(BaseModel):
    """Location match from global search."""
    id: int
    name: str
    type: Literal["district", "taluk", "village"]
    label: str
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    taluk_id: Optional[int] = None
    taluk_name: Optional[str] = None
    pincode: Optional[str] = None
