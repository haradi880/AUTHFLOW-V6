"""
File Upload Handler - Manages secure file uploads.
Handles validation, naming, and saving of uploaded files.
"""

import os
import secrets
import shlex
import subprocess  # nosec B404
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image
from flask import current_app, url_for
from werkzeug.utils import secure_filename


PUBLIC_UPLOAD_FOLDERS = {'avatars', 'banners', 'blogs', 'projects', 'devlogs'}
PRIVATE_UPLOAD_FOLDERS = {'messages'}
ALLOWED_UPLOAD_FOLDERS = PUBLIC_UPLOAD_FOLDERS | PRIVATE_UPLOAD_FOLDERS
IMAGE_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}
MESSAGE_MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "zip": "application/zip",
}
IMAGE_MIME_BY_EXTENSION = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _supabase_settings(bucket=None):
    url = (current_app.config.get('SUPABASE_URL') or '').rstrip('/')
    key = current_app.config.get('SUPABASE_KEY')
    bucket = bucket or current_app.config.get('UPLOAD_STORAGE_BUCKET', 'uploads')
    return url, key, bucket


def _private_bucket():
    return current_app.config.get('PRIVATE_UPLOAD_STORAGE_BUCKET', 'private-uploads')


def _supabase_required():
    return not current_app.config.get("TESTING") and current_app.config.get("APP_ENV") == "production"


def supabase_configured():
    supa_url, supa_key, _ = _supabase_settings()
    return bool(supa_url and supa_key)


def _should_keep_local_upload(uploaded):
    if not uploaded:
        return True
    return bool(current_app.config.get("UPLOAD_KEEP_LOCAL"))


def _remove_local_after_cloud_upload(filepath, uploaded):
    path = Path(filepath)
    if not _should_keep_local_upload(uploaded) and path.exists():
        path.unlink(missing_ok=True)


def scan_file_for_virus(filepath):
    """Run an optional server-side scanner command against an uploaded file."""
    if not current_app.config.get("VIRUS_SCAN_ENABLED"):
        return True
    command = current_app.config.get("VIRUS_SCAN_COMMAND")
    if not command:
        raise RuntimeError("Virus scan is enabled but VIRUS_SCAN_COMMAND is not configured.")
    args = shlex.split(command) + [str(filepath)]
    result = subprocess.run(args, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)  # nosec B603
    if result.returncode != 0:
        current_app.logger.warning("Virus scanner rejected upload %s: %s", filepath, result.stderr.decode("utf-8", "ignore")[:300])
        raise ValueError("The uploaded file did not pass security scanning.")
    return True


def upload_to_supabase(filepath, folder, filename, content_type=None, bucket=None):
    """Upload a saved file to Supabase Storage when configured."""
    if folder not in ALLOWED_UPLOAD_FOLDERS or Path(filename).name != filename:
        return False

    supa_url, supa_key, bucket = _supabase_settings(bucket)
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


def delete_from_supabase(folder, filename, bucket=None):
    """Delete a mirrored upload from Supabase Storage when configured."""
    if folder not in ALLOWED_UPLOAD_FOLDERS or Path(filename).name != filename:
        return False

    supa_url, supa_key, bucket = _supabase_settings(bucket)
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
    if folder not in PUBLIC_UPLOAD_FOLDERS or Path(filename).name != filename:
        return None
    supa_url, _, bucket = _supabase_settings()
    if not supa_url:
        return None
    encoded_path = quote(f"{folder}/{filename}", safe="/")
    return f"{supa_url}/storage/v1/object/public/{bucket}/{encoded_path}"


def public_upload_url(folder, filename):
    if not filename:
        return ""
    if folder in PUBLIC_UPLOAD_FOLDERS and Path(filename).name == filename:
        if not current_app.config.get("UPLOAD_KEEP_LOCAL"):
            public_url = supabase_public_url(folder, filename)
            if public_url:
                return public_url
        return url_for("uploaded_file", folder=folder, filename=filename)
    return ""


