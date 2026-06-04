"""Safer upload helpers used by destructive and edit flows."""

from pathlib import Path

from flask import current_app

from app.utils.uploads import (
    ALLOWED_UPLOAD_FOLDERS,
    _remove_local_after_cloud_upload,
    allowed_file,
    generate_filename,
    detect_image_mime,
    resize_image,
    scan_file_for_virus,
    upload_to_supabase,
    validate_image,
    delete_from_supabase,
)


DEFAULT_FILES = {"default.jpg", "default_banner.jpg", ""}


def _supabase_required():
    return not current_app.config.get("TESTING") and current_app.config.get("APP_ENV") == "production"


def _folder_path(folder):
    if folder not in ALLOWED_UPLOAD_FOLDERS:
        raise ValueError("Unsupported upload folder.")

    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (root / folder).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Invalid upload folder path.")
    target.mkdir(parents=True, exist_ok=True)
    return target


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


def save_upload_secure(file, folder, max_size=(1200, 1200), max_bytes=None):
    """Save an image upload and return ``(filename, error)``."""
    if not file or not file.filename:
        return None, "No file selected."

    if not allowed_file(file.filename):
        return None, "Unsupported file type. Use PNG, JPG, JPEG, GIF, or WebP."

    max_bytes = max_bytes or int(current_app.config.get("MAX_UPLOAD_BYTES", current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)))
    size = _stream_size(file)
    if size is not None and size > max_bytes:
        return None, f"File is too large. Maximum size is {max_bytes // (1024 * 1024)} MB."

    try:
        upload_folder = _folder_path(folder)
    except ValueError as exc:
        return None, str(exc)

    filename = generate_filename(file.filename)
    filepath = upload_folder / filename

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
            current_app.logger.exception("Error uploading secure file to Supabase")
            if _supabase_required():
                raise
        _remove_local_after_cloud_upload(filepath, uploaded)
        return filename, None
    except Exception as exc:
        current_app.logger.warning("Secure upload failed for %s: %s", file.filename, exc)
        if filepath.exists():
            filepath.unlink(missing_ok=True)
        if "Supabase upload storage" in str(exc):
            return None, str(exc)
        return None, "The uploaded file could not be processed as a valid image."


def delete_file_secure(filename, folder):
    """Delete an uploaded file without allowing path traversal."""
    if not filename or filename in DEFAULT_FILES:
        return False

    if Path(filename).name != filename:
        current_app.logger.warning("Blocked unsafe upload delete path: %s", filename)
        return False

    try:
        upload_folder = _folder_path(folder)
    except ValueError as exc:
        current_app.logger.warning("Blocked upload delete from invalid folder %s: %s", folder, exc)
        return False

    filepath = (upload_folder / filename).resolve()
    if upload_folder not in filepath.parents:
        current_app.logger.warning("Blocked upload delete outside folder: %s", filename)
        return False

    deleted = False
    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        deleted = True
    try:
        deleted = delete_from_supabase(folder, filename) or deleted
    except Exception:
        current_app.logger.exception("Error deleting secure file from Supabase")
    return deleted
