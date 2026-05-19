"""Team and collaboration workflows."""

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import ActivityUpdate, CollaborationRequest, Project, Team, TeamInvitation, TeamMember, User
from app.services.content import generate_slug
from app.services.notifications import create_notification
from app.utils.rate_limit import rate_limit

collaboration_bp = Blueprint("collaboration", __name__)

TEAM_ROLES = {"member", "admin", "viewer"}
COLLAB_STATUSES = {"pending", "accepted", "declined", "cancelled"}


@collaboration_bp.get("/collaboration")
@login_required
def hub():
    teams = (
        Team.query.join(TeamMember)
        .filter(TeamMember.user_id == current_user.id)
        .order_by(Team.updated_at.desc())
        .all()
    )
    invitations = TeamInvitation.query.filter_by(invitee_id=current_user.id, status="pending").order_by(TeamInvitation.created_at.desc()).all()
    requests = CollaborationRequest.query.filter_by(recipient_id=current_user.id, status="pending").order_by(CollaborationRequest.created_at.desc()).all()
    sent_requests = CollaborationRequest.query.filter_by(requester_id=current_user.id).order_by(CollaborationRequest.created_at.desc()).limit(10).all()
    return render_template(
        "collaboration/hub.html",
        teams=teams,
        invitations=invitations,
        requests=requests,
        sent_requests=sent_requests,
    )


@collaboration_bp.route("/collaboration/teams/new", methods=["GET", "POST"])
@login_required
@rate_limit(max_calls=10, window_seconds=600, scope="teams")
def create_team():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if len(name) < 2:
            flash("Team name must be at least 2 characters.", "error")
            return render_template("collaboration/team_form.html")
        team = Team(
            name=name,
            slug=generate_slug(name, Team),
            description=description[:500],
            visibility=request.form.get("visibility") if request.form.get("visibility") in {"private", "workspace"} else "private",
            owner_id=current_user.id,
        )
        db.session.add(team)
        db.session.flush()
        db.session.add(TeamMember(team_id=team.id, user_id=current_user.id, role="owner"))
        db.session.add(ActivityUpdate(actor_id=current_user.id, team_id=team.id, action="team_created", summary=f"{current_user.username} created the team."))
        db.session.commit()
        flash("Team workspace created.", "success")
        return redirect(url_for("collaboration.team_detail", slug=team.slug))
    return render_template("collaboration/team_form.html")


@collaboration_bp.get("/collaboration/teams/<slug>")
@login_required
def team_detail(slug):
    team = Team.query.filter_by(slug=slug).first_or_404()
    member = team.member_for(current_user)
    if not member and not current_user.is_admin:
        abort(403)
    activities = team.activities.order_by(ActivityUpdate.created_at.desc()).limit(30).all()
    return render_template("collaboration/team_detail.html", team=team, member=member, activities=activities)


@collaboration_bp.post("/collaboration/teams/<int:team_id>/invite")
@login_required
@rate_limit(max_calls=25, window_seconds=600, scope="team-invites")
def invite_to_team(team_id):
    team = Team.query.get_or_404(team_id)
    if not team.can_manage(current_user):
        abort(403)
    username_or_email = request.form.get("user", "").strip()
    invitee = User.query.filter(db.or_(User.username == username_or_email, User.email == username_or_email)).first()
    if not invitee:
        flash("User not found.", "error")
        return redirect(url_for("collaboration.team_detail", slug=team.slug))
    if team.member_for(invitee):
        flash("That user is already on the team.", "warning")
        return redirect(url_for("collaboration.team_detail", slug=team.slug))
    role = request.form.get("role") if request.form.get("role") in TEAM_ROLES else "member"
    invitation = TeamInvitation(
        team_id=team.id,
        inviter_id=current_user.id,
        invitee_id=invitee.id,
        role=role,
        message=request.form.get("message", "").strip()[:500],
    )
    db.session.add(invitation)
    db.session.flush()
    create_notification(
        invitee,
        "team_invitation",
        f"{current_user.username} invited you to join {team.name}.",
        link=url_for("collaboration.hub"),
        from_user=current_user,
        commit=False,
        priority="high",
        entity_type="team_invitation",
        entity_id=invitation.id,
    )
    db.session.add(ActivityUpdate(actor_id=current_user.id, team_id=team.id, action="team_invite_sent", summary=f"Invitation sent to {invitee.username}."))
    db.session.commit()
    flash("Invitation sent.", "success")
    return redirect(url_for("collaboration.team_detail", slug=team.slug))


