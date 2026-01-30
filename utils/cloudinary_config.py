import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, HTTPException, status
from typing import List
from config import settings
import os

# Configure Cloudinary with credentials
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)


async def upload_image_to_cloudinary(
    image: UploadFile,
    folder: str = "properties"
) -> dict:
    """
    Upload a single image to Cloudinary
    
    Args:
        image: UploadFile object from FastAPI
        folder: Cloudinary folder name
        
    Returns:
        dict: Contains url, public_id, width, height, format
    """
    try:
        # Validate file extension
        file_ext = os.path.splitext(image.filename)[1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {file_ext} not allowed. Allowed types: {settings.ALLOWED_EXTENSIONS}"
            )
        
        # Read file content
        contents = await image.read()
        
        # Validate file size
        if len(contents) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE / (1024*1024):.1f}MB"
            )
        
        # Upload to Cloudinary with transformations
        upload_result = cloudinary.uploader.upload(
            contents,
            folder=folder,
            resource_type="auto",
            transformation=[
                {'quality': 'auto', 'fetch_format': 'auto'},
                {'width': 1200, 'height': 1200, 'crop': 'limit'}
            ]
        )
        
        return {
            "url": upload_result.get("secure_url"),
            "public_id": upload_result.get("public_id"),
            "width": upload_result.get("width"),
            "height": upload_result.get("height"),
            "format": upload_result.get("format")
        }
        
    except cloudinary.exceptions.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cloudinary upload error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading image: {str(e)}"
        )
    finally:
        await image.seek(0)  # Reset file pointer


async def upload_multiple_images(
    images: List[UploadFile],
    folder: str = "properties"
) -> List[dict]:
    """
    Upload multiple images to Cloudinary
    
    Args:
        images: List of UploadFile objects
        folder: Cloudinary folder name
        
    Returns:
        List[dict]: List of uploaded image data
    """
    if len(images) > settings.MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.MAX_FILES} files allowed"
        )
    
    uploaded_images = []
    
    for image in images:
        if image.filename:  # Skip empty file uploads
            try:
                result = await upload_image_to_cloudinary(image, folder)
                uploaded_images.append(result)
            except HTTPException:
                # If one upload fails, delete already uploaded images
                await delete_multiple_images([img["public_id"] for img in uploaded_images])
                raise
    
    return uploaded_images


async def delete_image_from_cloudinary(public_id: str) -> bool:
    """
    Delete a single image from Cloudinary
    
    Args:
        public_id: Cloudinary public ID of the image
        
    Returns:
        bool: True if deleted successfully
    """
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception as e:
        print(f"Error deleting image {public_id}: {str(e)}")
        return False


async def delete_multiple_images(public_ids: List[str]) -> dict:
    """
    Delete multiple images from Cloudinary
    
    Args:
        public_ids: List of Cloudinary public IDs
        
    Returns:
        dict: Statistics of deletion (deleted count, failed count)
    """
    deleted_count = 0
    failed_count = 0
    
    for public_id in public_ids:
        success = await delete_image_from_cloudinary(public_id)
        if success:
            deleted_count += 1
        else:
            failed_count += 1
    
    return {
        "deleted": deleted_count,
        "failed": failed_count
    }
