from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from core.extensions import db, socketio
from core.models import ChatMessage, User
from core.services.filter import filter_message
from datetime import datetime


@socketio.on('join')
def on_join(data):
    grade_id = data.get('grade_id')
    if not current_user.is_authenticated:
        return
    join_room(f'grade_{grade_id}')


@socketio.on('leave')
def on_leave(data):
    leave_room(f'grade_{data.get("grade_id")}')


@socketio.on('send_message')
def handle_message(data):
    if not current_user.is_authenticated or current_user.is_banned:
        return

    grade_id = data.get('grade_id')
    content = data.get('content', '').strip()

    if not content or len(content) > 500:
        return

    if str(current_user.grade_id) != str(grade_id) and current_user.role not in ('teacher', 'moderator'):
        return

    filtered_content, violations = filter_message(content)

    msg = ChatMessage(
        sender_id=current_user.id,
        grade_id=grade_id,
        content=filtered_content,
        violations=violations,
        is_deleted=(violations >= 3)
    )
    db.session.add(msg)
    db.session.commit()

    if not msg.is_deleted:
        emit('new_message', {
            'id': msg.id,
            'sender': current_user.name,
            'sender_id': current_user.id,
            'content': filtered_content,
            'time': msg.created_at.strftime('%H:%M'),
            'is_teacher': current_user.role == 'teacher',
            'is_moderator': current_user.role == 'moderator'
        }, room=f'grade_{grade_id}')


@socketio.on('delete_message')
def handle_delete(data):
    if not current_user.is_authenticated or current_user.role not in ('teacher', 'moderator'):
        return
    msg_id = data.get('msg_id')
    msg = ChatMessage.query.get(msg_id)
    if msg:
        msg.is_deleted = True
        db.session.commit()
        emit('message_deleted', {'msg_id': msg_id}, room=f'grade_{msg.grade_id}')