def fetch_private_upload(folder, filename):
    if folder not in PRIVATE_UPLOAD_FOLDERS or Path(filename).name != filename:
        return None
    supa_url, supa_key, bucket = _supabase_settings(_private_bucket())
    if not supa_url or not supa_key:
        return None
    encoded_path = quote(f"{folder}/{filename}", safe="/")
    endpoint = f"{supa_url}/storage/v1/object/{bucket}/{encoded_path}"
    response = requests.get(
        endpoint,
        headers={"Authorization": f"Bearer {supa_key}", "apikey": supa_key},
        timeout=45,
    )
    if response.status_code != 200:
        current_app.logger.info("Supabase private fetch failed: %s %s", response.status_code, response.text[:200])
        return None
    return response.content, response.headers.get("content-type") or "application/octet-stream"


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
        scan_file_for_virus(filepath)
        resize_image(filepath, max_size)
        content_type = detect_image_mime(filepath)
        try:
            uploaded = upload_to_supabase(filepath, folder, filename, content_type)
            if not uploaded and _supabase_required():
                raise RuntimeError("Supabase upload storage is not configured.")
        except Exception:
            current_app.logger.exception('Error uploading to Supabase')
            if _supabase_required():
                raise
        _remove_local_after_cloud_upload(filepath, uploaded)

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


def safe_message_mime(filename, stored_mime=None):
    """Return a conservative display MIME for validated or legacy attachments."""
    ext = filename.rsplit('.', 1)[1].lower() if filename and '.' in filename else ''
    stored_mime = (stored_mime or "").split(";", 1)[0].strip().lower()
    if ext in IMAGE_MIME_BY_EXTENSION:
        return stored_mime if stored_mime in set(IMAGE_MIME_BY_FORMAT.values()) else IMAGE_MIME_BY_EXTENSION[ext]
    if ext in MESSAGE_MIME_BY_EXTENSION:
        return MESSAGE_MIME_BY_EXTENSION[ext]
    return "application/octet-stream"


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
        safe_mime = validate_message_attachment(filepath, file.filename)
        scan_file_for_virus(filepath)
        attachment_size = filepath.stat().st_size
        try:
            uploaded = upload_to_supabase(filepath, 'messages', filename, safe_mime, bucket=_private_bucket())
            if not uploaded and _supabase_required():
                raise RuntimeError("Private Supabase upload storage is not configured.")
        except Exception:
            current_app.logger.exception('Error uploading message attachment to Supabase')
            if _supabase_required():
                raise
        _remove_local_after_cloud_upload(filepath, uploaded)
        return {
            "filename": filename,
            "original_name": secure_filename(file.filename)[:255],
            "size": attachment_size,
            "mime": safe_mime[:120],
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
            scan_file_for_virus(filepath)
            resize_image(filepath, max_size)
            content_type = detect_image_mime(filepath)
        else:
            scan_file_for_virus(filepath)
            content_type = media_mime_for(filename)
        try:
            uploaded = upload_to_supabase(filepath, folder, filename, content_type)
            if not uploaded and _supabase_required():
                raise RuntimeError("Supabase upload storage is not configured.")
        except Exception:
            current_app.logger.exception('Error uploading media to Supabase')
            if _supabase_required():
                raise
        _remove_local_after_cloud_upload(filepath, uploaded)
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


def detect_image_mime(filepath):
    Image.MAX_IMAGE_PIXELS = current_app.config.get("MAX_IMAGE_PIXELS", 24_000_000)
    with Image.open(filepath) as img:
        mime = IMAGE_MIME_BY_FORMAT.get(img.format)
    if not mime:
        raise ValueError("Unsupported image format.")
    return mime


def media_mime_for(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return {
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
    }.get(ext, "application/octet-stream")


def validate_message_attachment(filepath, original_filename):
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    if ext in {"png", "jpg", "jpeg", "gif", "webp"}:
        validate_image(filepath)
        resize_image(filepath, (1600, 1600))
        return detect_image_mime(filepath)
    if ext == "pdf":
        with Path(filepath).open("rb") as file_handle:
            if file_handle.read(5) != b"%PDF-":
                raise ValueError("Invalid PDF file.")
        return MESSAGE_MIME_BY_EXTENSION[ext]
    if ext == "zip":
        if not zipfile.is_zipfile(filepath):
            raise ValueError("Invalid ZIP file.")
        return MESSAGE_MIME_BY_EXTENSION[ext]
    if ext == "txt":
        with Path(filepath).open("rb") as file_handle:
            file_handle.read(8192).decode("utf-8")
        return MESSAGE_MIME_BY_EXTENSION[ext]
    raise ValueError("Unsupported attachment type.")


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
        deleted = False
        if filepath.exists():
            filepath.unlink()
            deleted = True
        try:
            deleted = delete_from_supabase(folder, filename, bucket=_private_bucket() if folder in PRIVATE_UPLOAD_FOLDERS else None) or deleted
        except Exception:
            current_app.logger.exception('Error deleting upload from Supabase')
        return deleted
