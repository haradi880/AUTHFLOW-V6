from html.parser import HTMLParser

from app import create_app, db
from app.models import Blog, Category, Project, User


class AccessibilityParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.html_lang = None
        self.title_text = ""
        self.in_title = False
        self.viewport = False
        self.canonical = False
        self.images = []
        self.buttons = []
        self.links = []
        self.inputs = []
        self.labels_for = set()
        self._current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.html_lang = attrs.get("lang")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta" and attrs.get("name") == "viewport":
            self.viewport = bool(attrs.get("content"))
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = bool(attrs.get("href"))
        elif tag == "img":
            self.images.append(attrs)
        elif tag == "button":
            self.buttons.append({"attrs": attrs, "text": ""})
            self._current = ("button", len(self.buttons) - 1)
        elif tag == "a":
            self.links.append({"attrs": attrs, "text": ""})
            self._current = ("link", len(self.links) - 1)
        elif tag in {"input", "select", "textarea"}:
            input_type = (attrs.get("type") or "").lower()
            if input_type not in {"hidden", "submit", "button", "checkbox", "radio"}:
                self.inputs.append(attrs)
        elif tag == "label" and attrs.get("for"):
            self.labels_for.add(attrs["for"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if self._current and ((tag == "button" and self._current[0] == "button") or (tag == "a" and self._current[0] == "link")):
            self._current = None

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data.strip()
        if self._current:
            kind, index = self._current
            target = self.buttons if kind == "button" else self.links
            target[index]["text"] += data.strip()


def seed_accessibility_content():
    user = User(username="a11y", email="a11y@example.com", is_verified=True)
    user.set_password("password123")
    category = Category(name="Accessibility", slug="accessibility")
    db.session.add_all([user, category])
    db.session.flush()
    db.session.add_all(
        [
            Blog(
                title="Accessible Blog",
                slug="accessible-blog",
                content="Accessible content",
                excerpt="Accessible",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
            Project(
                title="Accessible Project",
                slug="accessible-project",
                description="Accessible project",
                status="published",
                user_id=user.id,
                category_id=category.id,
            ),
        ]
    )
    db.session.commit()


def parse_response(response):
    parser = AccessibilityParser()
    parser.feed(response.get_data(as_text=True))
    return parser


def accessible_name(item):
    attrs = item["attrs"]
    return item.get("text") or attrs.get("aria-label") or attrs.get("title")


def test_core_public_pages_have_accessibility_basics():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_accessibility_content()

    paths = ["/blogs", "/projects", "/login", "/register", "/blog/accessible-blog", "/project/accessible-project"]
    with app.test_client() as client:
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            parser = parse_response(response)
            assert parser.html_lang, path
            assert parser.viewport, path
            assert parser.canonical, path
            assert parser.title_text, path
            assert all("alt" in image for image in parser.images), path
            assert all(accessible_name(button) for button in parser.buttons), path
            assert all(link["text"] or link["attrs"].get("aria-label") or link["attrs"].get("title") for link in parser.links if link["attrs"].get("href")), path
            for field in parser.inputs:
                field_id = field.get("id")
                has_name = field.get("aria-label") or field.get("placeholder") or (field_id and field_id in parser.labels_for)
                assert has_name, f"{path} input={field}"
