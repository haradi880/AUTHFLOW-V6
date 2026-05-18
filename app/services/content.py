import re
import secrets
import string

from markupsafe import Markup
from markdown import markdown
import bleach

from app.extensions import db
from app.models import Tag


ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "span", "div", "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class"],
    "div": ["class"],
}


def generate_slug(text, model_class):
    slug = re.sub(r"[^\w\s-]", "", (text or "").lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    if not slug:
        slug = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    original = slug
    counter = 1
    while model_class.query.filter_by(slug=slug).first() is not None:
        slug = f"{original}-{counter}"
        counter += 1
    return slug


def calculate_reading_time(content):
    return max(1, round(len((content or "").split()) / 200))


def render_markdown(content):
    html = markdown(content or "", extensions=["fenced_code", "tables", "codehilite"])
    cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
    return Markup(cleaned)


def sync_tags(instance, tags_string):
    instance.tags = []
    for name in [tag.strip().lower() for tag in (tags_string or "").split(",") if tag.strip()]:
        tag = Tag.query.filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name, slug=generate_slug(name, Tag))
            db.session.add(tag)
        instance.tags.append(tag)
