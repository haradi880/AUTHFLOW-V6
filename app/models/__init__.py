from datetime import datetime, timedelta

from flask import url_for
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


blog_tags = db.Table(
    "blog_tags",
    db.Column("blog_id", db.Integer, db.ForeignKey("blogs.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

project_tags = db.Table(
    "project_tags",
    db.Column("project_id", db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

devlog_tags = db.Table(
    "devlog_tags",
    db.Column("devlog_id", db.Integer, db.ForeignKey("devlogs.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    headline = db.Column(db.String(160))
    bio = db.Column(db.String(500))
    location = db.Column(db.String(120))
    website = db.Column(db.String(255))
    resume_url = db.Column(db.String(500))
    avatar = db.Column(db.String(255), default="default.jpg")
    banner = db.Column(db.String(255), default="default_banner.jpg")
    skills = db.Column(db.String(500))
    twitter = db.Column(db.String(255))
    linkedin = db.Column(db.String(255))
    github = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column("is_active", db.Boolean, default=True, nullable=False)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    featured_blog_id = db.Column(db.Integer, db.ForeignKey("blogs.id", ondelete="SET NULL"), index=True)
    featured_project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    pending_email = db.Column(db.String(255))
    email_on_messages = db.Column(db.Boolean, default=True, nullable=False)
    email_on_comments = db.Column(db.Boolean, default=True, nullable=False)
    email_on_follows = db.Column(db.Boolean, default=True, nullable=False)
    email_on_likes = db.Column(db.Boolean, default=False, nullable=False)
    weekly_digest = db.Column(db.Boolean, default=True, nullable=False)
    message_permission = db.Column(db.String(20), default="everyone", nullable=False)
    profile_views_count = db.Column(db.Integer, default=0, nullable=False)
    xp_total = db.Column(db.Integer, default=0, nullable=False, index=True)
    level = db.Column(db.Integer, default=1, nullable=False, index=True)
    profile_xp_awarded_at = db.Column(db.DateTime)

    # Reputation
    reputation_points = db.Column(db.Integer, default=0, nullable=False, index=True)
    trust_level = db.Column(db.Integer, default=1, nullable=False)
    contributor_tier = db.Column(db.String(30), default="newcomer", nullable=False)
    is_verified_creator = db.Column(db.Boolean, default=False, nullable=False)

    # Hiring
    open_to_work = db.Column(db.Boolean, default=False, nullable=False)
    availability_status = db.Column(db.String(30), default="not-specified", nullable=False)
    job_title = db.Column(db.String(160))
    years_experience = db.Column(db.Integer)
    preferred_work_type = db.Column(db.String(30))
    is_recruiter = db.Column(db.Boolean, default=False, nullable=False)

    # Robotics
    robotics_specialties = db.Column(db.Text)  # comma-separated

    # Analysis
    portfolio_score = db.Column(db.Integer)
    last_analyzed_at = db.Column(db.DateTime)

    blogs = db.relationship("Blog", back_populates="author", lazy="dynamic", cascade="all, delete-orphan", foreign_keys="Blog.user_id")
    projects = db.relationship("Project", back_populates="author", lazy="dynamic", cascade="all, delete-orphan", foreign_keys="Project.user_id")
    devlogs = db.relationship("DevLog", back_populates="author", lazy="dynamic", cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="author", lazy="dynamic", cascade="all, delete-orphan")
    otp_tokens = db.relationship("OTPToken", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
    received_notifications = db.relationship(
        "Notification",
        foreign_keys="Notification.user_id",
        back_populates="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    xp_transactions = db.relationship("XPTransaction", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")

    followed = db.relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        back_populates="follower",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    followers = db.relationship(
        "Follow",
        foreign_keys="Follow.followed_id",
        back_populates="followed",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def register_failed_login(self, max_attempts=5, lock_minutes=15):
        self.failed_login_count = (self.failed_login_count or 0) + 1
        if self.failed_login_count >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(minutes=lock_minutes)

    def clear_failed_logins(self):
        self.failed_login_count = 0
        self.locked_until = None

    def increment_failed_login(self, max_attempts=5, lock_minutes=15):
        self.register_failed_login(max_attempts, lock_minutes)
        db.session.commit()

    def reset_failed_logins(self):
        self.clear_failed_logins()
        db.session.commit()

    def get_skills_list(self):
        return [skill.strip() for skill in (self.skills or "").split(",") if skill.strip()]

    def profile_completion(self):
        checks = [
            bool(self.full_name),
            bool(self.headline),
            bool(self.bio and len(self.bio) >= 40),
            bool(self.location),
            bool(self.website),
            bool(self.resume_url),
            bool(self.github),
            bool(self.linkedin),
            len(self.get_skills_list()) >= 3,
            bool(self.avatar and self.avatar != "default.jpg"),
            bool(self.banner and self.banner != "default_banner.jpg"),
        ]
        completed = sum(1 for item in checks if item)
        return round((completed / len(checks)) * 100)

    @property
    def xp_progress(self):
        try:
            from app.services.gamification import xp_progress

            return xp_progress(self.xp_total or 0)
        except Exception:
            return {"level": self.level or 1, "current": 0, "needed": 100, "percent": 0}

    def set_skills_list(self, skills_list):
        self.skills = ",".join(skill.strip() for skill in skills_list if skill.strip())

    def follow(self, user):
        if user.id != self.id and not self.is_following(user):
            db.session.add(Follow(follower_id=self.id, followed_id=user.id))

    def unfollow(self, user):
        follow = self.followed.filter_by(followed_id=user.id).first()
        if follow:
            db.session.delete(follow)

    def is_following(self, user):
        return user and self.followed.filter_by(followed_id=user.id).first() is not None

    def followers_count(self):
        return self.followers.count()

    def following_count(self):
        return self.followed.count()

    @property
    def avatar_url(self):
        return url_for("uploaded_file", folder="avatars", filename=self.avatar) if self.avatar else ""

    @property
    def banner_url(self):
        return url_for("uploaded_file", folder="banners", filename=self.banner) if self.banner else ""

    @property
    def social(self):
        return {"twitter": self.twitter, "linkedin": self.linkedin, "github": self.github}

    def __str__(self):
        return self.username

    def __getitem__(self, index):
        return self.username[index]


class Follow(db.Model):
    __tablename__ = "follows"

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    follower = db.relationship("User", foreign_keys=[follower_id], back_populates="followed")
    followed = db.relationship("User", foreign_keys=[followed_id], back_populates="followers")

    __table_args__ = (db.UniqueConstraint("follower_id", "followed_id", name="uq_follow_pair"),)


class XPTransaction(db.Model):
    __tablename__ = "xp_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    points = db.Column(db.Integer, nullable=False)
    source_type = db.Column(db.String(50), index=True)
    source_id = db.Column(db.Integer, index=True)
    meta = db.Column(db.JSON)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    bucket_key = db.Column(db.String(120), index=True)

    user = db.relationship("User", back_populates="xp_transactions")

    __table_args__ = (
        db.UniqueConstraint("user_id", "action", "source_type", "source_id", name="uq_xp_source_once"),
        db.UniqueConstraint("user_id", "action", "bucket_key", name="uq_xp_bucket_once"),
    )


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))

    blogs = db.relationship("Blog", back_populates="category", lazy="dynamic")
    projects = db.relationship("Project", back_populates="category", lazy="dynamic")

    def __str__(self):
        return self.name


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)

    def __str__(self):
        return self.name


class Blog(TimestampMixin, db.Model):
    __tablename__ = "blogs"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.String(500))
    thumbnail = db.Column(db.String(255))
    status = db.Column(db.String(20), default="draft", nullable=False, index=True)
    reading_time = db.Column(db.Integer, default=1, nullable=False)
    views_count = db.Column(db.Integer, default=0, nullable=False)
    likes_count = db.Column(db.Integer, default=0, nullable=False)
    comments_count = db.Column(db.Integer, default=0, nullable=False)
    published_at = db.Column(db.DateTime, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"), index=True)

    author = db.relationship("User", back_populates="blogs", foreign_keys=[user_id])
    category = db.relationship("Category", back_populates="blogs")
    tags = db.relationship("Tag", secondary=blog_tags, lazy="subquery", backref=db.backref("blogs", lazy=True))
    comments = db.relationship("Comment", back_populates="blog", lazy="dynamic", cascade="all, delete-orphan")
    likes = db.relationship("BlogLike", back_populates="blog", lazy="dynamic", cascade="all, delete-orphan")
    bookmarks = db.relationship("Bookmark", back_populates="blog", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def thumbnail_url(self):
        return url_for("uploaded_file", folder="blogs", filename=self.thumbnail) if self.thumbnail else ""

    @property
    def author_bio(self):
        return self.author.bio if self.author else ""

    @property
    def author_full_bio(self):
        return self.author.bio if self.author else ""

    @property
    def author_skills(self):
        return self.author.get_skills_list() if self.author else []

    @property
    def followers_count(self):
        return self.author.followers_count() if self.author else 0

    @property
    def total_blogs(self):
        return self.author.blogs.filter_by(status="published").count() if self.author else 0

    def calculate_reading_time(self):
        self.reading_time = max(1, round(len((self.content or "").split()) / 200))

    def is_liked_by(self, user):
        return bool(user and getattr(user, "is_authenticated", False) and BlogLike.query.filter_by(blog_id=self.id, user_id=user.id).first())

    def is_bookmarked_by(self, user):
        return bool(user and getattr(user, "is_authenticated", False) and Bookmark.query.filter_by(blog_id=self.id, user_id=user.id).first())

    def get_absolute_url(self):
        return url_for("blog.blog_detail", slug=self.slug)


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    thumbnail = db.Column(db.String(255))
    github_url = db.Column(db.String(500))
    demo_url = db.Column(db.String(500))
    stars_count = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(20), default="draft", nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"), index=True)

    author = db.relationship("User", back_populates="projects", foreign_keys=[user_id])
    category = db.relationship("Category", back_populates="projects")
    tags = db.relationship("Tag", secondary=project_tags, lazy="subquery", backref=db.backref("projects", lazy=True))
    images = db.relationship("ProjectImage", back_populates="project", lazy="dynamic", cascade="all, delete-orphan")
    stars = db.relationship("ProjectStar", back_populates="project", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def thumbnail_url(self):
        return url_for("uploaded_file", folder="projects", filename=self.thumbnail) if self.thumbnail else ""

    @property
    def tech_stack(self):
        return [tag.name for tag in self.tags]

    def get_absolute_url(self):
        return url_for("project.project_detail", slug=self.slug)

    def is_starred_by(self, user):
        return bool(user and getattr(user, "is_authenticated", False) and ProjectStar.query.filter_by(project_id=self.id, user_id=user.id).first())


class ProjectStar(db.Model):
    __tablename__ = "project_stars"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    project = db.relationship("Project", back_populates="stars")
    user = db.relationship("User", backref=db.backref("project_stars", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("user_id", "project_id", name="uq_project_star"),)


class ProjectImage(db.Model):
    __tablename__ = "project_images"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(200))
    order = db.Column(db.Integer, default=0, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    project = db.relationship("Project", back_populates="images")

    @property
    def url(self):
        return url_for("uploaded_file", folder="projects", filename=self.filename)


class DevLog(TimestampMixin, db.Model):
    __tablename__ = "devlogs"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    progress = db.Column(db.Integer, default=0, nullable=False, index=True)
    milestone = db.Column(db.String(160))
    is_pinned = db.Column(db.Boolean, default=False, nullable=False, index=True)
    visibility = db.Column(db.String(20), default="public", nullable=False, index=True)
    likes_count = db.Column(db.Integer, default=0, nullable=False)
    comments_count = db.Column(db.Integer, default=0, nullable=False)
    reposts_count = db.Column(db.Integer, default=0, nullable=False)
    bookmarks_count = db.Column(db.Integer, default=0, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    author = db.relationship("User", back_populates="devlogs")
    tags = db.relationship("Tag", secondary=devlog_tags, lazy="subquery", backref=db.backref("devlogs", lazy=True))
    media = db.relationship("DevLogMedia", back_populates="devlog", order_by="DevLogMedia.order", cascade="all, delete-orphan")
    comments = db.relationship("DevLogComment", back_populates="devlog", lazy="dynamic", cascade="all, delete-orphan")
    likes = db.relationship("DevLogLike", back_populates="devlog", lazy="dynamic", cascade="all, delete-orphan")
    bookmarks = db.relationship("DevLogBookmark", back_populates="devlog", lazy="dynamic", cascade="all, delete-orphan")
    reposts = db.relationship("DevLogRepost", back_populates="devlog", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def preview(self):
        return (self.content or "").strip()[:180]

    @property
    def trending_score(self):
        return (
            (self.likes_count or 0) * 3
            + (self.comments_count or 0) * 4
            + (self.reposts_count or 0) * 5
            + (self.bookmarks_count or 0)
            + min(self.progress or 0, 100)
        )

    def is_liked_by(self, user):
        return bool(user and getattr(user, "is_authenticated", False) and DevLogLike.query.filter_by(devlog_id=self.id, user_id=user.id).first())

    def is_bookmarked_by(self, user):
        return bool(user and getattr(user, "is_authenticated", False) and DevLogBookmark.query.filter_by(devlog_id=self.id, user_id=user.id).first())

    def is_reposted_by(self, user):
        return bool(user and getattr(user, "is_authenticated", False) and DevLogRepost.query.filter_by(devlog_id=self.id, user_id=user.id).first())

    def get_absolute_url(self):
        return url_for("devlogs.detail", devlog_id=self.id)


class DevLogMedia(db.Model):
    __tablename__ = "devlog_media"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    media_type = db.Column(db.String(20), default="image", nullable=False)
    alt_text = db.Column(db.String(200))
    order = db.Column(db.Integer, default=0, nullable=False)
    devlog_id = db.Column(db.Integer, db.ForeignKey("devlogs.id", ondelete="CASCADE"), nullable=False, index=True)

    devlog = db.relationship("DevLog", back_populates="media")

    @property
    def url(self):
        return url_for("uploaded_file", folder="devlogs", filename=self.filename)


class DevLogComment(TimestampMixin, db.Model):
    __tablename__ = "devlog_comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    devlog_id = db.Column(db.Integer, db.ForeignKey("devlogs.id", ondelete="CASCADE"), nullable=False, index=True)

    author = db.relationship("User", backref=db.backref("devlog_comments", lazy="dynamic", cascade="all, delete-orphan"))
    devlog = db.relationship("DevLog", back_populates="comments")


class DevLogLike(db.Model):
    __tablename__ = "devlog_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    devlog_id = db.Column(db.Integer, db.ForeignKey("devlogs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    devlog = db.relationship("DevLog", back_populates="likes")
    user = db.relationship("User", backref=db.backref("devlog_likes", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("user_id", "devlog_id", name="uq_devlog_like"),)


class DevLogBookmark(db.Model):
    __tablename__ = "devlog_bookmarks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    devlog_id = db.Column(db.Integer, db.ForeignKey("devlogs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    devlog = db.relationship("DevLog", back_populates="bookmarks")
    user = db.relationship("User", backref=db.backref("devlog_bookmarks", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("user_id", "devlog_id", name="uq_devlog_bookmark"),)


class DevLogRepost(db.Model):
    __tablename__ = "devlog_reposts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    devlog_id = db.Column(db.Integer, db.ForeignKey("devlogs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    devlog = db.relationship("DevLog", back_populates="reposts")
    user = db.relationship("User", backref=db.backref("devlog_reposts", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("user_id", "devlog_id", name="uq_devlog_repost"),)


class Comment(TimestampMixin, db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blog_id = db.Column(db.Integer, db.ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False, index=True)

    author = db.relationship("User", back_populates="comments")
    blog = db.relationship("Blog", back_populates="comments")
    replies = db.relationship("Comment", backref=db.backref("parent", remote_side=[id]), lazy="dynamic", cascade="all, delete-orphan")

    @property
    def likes(self):
        return 0


class BlogLike(db.Model):
    __tablename__ = "blog_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blog_id = db.Column(db.Integer, db.ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    blog = db.relationship("Blog", back_populates="likes")
    user = db.relationship("User", backref=db.backref("blog_likes", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("user_id", "blog_id", name="uq_blog_like"),)


class Bookmark(db.Model):
    __tablename__ = "bookmarks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blog_id = db.Column(db.Integer, db.ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    blog = db.relationship("Blog", back_populates="bookmarks")
    user = db.relationship("User", backref=db.backref("bookmarks", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("user_id", "blog_id", name="uq_bookmark"),)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    seen_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    email_sent_at = db.Column(db.DateTime)
    email_status = db.Column(db.String(30), default="pending", nullable=False, index=True)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.String(500))
    priority = db.Column(db.String(20), default="normal", nullable=False, index=True)
    entity_type = db.Column(db.String(60), index=True)
    entity_id = db.Column(db.Integer, index=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id], back_populates="received_notifications")
    from_user = db.relationship("User", foreign_keys=[from_user_id])

    __table_args__ = (
        db.Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
        db.Index("ix_notifications_entity", "entity_type", "entity_id"),
    )

    def mark_seen(self):
        if not self.seen_at:
            self.seen_at = datetime.utcnow()

    def mark_read(self):
        self.is_read = True
        self.mark_seen()
        if not self.read_at:
            self.read_at = datetime.utcnow()


class OTPToken(db.Model):
    __tablename__ = "otp_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    consumed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="otp_tokens")

    def set_code(self, code):
        self.code_hash = generate_password_hash(code)

    def verify(self, code):
        return not self.consumed_at and self.expires_at > datetime.utcnow() and check_password_hash(self.code_hash, code)


class LoginSession(db.Model):
    __tablename__ = "login_sessions"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address = db.Column(db.String(45), index=True)
    user_agent = db.Column(db.String(500))
    device_label = db.Column(db.String(160))
    browser = db.Column(db.String(80))
    platform = db.Column(db.String(80))
    fingerprint = db.Column(db.String(128), nullable=False, index=True)
    is_current = db.Column(db.Boolean, default=False, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, index=True)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("login_sessions", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (
        db.Index("ix_login_sessions_user_revoked_seen", "user_id", "revoked_at", "last_seen_at"),
        db.Index("ix_login_sessions_user_fingerprint", "user_id", "fingerprint"),
    )

    @property
    def is_active(self):
        return self.revoked_at is None


class LoginEvent(db.Model):
    __tablename__ = "login_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    email = db.Column(db.String(255), index=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    success = db.Column(db.Boolean, default=False, nullable=False, index=True)
    reason = db.Column(db.String(160))
    ip_address = db.Column(db.String(45), index=True)
    user_agent = db.Column(db.String(500))
    fingerprint = db.Column(db.String(128), index=True)
    suspicious = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("login_events", lazy="dynamic"))

    __table_args__ = (
        db.Index("ix_login_events_user_created", "user_id", "created_at"),
        db.Index("ix_login_events_email_created", "email", "created_at"),
        db.Index("ix_login_events_success_created", "success", "created_at"),
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    attachment_filename = db.Column(db.String(255))
    attachment_original_name = db.Column(db.String(255))
    attachment_mime = db.Column(db.String(120))
    attachment_size = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    sender = db.relationship("User", foreign_keys=[sender_id], backref=db.backref("sent_messages", lazy="dynamic"))
    recipient = db.relationship("User", foreign_keys=[recipient_id], backref=db.backref("received_messages", lazy="dynamic"))

    @property
    def has_attachment(self):
        return bool(self.attachment_filename)

    @property
    def attachment_is_image(self):
        return bool((self.attachment_mime or "").startswith("image/"))


# =====================================================
#  COLLABORATION SYSTEM
# =====================================================

class Team(TimestampMixin, db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    description = db.Column(db.String(500))
    visibility = db.Column(db.String(20), default="private", nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    owner = db.relationship("User", foreign_keys=[owner_id], backref=db.backref("owned_teams", lazy="dynamic"))
    members = db.relationship("TeamMember", back_populates="team", lazy="dynamic", cascade="all, delete-orphan")
    invitations = db.relationship("TeamInvitation", back_populates="team", lazy="dynamic", cascade="all, delete-orphan")
    activities = db.relationship("ActivityUpdate", back_populates="team", lazy="dynamic", cascade="all, delete-orphan")

    def member_for(self, user):
        if not user or not getattr(user, "is_authenticated", False):
            return None
        return TeamMember.query.filter_by(team_id=self.id, user_id=user.id).first()

    def can_manage(self, user):
        member = self.member_for(user)
        return bool(user and (getattr(user, "is_admin", False) or self.owner_id == user.id or (member and member.role in {"owner", "admin"})))


class TeamMember(db.Model):
    __tablename__ = "team_members"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(30), default="member", nullable=False, index=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    team = db.relationship("Team", back_populates="members")
    user = db.relationship("User", backref=db.backref("team_memberships", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        db.Index("ix_team_members_user_role", "user_id", "role"),
    )


class TeamInvitation(TimestampMixin, db.Model):
    __tablename__ = "team_invitations"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    inviter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    invitee_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(30), default="member", nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False, index=True)
    message = db.Column(db.String(500))
    responded_at = db.Column(db.DateTime)

    team = db.relationship("Team", back_populates="invitations")
    inviter = db.relationship("User", foreign_keys=[inviter_id])
    invitee = db.relationship("User", foreign_keys=[invitee_id], backref=db.backref("team_invitations", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint("team_id", "invitee_id", "status", name="uq_team_invitation_status"),
        db.Index("ix_team_invitations_invitee_status", "invitee_id", "status"),
    )


class CollaborationRequest(TimestampMixin, db.Model):
    __tablename__ = "collaboration_requests"

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(1000))
    requested_role = db.Column(db.String(60), default="collaborator", nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False, index=True)
    responded_at = db.Column(db.DateTime)

    requester = db.relationship("User", foreign_keys=[requester_id], backref=db.backref("sent_collaboration_requests", lazy="dynamic", cascade="all, delete-orphan"))
    recipient = db.relationship("User", foreign_keys=[recipient_id], backref=db.backref("received_collaboration_requests", lazy="dynamic", cascade="all, delete-orphan"))
    project = db.relationship("Project", backref=db.backref("collaboration_requests", lazy="dynamic"))
    job = db.relationship("Job", backref=db.backref("collaboration_requests", lazy="dynamic"))
    team = db.relationship("Team", backref=db.backref("collaboration_requests", lazy="dynamic"))

    __table_args__ = (
        db.Index("ix_collab_requests_recipient_status", "recipient_id", "status"),
        db.Index("ix_collab_requests_requester_status", "requester_id", "status"),
    )


class ActivityUpdate(TimestampMixin, db.Model):
    __tablename__ = "activity_updates"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    summary = db.Column(db.String(500), nullable=False)

    actor = db.relationship("User", foreign_keys=[actor_id])
    team = db.relationship("Team", back_populates="activities")
    project = db.relationship("Project", backref=db.backref("activity_updates", lazy="dynamic"))
    job = db.relationship("Job", backref=db.backref("activity_updates", lazy="dynamic"))

    __table_args__ = (
        db.Index("ix_activity_updates_team_created", "team_id", "created_at"),
        db.Index("ix_activity_updates_project_created", "project_id", "created_at"),
        db.Index("ix_activity_updates_job_created", "job_id", "created_at"),
    )


class Block(db.Model):
    __tablename__ = "blocks"

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    blocker = db.relationship("User", foreign_keys=[blocker_id], backref=db.backref("blocks_made", lazy="dynamic", cascade="all, delete-orphan"))
    blocked = db.relationship("User", foreign_keys=[blocked_id], backref=db.backref("blocks_received", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(80), nullable=False)
    details = db.Column(db.String(1000))
    status = db.Column(db.String(20), default="open", nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reported_user = db.relationship("User", foreign_keys=[reported_user_id], backref=db.backref("reports_received", lazy="dynamic"))


# =====================================================
#  REPUTATION & BADGES
# =====================================================

class Badge(db.Model):
    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300))
    icon = db.Column(db.String(60), default="⭐")
    tier = db.Column(db.String(20), default="bronze", nullable=False)  # bronze, silver, gold, platinum
    category = db.Column(db.String(50), nullable=False, index=True)  # content, social, robotics, hiring
    criteria_type = db.Column(db.String(50))
    criteria_value = db.Column(db.Integer, default=1)
    xp_reward = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    holders = db.relationship("UserBadge", back_populates="badge", lazy="dynamic", cascade="all, delete-orphan")


class UserBadge(db.Model):
    __tablename__ = "user_badges"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id", ondelete="CASCADE"), nullable=False, index=True)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("badges_earned", lazy="dynamic", cascade="all, delete-orphan"))
    badge = db.relationship("Badge", back_populates="holders")

    __table_args__ = (db.UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)


class Streak(db.Model):
    __tablename__ = "streaks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    current = db.Column(db.Integer, default=0, nullable=False)
    longest = db.Column(db.Integer, default=0, nullable=False)
    last_active_date = db.Column(db.Date)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("streak", uselist=False, cascade="all, delete-orphan"))


class LeaderboardSnapshot(db.Model):
    __tablename__ = "leaderboard_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period = db.Column(db.String(20), nullable=False, index=True)  # weekly, monthly, alltime
    period_key = db.Column(db.String(20), nullable=False, index=True)  # e.g. 2026-W19
    rank = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("leaderboard_entries", lazy="dynamic"))

    __table_args__ = (db.UniqueConstraint("user_id", "period", "period_key", name="uq_leaderboard_entry"),)


# =====================================================
#  HIRING SYSTEM
# =====================================================

class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    logo = db.Column(db.String(255))
    website = db.Column(db.String(500))
    location = db.Column(db.String(200))
    size = db.Column(db.String(50))  # 1-10, 11-50, etc.
    industry = db.Column(db.String(100))
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.relationship("User", backref=db.backref("companies", lazy="dynamic"))
    jobs = db.relationship("Job", back_populates="company", lazy="dynamic", cascade="all, delete-orphan")


class Job(TimestampMixin, db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    job_type = db.Column(db.String(30), nullable=False, index=True)  # full-time, part-time, contract, internship, freelance
    work_mode = db.Column(db.String(20), default="remote", nullable=False)  # remote, onsite, hybrid
    category = db.Column(db.String(60), nullable=False, index=True)  # robotics, ai-ml, web, mobile, devops, etc.
    location = db.Column(db.String(200))
    salary_min = db.Column(db.Integer)
    salary_max = db.Column(db.Integer)
    salary_currency = db.Column(db.String(10), default="USD")
    experience_level = db.Column(db.String(30))  # entry, mid, senior, lead
    skills_required = db.Column(db.Text)  # comma separated
    status = db.Column(db.String(20), default="active", nullable=False, index=True)  # active, closed, draft
    applications_count = db.Column(db.Integer, default=0, nullable=False)
    views_count = db.Column(db.Integer, default=0, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    expires_at = db.Column(db.DateTime)

    company = db.relationship("Company", back_populates="jobs")
    posted_by = db.relationship("User", backref=db.backref("posted_jobs", lazy="dynamic"))
    applications = db.relationship("JobApplication", back_populates="job", lazy="dynamic", cascade="all, delete-orphan")
    saves = db.relationship("JobSave", back_populates="job", lazy="dynamic", cascade="all, delete-orphan")

    def get_skills_list(self):
        return [s.strip() for s in (self.skills_required or "").split(",") if s.strip()]

    def user_can_manage(self, user):
        company_owner_id = self.company.created_by_id if self.company else None
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and (user.id == self.posted_by_id or user.id == company_owner_id or getattr(user, "is_admin", False))
        )

    __table_args__ = (
        db.Index("ix_jobs_status_created", "status", "created_at"),
        db.Index("ix_jobs_status_category_type_mode", "status", "category", "job_type", "work_mode"),
        db.Index("ix_jobs_company_status", "company_id", "status"),
    )


class JobApplication(TimestampMixin, db.Model):
    __tablename__ = "job_applications"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    cover_note = db.Column(db.Text)
    resume_url = db.Column(db.String(500))
    status = db.Column(db.String(30), default="applied", nullable=False, index=True)  # applied, reviewed, shortlisted, rejected, hired
    recruiter_response = db.Column(db.String(1000))
    status_changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)

    job = db.relationship("Job", back_populates="applications")
    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("job_applications", lazy="dynamic", cascade="all, delete-orphan"),
    )
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])

    __table_args__ = (
        db.UniqueConstraint("job_id", "user_id", name="uq_job_application"),
        db.Index("ix_job_applications_job_status_created", "job_id", "status", "created_at"),
        db.Index("ix_job_applications_user_status_created", "user_id", "status", "created_at"),
    )


class JobSave(db.Model):
    __tablename__ = "job_saves"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("saved_jobs", lazy="dynamic", cascade="all, delete-orphan"))
    job = db.relationship("Job", back_populates="saves")

    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_job_save"),)


class DonationIntent(db.Model):
    __tablename__ = "donation_intents"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default="INR", nullable=False)
    upi_url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(30), default="qr_generated", nullable=False, index=True)
    ip_address = db.Column(db.String(45), index=True)
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = db.Column(db.DateTime)

    user = db.relationship("User", backref=db.backref("donation_intents", lazy="dynamic"))

    __table_args__ = (
        db.Index("ix_donation_intents_user_created", "user_id", "created_at"),
        db.Index("ix_donation_intents_status_created", "status", "created_at"),
    )


class SupportTicket(TimestampMixin, db.Model):
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    username = db.Column(db.String(80))
    category = db.Column(db.String(40), default="general", nullable=False, index=True)
    subject = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="open", nullable=False, index=True)
    priority = db.Column(db.String(20), default="normal", nullable=False, index=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    resolved_at = db.Column(db.DateTime)
    handled_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    admin_note = db.Column(db.String(1000))

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("support_tickets", lazy="dynamic"))
    handled_by = db.relationship("User", foreign_keys=[handled_by_id])

    __table_args__ = (
        db.Index("ix_support_tickets_status_created", "status", "created_at"),
        db.Index("ix_support_tickets_category_status", "category", "status"),
    )


# =====================================================
#  ROBOTICS HUB
# =====================================================

robotics_project_tags = db.Table(
    "robotics_project_tags",
    db.Column("robotics_project_id", db.Integer, db.ForeignKey("robotics_projects.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class RoboticsProject(TimestampMixin, db.Model):
    __tablename__ = "robotics_projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    thumbnail = db.Column(db.String(255))
    project_type = db.Column(db.String(50), nullable=False, index=True)  # robot, drone, iot, cnc, embedded, ros, arduino, esp32, rpi
    difficulty = db.Column(db.String(20), default="intermediate")  # beginner, intermediate, advanced, expert
    status = db.Column(db.String(20), default="draft", nullable=False, index=True)
    github_url = db.Column(db.String(500))
    demo_url = db.Column(db.String(500))
    video_url = db.Column(db.String(500))
    hardware_specs = db.Column(db.Text)  # JSON: components, voltage, power, etc.
    bom_data = db.Column(db.Text)  # JSON: bill of materials
    views_count = db.Column(db.Integer, default=0, nullable=False)
    stars_count = db.Column(db.Integer, default=0, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    author = db.relationship("User", backref=db.backref("robotics_projects", lazy="dynamic", cascade="all, delete-orphan"))
    tags = db.relationship("Tag", secondary=robotics_project_tags, lazy="subquery", backref=db.backref("robotics_projects", lazy=True))
    files = db.relationship("RoboticsFile", back_populates="project", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def thumbnail_url(self):
        return url_for("uploaded_file", folder="projects", filename=self.thumbnail) if self.thumbnail else ""


class RoboticsFile(db.Model):
    __tablename__ = "robotics_files"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    file_type = db.Column(db.String(30), nullable=False, index=True)  # cad, stl, bom, schematic, firmware, code, datasheet, other
    description = db.Column(db.String(300))
    download_count = db.Column(db.Integer, default=0, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("robotics_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    project = db.relationship("RoboticsProject", back_populates="files")


# =====================================================
#  AI PORTFOLIO ANALYZER
# =====================================================

class PortfolioAnalysis(db.Model):
    __tablename__ = "portfolio_analyses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    overall_score = db.Column(db.Integer, default=0)
    portfolio_strength = db.Column(db.Integer, default=0)
    hiring_readiness = db.Column(db.Integer, default=0)
    frontend_score = db.Column(db.Integer, default=0)
    backend_score = db.Column(db.Integer, default=0)
    project_depth = db.Column(db.Integer, default=0)
    ai_ml_score = db.Column(db.Integer, default=0)
    robotics_score = db.Column(db.Integer, default=0)
    open_source_score = db.Column(db.Integer, default=0)
    writing_quality = db.Column(db.Integer, default=0)
    strengths = db.Column(db.Text)  # JSON list
    weaknesses = db.Column(db.Text)  # JSON list
    suggestions = db.Column(db.Text)  # JSON list
    raw_data = db.Column(db.Text)  # Full JSON analysis
    analyzed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("portfolio_analyses", lazy="dynamic", cascade="all, delete-orphan"))


# =====================================================
#  COMMUNITY POSTS
# =====================================================

class CommunityPost(TimestampMixin, db.Model):
    __tablename__ = "community_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    post_type = db.Column(db.String(30), nullable=False, index=True)  # buildlog, launch, collab, showcase, roadmap, goal, milestone
    status = db.Column(db.String(20), default="published", nullable=False, index=True)
    likes_count = db.Column(db.Integer, default=0, nullable=False)
    comments_count = db.Column(db.Integer, default=0, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    author = db.relationship("User", backref=db.backref("community_posts", lazy="dynamic", cascade="all, delete-orphan"))


# =====================================================
#  SECURITY & AUDIT MODELS
# =====================================================

class AuditLog(db.Model):
    """Audit log for security tracking and compliance."""
    
    __tablename__ = "audit_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_username = db.Column(db.String(50), index=True)
    target_id = db.Column(db.Integer, index=True)
    target_type = db.Column(db.String(50))
    description = db.Column(db.String(500))
    ip_address = db.Column(db.String(45), index=True)
    user_agent = db.Column(db.String(500))
    request_path = db.Column(db.String(255))
    request_method = db.Column(db.String(10))
    status_code = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    extra_metadata = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    actor = db.relationship("User", foreign_keys=[actor_id], backref=db.backref("audit_logs", lazy="dynamic"))


class DeletedContent(db.Model):
    """Archive for deleted content with recovery capability."""
    
    __tablename__ = "deleted_content_archive"
    
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(50), nullable=False, index=True)
    content_id = db.Column(db.Integer, nullable=False, index=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    deleted_by_username = db.Column(db.String(50))
    content_data = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.String(255))
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, index=True)
    recovered = db.Column(db.Boolean, default=False, nullable=False)
    recovered_at = db.Column(db.DateTime)
    recovered_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    
    deleted_by = db.relationship("User", foreign_keys=[deleted_by_id], backref=db.backref("deleted_content", lazy="dynamic"))
    recovered_by = db.relationship("User", foreign_keys=[recovered_by_id])
