"""AI Portfolio Analyzer blueprint — profile scoring, recommendations."""

import json
from flask import Blueprint, render_template, jsonify
from flask_login import current_user, login_required

from app.extensions import db
from app.models import User, Blog, Project, DevLog, PortfolioAnalysis, RoboticsProject
from datetime import datetime

analyzer_bp = Blueprint("analyzer", __name__)


def _compute_analysis(user):
    """Compute portfolio scores based on user profile, content, and activity."""
    blogs = Blog.query.filter_by(user_id=user.id, status="published").all()
    projects = Project.query.filter_by(user_id=user.id, status="published").all()
    devlogs = DevLog.query.filter_by(user_id=user.id).count()
    robotics = RoboticsProject.query.filter_by(user_id=user.id, status="published").count()

    # Profile completeness
    profile_pct = user.profile_completion()

    # Portfolio strength (content volume + quality signals)
    blog_score = min(100, len(blogs) * 12 + sum(b.likes_count for b in blogs) * 2)
    project_score = min(100, len(projects) * 15 + sum(p.stars_count for p in projects) * 3)

    # Hiring readiness
    hire_checks = [
        bool(user.full_name),
        bool(user.headline),
        bool(user.bio and len(user.bio) >= 40),
        bool(user.resume_url),
        bool(user.github),
        bool(user.linkedin),
        len(user.get_skills_list()) >= 3,
        len(projects) >= 1,
        len(blogs) >= 1,
        bool(user.avatar and user.avatar != "default.jpg"),
    ]
    hiring_readiness = round(sum(hire_checks) / len(hire_checks) * 100)

    # Tech domain scores
    all_tags = set()
    for b in blogs:
        all_tags.update(t.name.lower() for t in b.tags)
    for p in projects:
        all_tags.update(t.name.lower() for t in p.tags)

    frontend_keywords = {"react", "vue", "angular", "css", "html", "javascript", "typescript", "nextjs", "tailwind", "frontend"}
    backend_keywords = {"python", "flask", "django", "node", "express", "api", "backend", "database", "sql", "graphql"}
    aiml_keywords = {"ai", "ml", "machine-learning", "deep-learning", "tensorflow", "pytorch", "neural", "nlp", "cv", "data-science"}
    robotics_keywords = {"ros", "arduino", "esp32", "embedded", "robotics", "slam", "iot", "raspberry-pi", "sensor", "actuator"}
    opensource_keywords = {"open-source", "github", "contribution", "oss"}

    frontend_score = min(100, len(all_tags & frontend_keywords) * 25)
    backend_score = min(100, len(all_tags & backend_keywords) * 25)
    aiml_score = min(100, len(all_tags & aiml_keywords) * 25)
    robotics_score_val = min(100, len(all_tags & robotics_keywords) * 20 + robotics * 15)
    opensource_score = min(100, len(all_tags & opensource_keywords) * 30 + (30 if user.github else 0))

    # Writing quality (proxy via blog engagement)
    avg_engagement = 0
    if blogs:
        avg_engagement = sum(b.likes_count + b.comments_count for b in blogs) / len(blogs)
    writing_quality = min(100, int(avg_engagement * 8) + (20 if len(blogs) >= 3 else 0))

    # Project depth
    project_depth = min(100, project_score // 2 + (15 if any(p.github_url for p in projects) else 0) + (15 if any(p.demo_url for p in projects) else 0))

    # Overall
    overall = round(
        profile_pct * 0.15 +
        blog_score * 0.15 +
        project_score * 0.20 +
        hiring_readiness * 0.15 +
        writing_quality * 0.10 +
        (frontend_score + backend_score) / 2 * 0.10 +
        project_depth * 0.15
    )

    # Build suggestions
    suggestions = []
    if profile_pct < 90:
        suggestions.append("Complete your profile to 90%+ for maximum visibility.")
    if not user.resume_url:
        suggestions.append("Add a resume link to improve hiring readiness.")
    if len(blogs) < 3:
        suggestions.append("Publish at least 3 blogs to demonstrate writing ability.")
    if len(projects) < 2:
        suggestions.append("Showcase at least 2 projects with descriptions.")
    if not user.github:
        suggestions.append("Link your GitHub to boost open-source credibility.")
    if not any(p.demo_url for p in projects):
        suggestions.append("Add live demo links to your projects.")
    if devlogs < 5:
        suggestions.append("Post DevLogs regularly to show consistency.")
    if robotics == 0 and robotics_keywords & all_tags:
        suggestions.append("Upload dedicated robotics projects to the Robotics Hub.")

    # Strengths
    strengths = []
    if profile_pct >= 90:
        strengths.append("Complete, professional profile")
    if len(blogs) >= 5:
        strengths.append("Strong writing portfolio")
    if len(projects) >= 3:
        strengths.append("Multiple shipped projects")
    if user.github:
        strengths.append("Active GitHub presence")
    if avg_engagement >= 5:
        strengths.append("High community engagement")

    weaknesses = []
    if profile_pct < 60:
        weaknesses.append("Incomplete profile")
    if len(blogs) == 0:
        weaknesses.append("No published blogs")
    if len(projects) == 0:
        weaknesses.append("No published projects")

    return PortfolioAnalysis(
        user_id=user.id,
        overall_score=overall,
        portfolio_strength=round((blog_score + project_score) / 2),
        hiring_readiness=hiring_readiness,
        frontend_score=frontend_score,
        backend_score=backend_score,
        project_depth=project_depth,
        ai_ml_score=aiml_score,
        robotics_score=robotics_score_val,
        open_source_score=opensource_score,
        writing_quality=writing_quality,
        strengths=json.dumps(strengths),
        weaknesses=json.dumps(weaknesses),
        suggestions=json.dumps(suggestions),
        analyzed_at=datetime.utcnow(),
    )


@analyzer_bp.get("/analyzer")
@login_required
def dashboard():
    analysis = PortfolioAnalysis.query.filter_by(user_id=current_user.id).order_by(PortfolioAnalysis.analyzed_at.desc()).first()
    return render_template("analyzer/dashboard.html", analysis=analysis)


@analyzer_bp.post("/analyzer/run")
@login_required
def run_analysis():
    analysis = _compute_analysis(current_user)
    db.session.add(analysis)
    current_user.portfolio_score = analysis.overall_score
    current_user.last_analyzed_at = analysis.analyzed_at
    db.session.commit()
    return {"status": "ok", "score": analysis.overall_score}


@analyzer_bp.get("/api/analyzer/scores")
@login_required
def get_scores():
    analysis = PortfolioAnalysis.query.filter_by(user_id=current_user.id).order_by(PortfolioAnalysis.analyzed_at.desc()).first()
    if not analysis:
        return {"error": "No analysis found. Run an analysis first."}, 404
    return {
        "overall": analysis.overall_score,
        "portfolio_strength": analysis.portfolio_strength,
        "hiring_readiness": analysis.hiring_readiness,
        "frontend": analysis.frontend_score,
        "backend": analysis.backend_score,
        "project_depth": analysis.project_depth,
        "ai_ml": analysis.ai_ml_score,
        "robotics": analysis.robotics_score,
        "open_source": analysis.open_source_score,
        "writing": analysis.writing_quality,
        "strengths": json.loads(analysis.strengths or "[]"),
        "weaknesses": json.loads(analysis.weaknesses or "[]"),
        "suggestions": json.loads(analysis.suggestions or "[]"),
    }
