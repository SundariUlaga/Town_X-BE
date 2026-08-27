from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
import os
import logging
from migrate_db import ensure_schema
from models import Property, Story, User
from database import get_db
from schemas import (
    PropertyResponse,
    StoryCreate,
    StoryResponse,
    StoryStats,
    MessageResponse,
    CategoryStats,
    UserSignup,
    UserLogin,
    UserResponse,
    TokenResponse,
    SendOtpRequest,
    SendOtpResponse,
    VerifyOtpRequest,
)
from utils.cloudinary_config import upload_multiple_images, delete_multiple_images
from config import settings, validate_file_extension, get_max_file_size, is_video_file
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_optional_current_user,
    require_kyc_verified,
)
from app.api.locations import router as locations_router
from app.api.kyc import router as kyc_router
from app.api.account import router as account_router
from app.api.notifications import router as notifications_router
from app.api.advertisements import router as advertisements_router
from app.api.admin import router as admin_router
from app.api.activity import router as activity_router
from app.api.recommendations import router as recommendations_router
from app.api.enquiries import router as enquiries_router
from app.api.reports import router as reports_router
from services.phone_otp import DEMO_OTP, default_display_name, normalize_phone, phone_email, unusable_password_hash
from services.property_serialize import serialize_property
import crud

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sync tables + additive column patches (SQLite won't add columns via create_all alone)
ensure_schema()

# Initialize FastAPI app
app = FastAPI(
    title="Town Exchange - Property Listing API",
    description="Real estate property listing API with cloud-based image uploads and Instagram-style stories",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "Town Exchange Support",
        "email": "support@townexchange.com"
    },
    license_info={
        "name": "MIT License",
    }
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(locations_router)
app.include_router(kyc_router)
app.include_router(account_router)
app.include_router(notifications_router)
app.include_router(advertisements_router)
app.include_router(admin_router)
app.include_router(activity_router)
app.include_router(recommendations_router)
app.include_router(enquiries_router)
app.include_router(reports_router)


# ========================================
# STARTUP & SHUTDOWN EVENTS
# ========================================

@app.on_event("startup")
async def startup_event():
    """Run on app startup - Initialize background tasks"""
    logger.info("🚀 Starting Town Exchange API...")

    try:
        from services.cashfree_kyc import effective_kyc_mode, resolve_kyc_mode

        kyc_mode = resolve_kyc_mode()
        logger.info(
            "KYC configured — mode=%s effective=%s redirect=%s",
            kyc_mode,
            effective_kyc_mode(),
            settings.KYC_REDIRECT_URL,
        )
    except Exception as e:
        logger.warning("KYC startup check skipped: %s", e)

    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        def cleanup_expired_stories_job():
            """Background job to delete expired stories"""
            db = next(get_db())
            try:
                deleted_count = crud.delete_expired_stories(db)
                if deleted_count > 0:
                    logger.info(f"✅ Cleaned up {deleted_count} expired stories")
            except Exception as e:
                logger.error(f"❌ Error in cleanup job: {e}")
            finally:
                db.close()

        def refresh_advertisement_statuses_job():
            db = next(get_db())
            try:
                changed = crud.refresh_advertisement_statuses(db)
                if changed > 0:
                    logger.info("✅ Refreshed %s advertisement status(es)", changed)
            except Exception as e:
                logger.error("❌ Error refreshing advertisement statuses: %s", e)
            finally:
                db.close()

        # Start scheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            cleanup_expired_stories_job,
            'interval',
            hours=settings.CLEANUP_INTERVAL_HOURS
        )
        scheduler.add_job(
            refresh_advertisement_statuses_job,
            'interval',
            hours=1,
        )
        scheduler.start()
        logger.info(
            f"✅ Background scheduler started - cleaning expired stories every {settings.CLEANUP_INTERVAL_HOURS} hour(s)")

        # Store scheduler in app state for shutdown
        app.state.scheduler = scheduler

    except Exception as e:
        logger.error(f"❌ Failed to start background scheduler: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on app shutdown"""
    logger.info("🛑 Shutting down Town Exchange API...")

    # Stop scheduler
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()
        logger.info("✅ Background scheduler stopped")


# ========================================
# ROOT & HEALTH ENDPOINTS
# ========================================

@app.get("/")
async def root():
    """Root endpoint - API status"""
    return {
        "message": "Town Exchange - Property Listing API with Stories",
        "status": "running",
        "version": "2.0.0",
        "documentation": "/docs",
        "features": [
            "Property Listings",
            "Instagram-style Stories (24h expiry)",
            "Location-based Search",
            "Favorites",
            "Image Upload via Cloudinary"
        ],
        "endpoints": {
            "properties": "/api/properties",
            "stories": "/api/stories",
            "config": "/api/landing-config",
            "locations": "/api/locations/districts",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database verification"""
    try:
        # Test database connection
        property_count = crud.get_properties_count(db)
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "disconnected"
        property_count = 0

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "cloudinary_configured": bool(settings.CLOUDINARY_CLOUD_NAME),
        "database": db_status,
        "property_count": property_count,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }


# ========================================
# AUTH ENDPOINTS
# ========================================

@app.post("/api/auth/signup", response_model=TokenResponse, status_code=201)
async def signup_endpoint(payload: UserSignup, db: Session = Depends(get_db)):
    """Create an account and return a session token"""
    existing = crud.get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = crud.create_user(
        db,
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    token = create_access_token(user)
    logger.info(f"✅ Signup successful - {user.email} ({user.role})")
    return TokenResponse(access_token=token, user=user)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login_endpoint(payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and return a session token"""
    user = crud.get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(user)
    logger.info(f"✅ Login successful - {user.email} ({user.role})")
    return TokenResponse(access_token=token, user=user)


@app.post("/api/auth/send-otp", response_model=SendOtpResponse)
async def send_otp_endpoint(payload: SendOtpRequest, db: Session = Depends(get_db)):
    """Send OTP to mobile (prototype: always succeeds, use 000000 to verify)."""
    phone = normalize_phone(payload.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit mobile number")
    existing = crud.get_user_by_phone(db, phone) is not None
    logger.info(
        "OTP requested for phone ending %s (demo OTP: %s, existing=%s)",
        phone[-4:],
        DEMO_OTP,
        existing,
    )
    return SendOtpResponse(phone=phone, is_existing_user=existing)


@app.post("/api/auth/verify-otp", response_model=TokenResponse)
async def verify_otp_endpoint(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    """Verify OTP and sign in — creates account automatically if phone is new."""
    phone = normalize_phone(payload.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit mobile number")
    if payload.otp.strip() != DEMO_OTP:
        raise HTTPException(status_code=401, detail="Invalid OTP. Use 000000 for demo.")

    user = crud.get_user_by_phone(db, phone)
    if user:
        token = create_access_token(user)
        logger.info("✅ OTP login - %s (%s)", phone, user.role)
        return TokenResponse(access_token=token, user=user)

    name = (payload.name or "").strip()
    if len(name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Enter your full name to create a new account",
        )
    email = phone_email(phone)
    if crud.get_user_by_email(db, email):
        raise HTTPException(status_code=400, detail="Unable to create account for this number")

    user = crud.create_user(
        db,
        name=name,
        email=email,
        password_hash=unusable_password_hash(),
        role=payload.role,
        phone=phone,
    )
    token = create_access_token(user)
    logger.info("✅ OTP signup - %s (%s)", phone, user.role)
    return TokenResponse(access_token=token, user=user)


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me_endpoint(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user"""
    return current_user


# ========================================
# LANDING PAGE CONFIGURATION ENDPOINTS
# ========================================

@app.get("/api/landing-config")
async def get_landing_config():
    """Get landing page configuration"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'landingPageConfig.json')

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info("✅ Landing config loaded from file")
            return config
        else:
            logger.warning("⚠️ Landing config file not found, using default")
            # Default configuration
            default_config = {
                "title": "Town Exchange",
                "location": "Your Town",
                "header": {
                    "logo": {
                        "icon": "Home",
                        "title": "Town Exchange",
                        "subtitle": "📍 Your Town"
                    },
                    "postButton": {
                        "text": "Create Post",
                        "mobileText": "Post",
                        "actionUrl": "/create-post",
                        "color": "#7C01A2",
                        "hoverColor": "#5D1578"
                    }
                },
                "searchSection": {
                    "enabled": True,
                    "placeholder": "Search properties, locations...",
                    "defaultRadius": 5,
                    "maxRadius": 50,
                    "userLocation": {
                        "latitude": 13.094579,
                        "longitude": 80.183212
                    }
                },
                "featuredSection": {
                    "enabled": True,
                    "title": "Featured Properties",
                    "subtitle": "Explore trending listings",
                    "stories": []
                },
                "categories": {
                    "title": "Browse by Category",
                    "subtitle": "Choose your property type",
                    "items": [
                        {
                            "id": 1,
                            "name": "Rent/Lease",
                            "icon": "Key",
                            "color": "purple",
                            "description": "Find rental homes",
                            "actionUrl": "/category/rent-lease",
                            "categoryFilter": "Rent/Lease"
                        },
                        {
                            "id": 2,
                            "name": "Buy Property",
                            "icon": "Building2",
                            "color": "blue",
                            "description": "Own your dream",
                            "actionUrl": "/category/buy",
                            "categoryFilter": "Buy Land/Homes"
                        }
                    ]
                },
                "favouritesSection": {
                    "enabled": True,
                    "title": "View Favourites",
                    "subtitle": "See all your saved properties",
                    "icon": "Heart",
                    "actionUrl": "/favourites"
                }
            }
            return default_config

    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in config file: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid JSON in config file: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Error loading landing config: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading landing page config: {str(e)}")


@app.put("/api/landing-config")
async def update_landing_config(config: dict):
    """Update landing page configuration (admin endpoint)"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'landingPageConfig.json')
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info("✅ Landing config updated successfully")

        return {
            "message": "Landing page configuration updated successfully",
            "status": "success",
            "config": config
        }
    except Exception as e:
        logger.error(f"❌ Error updating landing config: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating landing page config: {str(e)}")


# ========================================
# STORY ENDPOINTS (NEW)
# ========================================

@app.post("/api/stories", response_model=StoryResponse, status_code=201)
async def create_story_endpoint(
        caption: Optional[str] = Form(None, max_length=200),
        location: Optional[str] = Form(None, max_length=100),
        property_id: Optional[int] = Form(None),
        user_id: Optional[str] = Form(None),
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """
    Create a new story (24-hour temporary post)

    - **file**: Image or video file
    - **caption**: Optional caption (max 200 characters)
    - **location**: Optional location tag
    - **property_id**: Optional link to property
    - **user_id**: Optional user identifier
    """
    try:
        logger.info(f"📸 Creating new story - File: {file.filename}, Type: {file.content_type}")

        # Validate file extension using config
        if not validate_file_extension(file.filename, file_type="story"):
            allowed_exts = settings.STORY_ALLOWED_IMAGE_EXTENSIONS.union(
                settings.STORY_ALLOWED_VIDEO_EXTENSIONS
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(sorted(allowed_exts))}"
            )

        # Validate file size
        max_size = get_max_file_size(file_type="story")
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        for chunk in iter(lambda: file.file.read(chunk_size), b''):
            file_size += len(chunk)
            if file_size > max_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File size must be less than {max_size / (1024 * 1024):.0f}MB"
                )
        file.file.seek(0)  # Reset file pointer

        logger.info(f"✅ File validation passed - Size: {file_size / (1024 * 1024):.2f}MB")

        # Determine media type
        media_type = "video" if is_video_file(file.filename) else "image"

        # Upload to Cloudinary
        logger.info(f"☁️ Uploading {media_type} to Cloudinary...")
        uploaded_media = await upload_multiple_images(
            [file],
            folder=settings.CLOUDINARY_FOLDER_STORIES
        )

        if not uploaded_media:
            raise HTTPException(status_code=500, detail="Failed to upload media to Cloudinary")

        logger.info(f"✅ Media uploaded successfully - URL: {uploaded_media[0]['url']}")

        media_info = {
            "url": uploaded_media[0]["url"],
            "type": media_type,
            "public_id": uploaded_media[0]["public_id"],
            "thumbnail_url": uploaded_media[0].get("thumbnail_url")
        }

        story_data = {
            "caption": caption,
            "location": location,
            "property_id": property_id,
            "user_id": user_id
        }

        new_story = crud.create_story(db, story_data, media_info)
        logger.info(f"✅ Story created successfully - ID: {new_story.id}")

        return new_story

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating story: {e}")
        # Clean up uploaded file if story creation fails
        if 'uploaded_media' in locals():
            try:
                await delete_multiple_images([uploaded_media[0]["public_id"]])
                logger.info("🗑️ Cleaned up orphaned media from Cloudinary")
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Error creating story: {str(e)}")


@app.get("/api/stories", response_model=List[StoryResponse])
async def get_stories_endpoint(
        limit: int = Query(50, ge=1, le=100, description="Maximum number of stories to return"),
        user_id: Optional[str] = Query(None, description="Filter by user ID"),
        property_id: Optional[int] = Query(None, description="Filter by property ID"),
        db: Session = Depends(get_db)
):
    """
    Get all active stories

    - Stories are automatically filtered to show only non-expired ones
    - Sorted by creation date (newest first)
    """
    if user_id:
        stories = crud.get_user_stories(db, user_id)
        logger.info(f"📖 Retrieved {len(stories)} stories for user: {user_id}")
    elif property_id:
        stories = crud.get_property_stories(db, property_id)
        logger.info(f"📖 Retrieved {len(stories)} stories for property: {property_id}")
    else:
        stories = crud.get_active_stories(db, limit)
        logger.info(f"📖 Retrieved {len(stories)} active stories")

    return stories


@app.get("/api/stories/trending", response_model=List[StoryResponse])
async def get_trending_stories_endpoint(
        limit: int = Query(10, ge=1, le=50),
        db: Session = Depends(get_db)
):
    """Get trending stories (most viewed)"""
    trending = crud.get_trending_stories(db, limit)
    logger.info(f"🔥 Retrieved {len(trending)} trending stories")
    return trending


@app.get("/api/stories/stats", response_model=StoryStats)
async def get_story_stats_endpoint(db: Session = Depends(get_db)):
    """Get story statistics"""
    stats = crud.get_story_stats(db)
    logger.info(f"📊 Story stats - Active: {stats['active_stories']}, Total: {stats['total_stories']}")
    return stats


@app.get("/api/stories/{story_id}", response_model=StoryResponse)
async def get_story_endpoint(
        story_id: int,
        request: Request,
        viewer_id: Optional[str] = Query(None),
        db: Session = Depends(get_db)
):
    """
    Get a specific story and increment view count

    - Automatically increments view count
    - Optionally tracks viewer information
    """
    story = crud.get_story_by_id(db, story_id)

    if not story or not story.is_active:
        raise HTTPException(status_code=404, detail="Story not found or expired")

    # Get viewer IP
    viewer_ip = request.client.host

    # Increment view count
    crud.increment_story_views(db, story_id, viewer_id=viewer_id, viewer_ip=viewer_ip)

    # Refresh to get updated view count
    db.refresh(story)

    logger.info(f"👁️ Story {story_id} viewed - Total views: {story.views_count}")

    return story


@app.delete("/api/stories/{story_id}")
async def delete_story_endpoint(
        story_id: int,
        db: Session = Depends(get_db)
):
    """Delete a story (soft delete)"""
    story = crud.get_story_by_id(db, story_id)

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Delete from Cloudinary
    if story.public_id:
        try:
            await delete_multiple_images([story.public_id])
            logger.info(f"✅ Deleted story media from Cloudinary: {story.public_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting story media: {e}")

    # Soft delete from database
    crud.delete_story(db, story_id)
    logger.info(f"🗑️ Story {story_id} deleted successfully")

    return {
        "message": "Story deleted successfully",
        "story_id": story_id,
        "status": "success"
    }


@app.post("/api/stories/cleanup")
async def cleanup_expired_stories_endpoint(db: Session = Depends(get_db)):
    """
    Manually trigger cleanup of expired stories
    (Usually runs automatically via background job)
    """
    logger.info("🧹 Manual cleanup triggered")
    deleted_count = crud.delete_expired_stories(db)
    logger.info(f"✅ Cleaned up {deleted_count} expired stories")

    return {
        "message": "Expired stories cleaned up",
        "deleted_count": deleted_count,
        "status": "success"
    }


# ========================================
# PROPERTY ENDPOINTS
# ========================================

@app.post("/api/properties", response_model=PropertyResponse, status_code=201)
async def create_property_endpoint(
        property_for: str = Form(..., alias="propertyFor"),
        property_type: str = Form(..., alias="propertyType"),
        user_type: str = Form(..., alias="userType"),
        bhk_type: str = Form(..., alias="bhkType"),
        apartment_type: str = Form(..., alias="apartmentType"),
        apartment_name: Optional[str] = Form(None, alias="apartmentName"),
        locality: str = Form(...),
        city: str = Form(...),
        address: str = Form(...),
        latitude: Optional[float] = Form(None),
        longitude: Optional[float] = Form(None),
        built_up_area: Optional[float] = Form(None, alias="builtUpArea"),
        carpet_area: float = Form(..., alias="carpetArea"),
        floor: int = Form(...),
        total_floors: int = Form(..., alias="totalFloors"),
        property_age: str = Form(..., alias="propertyAge"),
        furnishing_status: str = Form(..., alias="furnishingStatus"),
        parking: int = Form(0),
        bathrooms: int = Form(0),
        balconies: int = Form(0),
        expected_price: float = Form(..., alias="expectedPrice"),
        maintenance_charges: Optional[float] = Form(None, alias="maintenanceCharges"),
        security_deposit: Optional[float] = Form(None, alias="securityDeposit"),
        available_from: str = Form(..., alias="availableFrom"),
        description: Optional[str] = Form(None),
        amenities: str = Form("[]"),
        files: List[UploadFile] = File([]),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_kyc_verified),
):
    """Create a new property listing — requires KYC-verified user; enters moderation queue."""
    try:
        logger.info(f"🏠 Creating new property in {city}")

        amenities_list = json.loads(amenities)

        valid_files = [f for f in files if f.filename]
        if len(valid_files) < 1:
            raise HTTPException(status_code=400, detail="At least 1 property image is required")

        logger.info(f"☁️ Uploading {len(valid_files)} property images...")
        uploaded_images = await upload_multiple_images(
            valid_files,
            folder=settings.CLOUDINARY_FOLDER_PROPERTIES
        )

        property_data = {
            "owner_id": current_user.id,
            "status": "PENDING_REVIEW",
            "property_for": property_for,
            "property_type": property_type,
            "user_type": user_type,
            "bhk_type": bhk_type,
            "apartment_type": apartment_type,
            "apartment_name": apartment_name,
            "locality": locality,
            "city": city,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "built_up_area": built_up_area,
            "carpet_area": carpet_area,
            "floor": floor,
            "total_floors": total_floors,
            "property_age": property_age,
            "furnishing_status": furnishing_status,
            "parking": parking,
            "bathrooms": bathrooms,
            "balconies": balconies,
            "expected_price": expected_price,
            "maintenance_charges": maintenance_charges,
            "security_deposit": security_deposit,
            "available_from": available_from,
            "description": description,
            "amenities": amenities_list,
        }

        new_property = crud.create_property(db, property_data, uploaded_images)
        logger.info(f"✅ Property created successfully - ID: {new_property.id}")

        if new_property.owner_id:
            crud.create_notification(
                db,
                user_id=new_property.owner_id,
                type="property_submitted",
                title="Property submitted for review",
                body=f"Your listing in {new_property.locality}, {new_property.city} is pending admin approval.",
                property_id=new_property.id,
                payload={"path": "/owner/dashboard", "property_id": new_property.id},
            )

        return serialize_property(db, new_property, current_user.id)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid amenities JSON format")
    except Exception as e:
        logger.error(f"❌ Error creating property: {e}")
        db.rollback()
        if 'uploaded_images' in locals():
            public_ids = [img["public_id"] for img in uploaded_images]
            await delete_multiple_images(public_ids)
        raise HTTPException(status_code=500, detail=f"Error creating property: {str(e)}")


@app.get("/api/properties", response_model=List[PropertyResponse])
async def get_properties_endpoint(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(20, ge=1, le=100, description="Maximum records to return"),
        city: Optional[str] = Query(None, description="Filter by city"),
        property_for: Optional[str] = Query(None, description="Filter by purpose (Rent/Sell/PG)"),
        property_type: Optional[str] = Query(None, description="Filter by type (Residential/Commercial)"),
        bhk_type: Optional[str] = Query(None, description="Filter by BHK type"),
        min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
        max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
        category: Optional[str] = Query(None, description="Filter by category"),
        furnishing_status: Optional[str] = Query(None, description="Filter by furnishing status"),
        db: Session = Depends(get_db)
):
    """Get all property listings with optional filters"""
    properties = crud.get_properties(
        db=db, skip=skip, limit=limit, city=city, property_for=property_for,
        property_type=property_type,
        bhk_type=bhk_type, min_price=min_price, max_price=max_price,
        category=category, furnishing_status=furnishing_status
    )
    logger.info(f"📋 Retrieved {len(properties)} properties")
    return properties


@app.get("/api/properties/search", response_model=List[PropertyResponse])
async def search_properties_endpoint(
        q: str = Query(..., min_length=2, description="Search query"),
        limit: int = Query(20, ge=1, le=100),
        db: Session = Depends(get_db)
):
    """Search properties by city, locality, or apartment name"""
    results = crud.search_properties(db, q, limit)
    logger.info(f"🔍 Search '{q}' returned {len(results)} results")
    return results


@app.get("/api/properties/nearby", response_model=List[PropertyResponse])
async def get_nearby_properties_endpoint(
        latitude: float = Query(..., description="User's latitude"),
        longitude: float = Query(..., description="User's longitude"),
        radius: float = Query(10, ge=1, le=50, description="Search radius in kilometers"),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        db: Session = Depends(get_db)
):
    """Get properties near a location within specified radius"""
    properties = crud.get_properties_by_location(
        db=db, user_lat=latitude, user_lon=longitude,
        radius_km=radius, skip=skip, limit=limit
    )
    logger.info(f"📍 Found {len(properties)} properties within {radius}km")
    return properties


@app.get("/api/properties/mine", response_model=List[PropertyResponse])
async def get_my_properties_endpoint(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Get properties listed by the logged-in user — powers the owner dashboard"""
    properties = crud.get_properties_by_owner(db, current_user.id, skip, limit)
    logger.info(f"🏠 Retrieved {len(properties)} properties for owner {current_user.id}")
    return [serialize_property(db, prop, current_user.id) for prop in properties]


@app.get("/api/properties/{property_id}", response_model=PropertyResponse)
async def get_property_endpoint(
        property_id: int,
        db: Session = Depends(get_db),
        current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Get a specific property by ID"""
    property_data = crud.get_property_by_id(db, property_id)
    if not property_data:
        raise HTTPException(status_code=404, detail=f"Property with ID {property_id} not found")
    if property_data.status != "PUBLISHED":
        if not current_user or (
            current_user.role != "admin" and property_data.owner_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail=f"Property with ID {property_id} not found")

    if current_user and current_user.kyc_status == "verified" and property_data.status == "PUBLISHED":
        from services.activity import record_property_view

        record_property_view(db, current_user, property_data)

    return serialize_property(db, property_data, current_user.id if current_user else None)


@app.patch("/api/properties/{property_id}", response_model=PropertyResponse)
async def update_property_endpoint(
        property_id: int,
        property_for: str = Form(..., alias="propertyFor"),
        property_type: str = Form(..., alias="propertyType"),
        user_type: str = Form(..., alias="userType"),
        bhk_type: str = Form(..., alias="bhkType"),
        apartment_type: str = Form(..., alias="apartmentType"),
        apartment_name: Optional[str] = Form(None, alias="apartmentName"),
        locality: str = Form(...),
        city: str = Form(...),
        address: str = Form(...),
        latitude: Optional[float] = Form(None),
        longitude: Optional[float] = Form(None),
        built_up_area: Optional[float] = Form(None, alias="builtUpArea"),
        carpet_area: float = Form(..., alias="carpetArea"),
        floor: int = Form(...),
        total_floors: int = Form(..., alias="totalFloors"),
        property_age: str = Form(..., alias="propertyAge"),
        furnishing_status: str = Form(..., alias="furnishingStatus"),
        parking: int = Form(0),
        bathrooms: int = Form(0),
        balconies: int = Form(0),
        expected_price: float = Form(..., alias="expectedPrice"),
        maintenance_charges: Optional[float] = Form(None, alias="maintenanceCharges"),
        security_deposit: Optional[float] = Form(None, alias="securityDeposit"),
        available_from: str = Form(..., alias="availableFrom"),
        description: Optional[str] = Form(None),
        amenities: str = Form("[]"),
        files: List[UploadFile] = File([]),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_kyc_verified),
):
    """Owner updates a listing and resubmits for moderation."""
    prop = crud.get_property_by_id(db, property_id)
    if not prop or prop.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Property not found")
    if prop.status not in ("CHANGES_REQUESTED", "REJECTED"):
        raise HTTPException(
            status_code=400,
            detail=f"Only listings awaiting changes can be edited (current status: {prop.status})",
        )

    try:
        amenities_list = json.loads(amenities)
        valid_files = [f for f in files if f.filename]
        uploaded_images = list(prop.images or [])

        if valid_files:
            new_uploads = await upload_multiple_images(
                valid_files,
                folder=settings.CLOUDINARY_FOLDER_PROPERTIES,
            )
            uploaded_images = new_uploads

        if len(uploaded_images) < 1:
            raise HTTPException(status_code=400, detail="At least 1 property image is required")

        update_data = {
            "property_for": property_for,
            "property_type": property_type,
            "user_type": user_type,
            "bhk_type": bhk_type,
            "apartment_type": apartment_type,
            "apartment_name": apartment_name,
            "locality": locality,
            "city": city,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "built_up_area": built_up_area,
            "carpet_area": carpet_area,
            "floor": floor,
            "total_floors": total_floors,
            "property_age": property_age,
            "furnishing_status": furnishing_status,
            "parking": parking,
            "bathrooms": bathrooms,
            "balconies": balconies,
            "expected_price": expected_price,
            "maintenance_charges": maintenance_charges,
            "security_deposit": security_deposit,
            "available_from": available_from,
            "description": description,
            "amenities": amenities_list,
            "images": uploaded_images,
            "status": "PENDING_REVIEW",
            "admin_notes": None,
        }

        updated = crud.update_property(db, property_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Property not found")

        crud.create_notification(
            db,
            user_id=current_user.id,
            type="property_resubmitted",
            title="Listing resubmitted",
            body=f"Your updated listing in {updated.locality}, {updated.city} is pending admin review.",
            property_id=updated.id,
            payload={"path": "/owner/dashboard", "property_id": updated.id},
        )

        return serialize_property(db, updated, current_user.id)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid amenities JSON format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating property: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating property: {str(e)}")


@app.delete("/api/properties/{property_id}")
async def delete_property_endpoint(property_id: int, db: Session = Depends(get_db)):
    """Delete a property and its images from Cloudinary"""
    property_data = crud.get_property_by_id(db, property_id)
    if not property_data:
        raise HTTPException(status_code=404, detail=f"Property with ID {property_id} not found")

    if property_data.images:
        public_ids = [img["public_id"] for img in property_data.images]
        deletion_result = await delete_multiple_images(public_ids)
        logger.info(f"🗑️ Deleted {deletion_result['deleted']} images from Cloudinary")

    crud.delete_property(db, property_id)
    logger.info(f"✅ Property {property_id} deleted successfully")

    return {"message": "Property deleted successfully", "property_id": property_id}


# ========================================
# STATISTICS ENDPOINTS
# ========================================

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get overall statistics"""
    total_properties = crud.get_properties_count(db)
    story_stats = crud.get_story_stats(db)

    return {
        "properties": {
            "total": total_properties
        },
        "stories": story_stats,
        "status": "success",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/categories/stats")
async def get_category_stats_endpoint(db: Session = Depends(get_db)):
    """Get statistics for each property category"""
    counts = crud.get_category_counts(db)
    return {
        "categories": {
            "Rent/Lease": counts["rent_lease"],
            "Buy Land/Homes": counts["buy"],
            "New Project": counts["new_projects"],
            "Ready To Move/Resale": counts["ready_to_move"]
        },
        "total": sum(counts.values()),
        "status": "success"
    }


# ========================================
# FAVOURITE ENDPOINTS
# ========================================

@app.post("/api/properties/{property_id}/favourite")
async def toggle_favourite_endpoint(
        property_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_kyc_verified),
):
    """Toggle favourite for the current user"""
    is_favourite, property_data = crud.toggle_user_favourite(db, current_user.id, property_id)
    if not property_data:
        raise HTTPException(status_code=404, detail=f"Property with ID {property_id} not found")

    from services.activity import record_activity

    record_activity(
        db,
        current_user,
        activity_type="FAVOURITE" if is_favourite else "UNFAVOURITE",
        entity_type="property",
        entity_id=property_id,
    )

    return {
        "message": "Favourite status updated",
        "property_id": property_id,
        "is_favourite": is_favourite,
    }


@app.get("/api/favourites", response_model=List[PropertyResponse])
async def get_favourites_endpoint(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_kyc_verified),
):
    """Get favourite properties for the current user"""
    favourites = crud.get_user_favourite_properties(db, current_user.id, skip, limit)
    logger.info(f"❤️ Retrieved {len(favourites)} favourite properties for user {current_user.id}")
    return favourites


@app.get("/api/favourites/count")
async def get_favourites_count_endpoint(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_kyc_verified),
):
    """Get count of favourite properties for the current user"""
    count = crud.get_user_favourites_count(db, current_user.id)
    return {"count": count, "status": "success"}


# ========================================
# RUN SERVER
# ========================================

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Starting Town Exchange API Server...")
    logger.info(f"📍 Server will be available at: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"📚 API Documentation: http://{settings.API_HOST}:{settings.API_PORT}/docs")

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level="info"
    )
