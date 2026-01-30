from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime


# ========================================
# PROPERTY SCHEMAS
# ========================================

class PropertyResponse(BaseModel):
    """Pydantic schema for Property API responses"""

    # Primary Key
    id: int

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

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # For Pydantic v2
        # orm_mode = True  # Use this for Pydantic v1


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
                "location": "Chennai, Tamil Nadu",
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
