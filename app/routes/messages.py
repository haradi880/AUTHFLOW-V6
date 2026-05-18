"""Messages Routes - Inbox and Direct Messaging."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required
from app.extensions import db
from app.models import User, Message, Block
from app.services.notifications import create_notification
from app.utils.rate_limit import rate_limit
from datetime import datetime
from sqlalchemy import or_, and_

messages_bp = Blueprint('messages', __name__)


def message_payload(message):
    return {
        'id': message.id,
        'content': message.content,
        'sender_id': message.sender_id,
        'is_read': message.is_read,
        'created_at': message.created_at.isoformat() + 'Z',
    }

@messages_bp.route('/messages')
@login_required
def inbox():
    """Display list of conversations."""
    # Get all users the current user has exchanged messages with
    sent_to = db.session.query(Message.recipient_id).filter_by(sender_id=current_user.id)
    received_from = db.session.query(Message.sender_id).filter_by(recipient_id=current_user.id)
    
    user_ids = [uid[0] for uid in sent_to.union(received_from).all()]
    conversations = []
    
    for uid in user_ids:
        user = User.query.get(uid)
        if not user: continue
        
        # Get last message
        last_msg = Message.query.filter(
            or_(
                and_(Message.sender_id == current_user.id, Message.recipient_id == user.id),
                and_(Message.sender_id == user.id, Message.recipient_id == current_user.id)
            )
        ).order_by(Message.created_at.desc()).first()
        
        # Get unread count
        unread_count = Message.query.filter_by(
            sender_id=user.id, 
            recipient_id=current_user.id, 
            is_read=False
        ).count()
        
        conversations.append({
            'user': user,
            'last_message': last_msg,
            'unread_count': unread_count
        })
    
    # Sort by last message time
    conversations.sort(key=lambda x: x['last_message'].created_at if x['last_message'] else datetime.min, reverse=True)
    
    return render_template('messages/inbox.html', conversations=conversations)

@messages_bp.route('/messages/<username>')
@login_required
def chat(username):
    """Chat with a specific user."""
    other_user = User.query.filter_by(username=username).first_or_404()
    
    if other_user.id == current_user.id:
        flash("You cannot chat with yourself.", "info")
        return redirect(url_for('messages.inbox'))
    if Block.query.filter_by(blocker_id=other_user.id, blocked_id=current_user.id).first():
        flash("This user is not available for messages.", "error")
        return redirect(url_for('messages.inbox'))
        
    # Mark messages as read
    Message.query.filter_by(
        sender_id=other_user.id, 
        recipient_id=current_user.id, 
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    
    # Get messages
    last_id = request.args.get('last_id', 0, type=int)
    
    query = Message.query.filter(
        or_(
            and_(Message.sender_id == current_user.id, Message.recipient_id == other_user.id),
            and_(Message.sender_id == other_user.id, Message.recipient_id == current_user.id)
        )
    )
    
    if last_id > 0:
        query = query.filter(Message.id > last_id)
        
    messages = query.order_by(Message.created_at.asc()).all()
    
    # AJAX check for new messages
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax'):
        return jsonify({
            'messages': [message_payload(m) for m in messages]
        })
    
    return render_template('messages/chat.html', other_user=other_user, messages=messages)

@messages_bp.route('/messages/send', methods=['POST'])
@login_required
@rate_limit(max_calls=30, window_seconds=60, scope="messages")
def send_message():
    """Send a message (AJAX or form)."""
    recipient_id = request.form.get('recipient_id', type=int)
    content = request.form.get('content', '').strip()
    
    if not recipient_id or not content:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Invalid data'}), 400
        flash("Invalid message data.", "error")
        return redirect(request.referrer or url_for('messages.inbox'))
        
    recipient = User.query.get_or_404(recipient_id)
    if recipient.id == current_user.id:
        return jsonify({'error': 'Cannot message yourself'}), 400
    if Block.query.filter_by(blocker_id=recipient.id, blocked_id=current_user.id).first():
        return jsonify({'error': 'This user is not available for messages'}), 403
    if recipient.message_permission == 'none':
        return jsonify({'error': 'This user is not accepting messages'}), 403
    if recipient.message_permission == 'followers' and not recipient.is_following(current_user):
        return jsonify({'error': 'Only followers can message this user'}), 403
    
    message = Message(
        sender_id=current_user.id,
        recipient_id=recipient.id,
        content=content
    )
    
    db.session.add(message)
    db.session.commit()
    create_notification(
        user=recipient,
        action='message',
        message=f'{current_user.username} sent you a message',
        link=url_for('messages.chat', username=current_user.username),
        from_user=current_user,
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'sent',
            'message': message_payload(message)
        })
        
    return redirect(url_for('messages.chat', username=recipient.username))
