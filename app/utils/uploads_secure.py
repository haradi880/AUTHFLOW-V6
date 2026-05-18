"""Safer upload helpers used by destructive and edit flows."""

from pathlib import Path

from flask import current_app

from app.utils.uploads import (
    ALLOWED_UPLOAD_FOLDERS,
    allowed_file,
    generate_filename,
    resize_image,
    validate_image,
)


DEFAULT_FILES = {"default.jpg", "default_banner.jpg", ""}


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
        resize_image(filepath, max_size)
        return filename, None
    except Exception as exc:
        current_app.logger.warning("Secure upload failed for %s: %s", file.filename, exc)
        if filepath.exists():
            filepath.unlink(missing_ok=True)
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

    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        return True
    return False