@collaboration_bp.post("/collaboration/invitations/<int:invitation_id>/<decision>")
@login_required
def respond_invitation(invitation_id, decision):
    invitation = TeamInvitation.query.get_or_404(invitation_id)
    if invitation.invitee_id != current_user.id:
        abort(403)
    if invitation.status != "pending" or decision not in {"accept", "decline"}:
        flash("This invitation can no longer be changed.", "warning")
        return redirect(url_for("collaboration.hub"))
    invitation.status = "accepted" if decision == "accept" else "declined"
    invitation.responded_at = datetime.utcnow()
    if decision == "accept":
        db.session.add(TeamMember(team_id=invitation.team_id, user_id=current_user.id, role=invitation.role))
        db.session.add(ActivityUpdate(actor_id=current_user.id, team_id=invitation.team_id, action="team_joined", summary=f"{current_user.username} joined the team."))
    db.session.commit()
    flash("Invitation updated.", "success")
    return redirect(url_for("collaboration.hub"))


@collaboration_bp.post("/collaboration/request")
@login_required
@rate_limit(max_calls=20, window_seconds=600, scope="collab-requests")
def create_request():
    recipient = User.query.filter_by(username=request.form.get("recipient", "").strip()).first()
    if not recipient or recipient.id == current_user.id:
        flash("Choose a valid collaborator.", "error")
        return redirect(request.referrer or url_for("collaboration.hub"))
    project = Project.query.filter_by(id=request.form.get("project_id", type=int), user_id=current_user.id).first()
    subject = request.form.get("subject", "").strip()
    if len(subject) < 3:
        flash("Add a clear request subject.", "error")
        return redirect(request.referrer or url_for("collaboration.hub"))
    collab = CollaborationRequest(
        requester_id=current_user.id,
        recipient_id=recipient.id,
        project_id=project.id if project else None,
        subject=subject[:160],
        message=request.form.get("message", "").strip()[:1000],
        requested_role=request.form.get("requested_role", "collaborator").strip()[:60] or "collaborator",
    )
    db.session.add(collab)
    db.session.flush()
    create_notification(
        recipient,
        "collaboration_request",
        f"{current_user.username} sent a collaboration request: {collab.subject}.",
        link=url_for("collaboration.hub"),
        from_user=current_user,
        commit=False,
        priority="high",
        entity_type="collaboration_request",
        entity_id=collab.id,
    )
    db.session.commit()
    flash("Collaboration request sent.", "success")
    return redirect(request.referrer or url_for("collaboration.hub"))


@collaboration_bp.post("/collaboration/requests/<int:request_id>/<decision>")
@login_required
def respond_request(request_id, decision):
    collab = CollaborationRequest.query.get_or_404(request_id)
    if collab.recipient_id != current_user.id:
        abort(403)
    if collab.status != "pending" or decision not in {"accept", "decline"}:
        flash("This request can no longer be changed.", "warning")
        return redirect(url_for("collaboration.hub"))
    collab.status = "accepted" if decision == "accept" else "declined"
    collab.responded_at = datetime.utcnow()
    create_notification(
        collab.requester,
        "collaboration_update",
        f"{current_user.username} {collab.status} your collaboration request: {collab.subject}.",
        link=url_for("collaboration.hub"),
        from_user=current_user,
        commit=False,
        entity_type="collaboration_request",
        entity_id=collab.id,
    )
    db.session.commit()
    flash("Request updated.", "success")
    return redirect(url_for("collaboration.hub"))
