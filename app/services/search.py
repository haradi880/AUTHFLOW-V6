from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Blog, Job, Project, Tag, User


def _is_postgres():
    return db.engine.dialect.name == "postgresql"


def _ordered(model, ids):
    if not ids:
        return []
    rows = {row.id: row for row in model.query.filter(model.id.in_(ids)).all()}
    return [rows[item_id] for item_id in ids if item_id in rows]


def _ids(sql, query, limit):
    rows = db.session.execute(text(sql), {"query": query, "limit": limit}).mappings().all()
    return [row["id"] for row in rows]


def _postgres_search(query, limit):
    blogs = _ordered(
        Blog,
        _ids(
            """
            SELECT b.id
            FROM blogs b
            WHERE b.status = 'published'
              AND (
                (
                  setweight(to_tsvector('english', coalesce(b.title, '')), 'A') ||
                  setweight(to_tsvector('english', coalesce(b.excerpt, '')), 'B') ||
                  setweight(to_tsvector('english', coalesce(b.content, '')), 'C')
                ) @@ websearch_to_tsquery('english', :query)
                OR similarity(b.title, :query) > 0.18
                OR similarity(coalesce(b.excerpt, ''), :query) > 0.12
              )
            ORDER BY
              ts_rank_cd(
                setweight(to_tsvector('english', coalesce(b.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(b.excerpt, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(b.content, '')), 'C'),
                websearch_to_tsquery('english', :query)
              ) + greatest(similarity(b.title, :query), similarity(coalesce(b.excerpt, ''), :query)) DESC,
              b.likes_count DESC,
              b.views_count DESC,
              b.created_at DESC
            LIMIT :limit
            """,
            query,
            limit,
        ),
    )
    projects = _ordered(
        Project,
        _ids(
            """
            SELECT p.id
            FROM projects p
            WHERE p.status = 'published'
              AND (
                (
                  setweight(to_tsvector('english', coalesce(p.title, '')), 'A') ||
                  setweight(to_tsvector('english', coalesce(p.description, '')), 'B')
                ) @@ websearch_to_tsquery('english', :query)
                OR similarity(p.title, :query) > 0.18
                OR similarity(coalesce(p.description, ''), :query) > 0.12
              )
            ORDER BY
              ts_rank_cd(
                setweight(to_tsvector('english', coalesce(p.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(p.description, '')), 'B'),
                websearch_to_tsquery('english', :query)
              ) + greatest(similarity(p.title, :query), similarity(coalesce(p.description, ''), :query)) DESC,
              p.stars_count DESC,
              p.created_at DESC
            LIMIT :limit
            """,
            query,
            limit,
        ),
    )
    jobs = _ordered(
        Job,
        _ids(
            """
            SELECT j.id
            FROM jobs j
            WHERE j.status = 'active'
              AND (
                (
                  setweight(to_tsvector('english', coalesce(j.title, '')), 'A') ||
                  setweight(to_tsvector('english', coalesce(j.description, '')), 'B') ||
                  setweight(to_tsvector('english', coalesce(j.skills_required, '')), 'A') ||
                  setweight(to_tsvector('english', coalesce(j.location, '')), 'C')
                ) @@ websearch_to_tsquery('english', :query)
                OR similarity(j.title, :query) > 0.18
                OR similarity(coalesce(j.skills_required, ''), :query) > 0.12
              )
            ORDER BY
              ts_rank_cd(
                setweight(to_tsvector('english', coalesce(j.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(j.description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(j.skills_required, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(j.location, '')), 'C'),
                websearch_to_tsquery('english', :query)
              ) + greatest(similarity(j.title, :query), similarity(coalesce(j.skills_required, ''), :query)) DESC,
              j.created_at DESC
            LIMIT :limit
            """,
            query,
            limit,
        ),
    )
    users = _ordered(
        User,
        _ids(
            """
            SELECT u.id
            FROM users u
            WHERE u.is_active = true
              AND (
                similarity(u.username, :query) > 0.18
                OR similarity(coalesce(u.full_name, ''), :query) > 0.16
                OR similarity(coalesce(u.headline, ''), :query) > 0.12
                OR similarity(coalesce(u.skills, ''), :query) > 0.12
              )
            ORDER BY
              greatest(
                similarity(u.username, :query),
                similarity(coalesce(u.full_name, ''), :query),
                similarity(coalesce(u.headline, ''), :query),
                similarity(coalesce(u.skills, ''), :query)
              ) DESC,
              u.reputation_points DESC,
              u.xp_total DESC
            LIMIT :limit
            """,
            query,
            limit,
        ),
    )
    tags = _ordered(
        Tag,
        _ids(
            """
            SELECT t.id
            FROM tags t
            WHERE similarity(t.name, :query) > 0.16 OR t.name ILIKE '%' || :query || '%'
            ORDER BY similarity(t.name, :query) DESC, t.name ASC
            LIMIT :limit
            """,
            query,
            limit,
        ),
    )
    return {"blogs": blogs, "projects": projects, "jobs": jobs, "users": users, "tags": tags}


def _fallback_search(query, limit):
    pattern = f"%{query}%"
    blogs = Blog.query.filter(
        Blog.status == "published",
        db.or_(Blog.title.ilike(pattern), Blog.content.ilike(pattern), Blog.excerpt.ilike(pattern), Blog.tags.any(Tag.name.ilike(pattern))),
    ).order_by(Blog.likes_count.desc(), Blog.views_count.desc(), Blog.created_at.desc()).limit(limit).all()
    projects = Project.query.filter(
        Project.status == "published",
        db.or_(Project.title.ilike(pattern), Project.description.ilike(pattern), Project.tags.any(Tag.name.ilike(pattern))),
    ).order_by(Project.stars_count.desc(), Project.created_at.desc()).limit(limit).all()
    jobs = Job.query.filter(
        Job.status == "active",
        db.or_(Job.title.ilike(pattern), Job.description.ilike(pattern), Job.skills_required.ilike(pattern), Job.location.ilike(pattern)),
    ).order_by(Job.created_at.desc()).limit(limit).all()
    users = User.query.filter(
        User.active.is_(True),
        db.or_(User.username.ilike(pattern), User.full_name.ilike(pattern), User.headline.ilike(pattern), User.skills.ilike(pattern)),
    ).order_by(User.reputation_points.desc(), User.xp_total.desc()).limit(limit).all()
    tags = Tag.query.filter(Tag.name.ilike(pattern)).order_by(Tag.name.asc()).limit(limit).all()
    return {"blogs": blogs, "projects": projects, "jobs": jobs, "users": users, "tags": tags}


def search_all(query, limit=10):
    query = (query or "").strip()
    empty = {"blogs": [], "projects": [], "jobs": [], "users": [], "tags": []}
    if len(query) < 2:
        return empty
    if _is_postgres():
        try:
            return _postgres_search(query, limit)
        except SQLAlchemyError:
            db.session.rollback()
            return _fallback_search(query, limit)
    return _fallback_search(query, limit)
