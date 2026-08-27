from pydantic_settings import BaseSettings
from typing import Set


class Settings(BaseSettings):
    """Application configuration settings"""

    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Database Configuration
    DATABASE_URL: str = "sqlite:///./properties.db"

    # Property Image Upload Settings
    MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB per file for properties
    MAX_FILES: int = 20
    ALLOWED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

    # Story Upload Settings (NEW)
    STORY_MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB per file for stories
    STORY_ALLOWED_IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}
    STORY_ALLOWED_VIDEO_EXTENSIONS: Set[str] = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    STORY_EXPIRY_HOURS: int = 24  # Stories expire after 24 hours

    # API Server Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8024

    # CORS Settings (Town Exchange frontend dev server)
    CORS_ORIGINS: list = [
        "http://localhost:5188",
        "http://127.0.0.1:5188",
        "http://localhost:5190",
        "http://127.0.0.1:5190",
    ]

    # API Rate Limiting (Optional)
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60

    # Background Jobs
    CLEANUP_INTERVAL_HOURS: int = 1  # How often to run expired story cleanup

    # Storage Settings
    CLOUDINARY_FOLDER_PROPERTIES: str = "properties"
    CLOUDINARY_FOLDER_STORIES: str = "stories"
    CLOUDINARY_FOLDER_ADS: str = "advertisements"

    # Security Settings (Optional)
    API_KEY_ENABLED: bool = False
    API_KEY: str = ""

    # Auth / JWT Settings
    # NOTE: JWT_SECRET_KEY defaults to a dev-only value — set a real secret via
    # .env before any non-local deployment. Session handling here is
    # intentionally simple (single access token, no refresh rotation) per an
    # explicit "prototype the flow first" scope decision; token expiry is
    # deliberately long-lived for that reason.
    JWT_SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24 * 14

    # Cashfree Secure ID / DigiLocker eKYC
    # Leave CASHFREE_CLIENT_ID empty to use built-in demo mode (no external API calls).
    CASHFREE_CLIENT_ID: str = ""
    CASHFREE_CLIENT_SECRET: str = ""
    CASHFREE_BASE_URL: str = "https://sandbox.cashfree.com/verification"
    KYC_REDIRECT_URL: str = "http://localhost:5188/kyc/callback"
    KYC_MODE: str = ""  # auto | demo | sandbox — empty = auto (demo if no keys)
    # If sandbox calls fail (e.g. IP not whitelisted), fall back to local demo responses.
    KYC_DEV_FALLBACK_DEMO: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()


# Validation function
def validate_file_extension(filename: str, file_type: str = "property") -> bool:
    """
    Validate file extension

    Args:
        filename: Name of the file
        file_type: 'property' or 'story'

    Returns:
        bool: True if valid extension
    """
    import os
    ext = os.path.splitext(filename)[1].lower()

    if file_type == "property":
        return ext in settings.ALLOWED_EXTENSIONS
    elif file_type == "story":
        return (ext in settings.STORY_ALLOWED_IMAGE_EXTENSIONS or
                ext in settings.STORY_ALLOWED_VIDEO_EXTENSIONS)

    return False


def get_max_file_size(file_type: str = "property") -> int:
    """
    Get maximum file size for upload type

    Args:
        file_type: 'property' or 'story'

    Returns:
        int: Maximum file size in bytes
    """
    if file_type == "story":
        return settings.STORY_MAX_FILE_SIZE
    return settings.MAX_FILE_SIZE


def is_video_file(filename: str) -> bool:
    """
    Check if file is a video

    Args:
        filename: Name of the file

    Returns:
        bool: True if video file
    """
    import os
    ext = os.path.splitext(filename)[1].lower()
    return ext in settings.STORY_ALLOWED_VIDEO_EXTENSIONS


def is_image_file(filename: str) -> bool:
    """
    Check if file is an image

    Args:
        filename: Name of the file

    Returns:
        bool: True if image file
    """
    import os
    ext = os.path.splitext(filename)[1].lower()
    return (ext in settings.ALLOWED_EXTENSIONS or
            ext in settings.STORY_ALLOWED_IMAGE_EXTENSIONS)


# Print configuration on import (for debugging)
if __name__ == "__main__":
    print("🔧 Configuration Settings:")
    print(f"   Cloudinary: {settings.CLOUDINARY_CLOUD_NAME}")
    print(f"   Database: {settings.DATABASE_URL}")
    print(f"   Max Property File Size: {settings.MAX_FILE_SIZE / (1024 * 1024):.1f}MB")
    print(f"   Max Story File Size: {settings.STORY_MAX_FILE_SIZE / (1024 * 1024):.1f}MB")
    print(f"   Story Expiry: {settings.STORY_EXPIRY_HOURS} hours")
    print(f"   CORS Origins: {settings.CORS_ORIGINS}")
    print(f"   Property Extensions: {settings.ALLOWED_EXTENSIONS}")
    print(f"   Story Image Extensions: {settings.STORY_ALLOWED_IMAGE_EXTENSIONS}")
    print(f"   Story Video Extensions: {settings.STORY_ALLOWED_VIDEO_EXTENSIONS}")
