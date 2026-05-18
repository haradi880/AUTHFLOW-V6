"""
File Upload Handler - Manages secure file uploads.
Handles validation, naming, and saving of uploaded files.
"""

import os
import secrets
from PIL import Image
from flask import current_app
from werkzeug.utils import secure_filename


ALLOWED_UPLOAD_FOLDERS = {'avatars', 'banners', 'blogs', 'projects', 'devlogs'}


def save_upload(file, folder, max_size=(1200, 1200)):
    """
    Save an uploaded file securely.
    
    Args:
        file: The uploaded file object from request.files
        folder: Subfolder name inside uploads/ (e.g., 'avatars', 'blogs')
        max_size: Maximum image dimensions (width, height)
    
    Returns:
        The generated filename, or None if save failed
    """
    if not file or file.filename == '':
        return None
    
    # Validate file type
    if not allowed_file(file.filename):
        return None
    
    # Generate a secure random filename
    filename = generate_filename(file.filename)
    
    # Get the full save path
    if folder not in ALLOWED_UPLOAD_FOLDERS:
        return None

    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    
    # Save and optionally resize the image
    try:
        file.save(filepath)

        validate_image(filepath)
        resize_image(filepath, max_size)
        
        return filename
    except Exception as e:
        current_app.logger.warning("Error saving upload: %s", e)
        if os.path.exists(filepath):
            os.remove(filepath)
        return None


def allowed_file(filename):
    """
    Check if the file extension is allowed.
    
    Args:
        filename: The name of the file
    
    Returns:
        True if the file extension is allowed, False otherwise
    """
    allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def allowed_media_file(filename):
    """Allow images plus configured short-form video formats for devlog media."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config['ALLOWED_EXTENSIONS'] or ext in current_app.config.get('ALLOWED_VIDEO_EXTENSIONS', set())


def media_type_for(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return "video" if ext in current_app.config.get('ALLOWED_VIDEO_EXTENSIONS', set()) else "image"


def save_media_upload(file, folder='devlogs', max_size=(1400, 1400)):
    """Save an image or short-form video upload for interactive feed surfaces."""
    if not file or file.filename == '' or folder not in ALLOWED_UPLOAD_FOLDERS:
        return None, None
    if not allowed_media_file(file.filename):
        return None, None

    filename = generate_filename(file.filename)
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    media_type = media_type_for(filename)

    try:
        file.save(filepath)
        if media_type == "image":
            validate_image(filepath)
            resize_image(filepath, max_size)
        return filename, media_type
    except Exception as e:
        current_app.logger.warning("Error saving media upload: %s", e)
        if os.path.exists(filepath):
            os.remove(filepath)
        return None, None


def generate_filename(original_filename):
    """
    Generate a unique, secure filename.
    Uses random hex to prevent filename collisions and path manipulation attacks.
    
    Args:
        original_filename: The original filename from the user
    
    Returns:
        A unique secure filename
    """
    # Get the file extension
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
    
    # Create random filename: randomHex_originalName.extension
    random_hex = secrets.token_hex(8)
    safe_name = secure_filename(original_filename.rsplit('.', 1)[0])
    
    return f"{random_hex}_{safe_name}.{ext}"


def resize_image(filepath, max_size):
    """
    Resize an image if it exceeds max dimensions.
    Maintains aspect ratio.
    
    Args:
        filepath: Full path to the image file
        max_size: Tuple of (max_width, max_height)
    """
    try:
        img = Image.open(filepath)
        
        # Only resize if image is larger than max_size
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(filepath, optimize=True, quality=85)
    except Exception as e:
        current_app.logger.warning("Error resizing image: %s", e)


def validate_image(filepath):
    with Image.open(filepath) as img:
        img.verify()


def delete_file(filename, folder):
    """
    Delete a file from the uploads folder.
    
    Args:
        filename: Name of the file to delete
        folder: Subfolder where the file is stored
    """
    if filename and filename not in {'default.jpg', 'default_banner.jpg'}:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], folder, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
