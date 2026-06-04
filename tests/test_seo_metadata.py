import json
from html.parser import HTMLParser

from app import create_app, db
from app.models import Blog, Category, Company, Job, Project, Tag, User


class SeoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.meta = {}
        self.properties = {}
        self.links = {}
        self.ld_json = []
        self.in_ld_json = False
        self._script = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            if attrs.get("name"):
                self.meta[attrs["name"]] = attrs.get("content", "")
            if attrs.get("property"):
                self.properties[attrs["property"]] = attrs.get("content", "")
        elif tag == "link" and attrs.get("rel"):
            self.links[attrs["rel"]] = attrs.get("href", "")
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            self.in_ld_json = True
            self._script = []

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_ld_json:
            self.in_ld_json = False
            payload = "".join(self._script).strip()
            if payload:
                self.ld_json.append(json.loads(payload))

    def handle_data(self, data):
        if self.in_title:
            self.title += data.strip()
        if self.in_ld_json:
            self._script.append(data)


def seed_seo_content():
    user = User(
        username="seo-user",
        email="seo@example.com",
        is_verified=True,
        full_name="SEO User",
        headline="Robotics developer",
        bio="Builds public robotics projects.",
    )
    user.set_password("password123")
    category = Category(name="Robotics", slug="robotics")
    tag = Tag(name="Flask", slug="flask")
    db.session.add_all([user, category, tag])
    db.session.flush()

    blog = Blog(
        title="SEO Blog",
        slug="seo-blog",
        content="Public SEO blog content for search engines.",
        excerpt="Public SEO blog excerpt.",
        status="published",
        user_id=user.id,
        category_id=category.id,
    )
    project = Project(
        title="SEO Project",
        slug="seo-project",
        description="Public SEO project description.",
        status="published",
        user_id=user.id,
        category_id=category.id,
    )
    project.tags.append(tag)
    company = Company(name="SEO Robotics", slug="seo-robotics", created_by=user)
    db.session.add_all([blog, project, company])
    db.session.flush()
    job = Job(
        title="SEO Engineer",
        slug="seo-engineer",
        description="Build production robotics search systems.",
        job_type="contract",
        work_mode="remote",
        category="robotics",
        company_id=company.id,
        posted_by_id=user.id,
    )
    db.session.add(job)
    db.session.commit()


def parse(response):
    parser = SeoParser()
    parser.feed(response.get_data(as_text=True))
    return parser


def test_public_pages_emit_canonical_social_image_and_structured_data_without_csrf_session_cookie():
    app = create_app("testing")
    app.config["PUBLIC_BASE_URL"] = "https://haradibots.example.com"
    with app.app_context():
        db.create_all()
        seed_seo_content()

    paths = {
        "/blog/seo-blog": "BlogPosting",
        "/project/seo-project": "CreativeWork",
        "/seo-user": "Person",
        "/hiring/seo-engineer": "JobPosting",
    }
    with app.test_client() as client:
        for path, schema_type in paths.items():
            response = client.get(path)
            assert response.status_code == 200, path
            assert "Set-Cookie" not in response.headers, path
            page = parse(response)
            assert page.title, path
            assert page.meta["description"], path
            assert page.meta["robots"] == "index,follow", path
            assert page.links["canonical"].startswith("https://haradibots.example.com"), path
            assert page.properties["og:url"] == page.links["canonical"], path
            assert page.properties["og:image"].startswith("https://haradibots.example.com/og/haradibots.png"), path
            assert page.meta["twitter:image"] == page.properties["og:image"], path
            assert page.ld_json and page.ld_json[0]["@type"] == schema_type, path
            assert "localhost" not in response.get_data(as_text=True), path
            assert "csrf-token" not in response.get_data(as_text=True), path


def test_auth_pages_keep_csrf_available_for_post_forms():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

    with app.test_client() as client:
        response = client.get("/login")

    page = parse(response)
    assert response.status_code == 200
    assert page.meta["csrf-token"]


def test_default_social_card_is_cacheable_png():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

    with app.test_client() as client:
        response = client.get("/og/haradibots.png")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data.startswith(b"\x89PNG")
    assert "public" in response.headers["Cache-Control"]
