"""
File Upload Handler - Manages secure file uploads.
Handles validation, naming, and saving of uploaded files.
"""

import os
import secrets
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image
from flask import current_app
from werkzeug.utils import secure_filename


ALLOWED_UPLOAD_FOLDERS = {'avatars', 'banners', 'blogs', 'projects', 'devlogs', 'messages'}


def _supabase_settings():
    url = (current_app.config.get('SUPABASE_URL') or '').rstrip('/')
    key = current_app.config.get('SUPABASE_KEY')
    bucket = current_app.config.get('UPLOAD_STORAGE_BUCKET', 'uploads')
    return url, key, bucket


def upload_to_supabase(filepath, folder, filename, content_type=None):
    """Mirror a saved upload to Supabase Storage when configured."""
    if folder not in ALLOWED_UPLOAD_FOLDERS or Path(filename).name != filename:
        return False

    supa_url, supa_key, bucket = _supabase_settings()
    if not supa_url or not supa_key:
        return False

    remote_path = f"{folder}/{filename}"
    upload_endpoint = f"{supa_url}/storage/v1/object/{bucket}/{remote_path}"
    headers = {
        'Authorization': f'Bearer {supa_key}',
        'apikey': supa_key,
        'x-upsert': 'true',
    }
    if content_type:
        headers['content-type'] = content_type

    with Path(filepath).open('rb') as file_handle:
        response = requests.post(upload_endpoint, headers=headers, data=file_handle, timeout=45)
    if response.status_code not in (200, 201):
        current_app.logger.info('Supabase upload failed: %s %s', response.status_code, response.text[:200])
        return False
    return True


def delete_from_supabase(folder, filename):
    """Delete a mirrored upload from Supabase Storage when configured."""
    if folder not in ALLOWED_UPLOAD_FOLDERS or Path(filename).name != filename:
        return False

    supa_url, supa_key, bucket = _supabase_settings()
    if not supa_url or not supa_key:
        return False

    endpoint = f"{supa_url}/storage/v1/object/{bucket}"
    headers = {
        'Authorization': f'Bearer {supa_key}',
        'apikey': supa_key,
        'Content-Type': 'application/json',
    }
    response = requests.delete(endpoint, headers=headers, json={"prefixes": [f"{folder}/{filename}"]}, timeout=30)
    if response.status_code not in (200, 204):
        current_app.logger.info('Supabase delete failed: %s %s', response.status_code, response.text[:200])
        return False
    return True


def supabase_public_url(folder, filename):
    if folder not in ALLOWED_UPLOAD_FOLDERS or Path(filename).name != filename:
        return None
    supa_url, _, bucket = _supabase_settings()
    if not supa_url:
        return None
    encoded_path = quote(f"{folder}/{filename}", safe="/")
    return f"{supa_url}/storage/v1/object/public/{bucket}/{encoded_path}"


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
        try:
            upload_to_supabase(filepath, folder, filename, getattr(file, "mimetype", None))
        except Exception:
            current_app.logger.exception('Error uploading to Supabase')

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


def allowed_message_attachment(filename):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('MESSAGE_ATTACHMENT_EXTENSIONS', set())


def _stream_size(file):
    content_length = getattr(file, "content_length", None)
    if content_length:
        return content_length
    stream = getattr(file, "stream", None)
    if not stream or not hasattr(stream, "tell") or not hasattr(stream, "seek"):
        return None
    try:
        current = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current)
        return size
    except Exception:
        return None


def save_message_attachment(file):
    if not file or not file.filename:
        return None, "No file selected."
    if not allowed_message_attachment(file.filename):
        return None, "Unsupported attachment type. Use images, PDF, TXT, or ZIP."

    max_bytes = int(current_app.config.get("MESSAGE_ATTACHMENT_MAX_BYTES", 5 * 1024 * 1024))
    size = _stream_size(file)
    if size is not None and size > max_bytes:
        return None, f"Attachment is too large. Maximum size is {max_bytes // (1024 * 1024)} MB."

    filename = generate_filename(file.filename)
    upload_root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    upload_folder = (upload_root / 'messages').resolve()
    if upload_root not in upload_folder.parents and upload_folder != upload_root:
        return None, "Invalid upload path."
    upload_folder.mkdir(parents=True, exist_ok=True)
    filepath = upload_folder / filename

    try:
        file.save(filepath)
        try:
            upload_to_supabase(filepath, 'messages', filename, getattr(file, "mimetype", None))
        except Exception:
            current_app.logger.exception('Error uploading message attachment to Supabase')
        return {
            "filename": filename,
            "original_name": secure_filename(file.filename)[:255],
            "size": filepath.stat().st_size,
            "mime": (getattr(file, "mimetype", "") or "application/octet-stream")[:120],
        }, None
    except Exception as e:
        current_app.logger.warning("Error saving message attachment: %s", e)
        if filepath.exists():
            filepath.unlink(missing_ok=True)
        return None, "The attachment could not be saved."


def save_media_upload(file, folder='devlogs', max_size=(1400, 1400)):
    """Save an image or short-form video upload for interactive feed surfaces."""
    if not file or file.filename == '' or folder not in ALLOWED_UPLOAD_FOLDERS:
        return None, None
    if not allowed_media_file(file.filename):
        return None, None

    filename = generate_filename(file.filename)
    upload_root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    upload_folder = (upload_root / folder).resolve()
    if upload_root not in upload_folder.parents and upload_folder != upload_root:
        return None
    upload_folder.mkdir(parents=True, exist_ok=True)
    filepath = upload_folder / filename
    media_type = media_type_for(filename)

    try:
        file.save(filepath)
        if media_type == "image":
            validate_image(filepath)
            resize_image(filepath, max_size)
        try:
            upload_to_supabase(filepath, folder, filename, getattr(file, "mimetype", None))
        except Exception:
            current_app.logger.exception('Error uploading media to Supabase')
        return filename, media_type
    except Exception as e:
        current_app.logger.warning("Error saving media upload: %s", e)
        if filepath.exists():
            filepath.unlink(missing_ok=True)
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
        Image.MAX_IMAGE_PIXELS = current_app.config.get("MAX_IMAGE_PIXELS", 24_000_000)
        img = Image.open(filepath)
        
        # Only resize if image is larger than max_size
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(filepath, optimize=True, quality=85)
    except Exception as e:
        current_app.logger.warning("Error resizing image: %s", e)


def validate_image(filepath):
    Image.MAX_IMAGE_PIXELS = current_app.config.get("MAX_IMAGE_PIXELS", 24_000_000)
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
        if Path(filename).name != filename or folder not in ALLOWED_UPLOAD_FOLDERS:
            current_app.logger.warning("Blocked unsafe delete path: %s/%s", folder, filename)
            return
        upload_root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
        filepath = (upload_root / folder / filename).resolve()
        if upload_root not in filepath.parents:
            current_app.logger.warning("Blocked delete outside upload root: %s", filename)
            return
        if filepath.exists():
            filepath.unlink()
        try:
            delete_from_supabase(folder, filename)
        except Exception:
            current_app.logger.exception('Error deleting upload from Supabase')
