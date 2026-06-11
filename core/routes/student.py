from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from core.extensions import db
from core.models import (User, Grade, Course, Unit, Lesson, Exam, Question,
                         ExamResult, HomeworkSubmission, Announcement,
                         ChatMessage, SubscriptionCode, MessageReport)
from datetime import datetime
import os, json

student_bp = Blueprint('student', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def subscription_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role == 'teacher':
            return f(*args, **kwargs)
        sub = SubscriptionCode.query.filter_by(used_by=current_user.id).first()
        if not sub or sub.expires_at < datetime.utcnow():
            flash('Please activate your subscription to access content.', 'error')
            return redirect(url_for('student.activate'))
        return f(*args, **kwargs)
    return decorated


@student_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'teacher':
        return redirect(url_for('teacher.dashboard'))

    sub = SubscriptionCode.query.filter_by(used_by=current_user.id).first()
    is_subscribed = sub and sub.expires_at > datetime.utcnow()

    announcements = Announcement.query.filter(
        (Announcement.grade_id == current_user.grade_id) |
        (Announcement.grade_id == None)
    ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(5).all()

    courses = Course.query.filter_by(grade_id=current_user.grade_id, is_published=True).all()
    results = ExamResult.query.filter_by(student_id=current_user.id).all()

    return render_template('student/dashboard.html',
                           is_subscribed=is_subscribed,
                           sub=sub,
                           announcements=announcements,
                           courses=courses,
                           results=results)


@student_bp.route('/activate', methods=['GET', 'POST'])
@login_required
def activate():
    if request.method == 'POST':
        code_str = request.form.get('code', '').strip().upper()
        code = SubscriptionCode.query.filter_by(code=code_str).first()

        if not code:
            flash('Invalid activation code.', 'error')
        elif not code.is_valid():
            flash('This code is expired or already used.', 'error')
        elif code.grade_id != current_user.grade_id:
            flash('This code is not for your grade.', 'error')
        else:
            code.used_by = current_user.id
            code.is_active = True
            db.session.commit()
            flash('Subscription activated successfully!', 'success')
            return redirect(url_for('student.dashboard'))

    existing = SubscriptionCode.query.filter_by(used_by=current_user.id).first()
    return render_template('student/activate.html', existing=existing)


@student_bp.route('/courses')
@login_required
@subscription_required
def courses():
    courses = Course.query.filter_by(grade_id=current_user.grade_id, is_published=True).all()
    return render_template('student/courses.html', courses=courses)


@student_bp.route('/course/<int:course_id>')
@login_required
@subscription_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    if course.grade_id != current_user.grade_id and current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('student.courses'))
    return render_template('student/course_detail.html', course=course)


@student_bp.route('/lesson/<int:lesson_id>')
@login_required
@subscription_required
def lesson_detail(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    submission = HomeworkSubmission.query.filter_by(
        student_id=current_user.id, lesson_id=lesson_id).first()
    exams = Exam.query.filter_by(lesson_id=lesson_id, is_published=True).all()
    completed_exam_ids = [r.exam_id for r in ExamResult.query.filter_by(student_id=current_user.id).all()]

    youtube_embed = None
    if lesson.youtube_url:
        vid_id = extract_youtube_id(lesson.youtube_url)
        if vid_id:
            youtube_embed = f"https://www.youtube.com/embed/{vid_id}"

    return render_template('student/lesson_detail.html',
                           lesson=lesson,
                           submission=submission,
                           exams=exams,
                           completed_exam_ids=completed_exam_ids,
                           youtube_embed=youtube_embed)


def extract_youtube_id(url):
    import re
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


@student_bp.route('/lesson/<int:lesson_id>/submit-homework', methods=['POST'])
@login_required
@subscription_required
def submit_homework(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('student.lesson_detail', lesson_id=lesson_id))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('student.lesson_detail', lesson_id=lesson_id))

    if file and allowed_file(file.filename):
        original = file.filename
        filename = secure_filename(f"{current_user.id}_{lesson_id}_{datetime.utcnow().timestamp()}_{file.filename}")
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)

        existing = HomeworkSubmission.query.filter_by(
            student_id=current_user.id, lesson_id=lesson_id).first()
        if existing:
            existing.filename = filename
            existing.original_name = original
            existing.submitted_at = datetime.utcnow()
            existing.status = 'submitted'
        else:
            sub = HomeworkSubmission(
                student_id=current_user.id,
                lesson_id=lesson_id,
                filename=filename,
                original_name=original
            )
            db.session.add(sub)
        db.session.commit()
        flash('Homework submitted successfully!', 'success')
    else:
        flash('Invalid file type. Only PDF, JPG, PNG allowed.', 'error')

    return redirect(url_for('student.lesson_detail', lesson_id=lesson_id))


@student_bp.route('/exam/<int:exam_id>', methods=['GET'])
@login_required
@subscription_required
def take_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if exam.grade_id != current_user.grade_id:
        flash('Access denied.', 'error')
        return redirect(url_for('student.dashboard'))

    already = ExamResult.query.filter_by(student_id=current_user.id, exam_id=exam_id).first()
    if already:
        return redirect(url_for('student.exam_result', result_id=already.id))

    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.order).all()
    return render_template('student/exam.html', exam=exam, questions=questions)


@student_bp.route('/exam/<int:exam_id>/submit', methods=['POST'])
@login_required
@subscription_required
def submit_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    already = ExamResult.query.filter_by(student_id=current_user.id, exam_id=exam_id).first()
    if already:
        return redirect(url_for('student.exam_result', result_id=already.id))

    questions = Question.query.filter_by(exam_id=exam_id).all()
    score = 0
    answers = {}

    for q in questions:
        ans = request.form.get(f'q_{q.id}', '')
        answers[str(q.id)] = ans
        if ans.upper() == q.correct_answer.upper():
            score += 1

    total = len(questions)
    percentage = (score / total * 100) if total > 0 else 0

    result = ExamResult(
        student_id=current_user.id,
        exam_id=exam_id,
        score=score,
        total=total,
        percentage=percentage,
        answers=json.dumps(answers)
    )
    db.session.add(result)
    db.session.commit()

    return redirect(url_for('student.exam_result', result_id=result.id))


@student_bp.route('/result/<int:result_id>')
@login_required
def exam_result(result_id):
    result = ExamResult.query.get_or_404(result_id)
    if result.student_id != current_user.id and current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('student.dashboard'))

    questions = Question.query.filter_by(exam_id=result.exam_id).order_by(Question.order).all()
    answers = json.loads(result.answers) if result.answers else {}
    return render_template('student/result.html', result=result, questions=questions, answers=answers)


@student_bp.route('/exams')
@login_required
@subscription_required
def exams():
    all_exams = Exam.query.filter_by(grade_id=current_user.grade_id, is_published=True).all()
    completed = {r.exam_id: r for r in ExamResult.query.filter_by(student_id=current_user.id).all()}
    return render_template('student/exams.html', exams=all_exams, completed=completed)


@student_bp.route('/chat')
@login_required
@subscription_required
def chat():
    grade = Grade.query.get(current_user.grade_id)
    messages = ChatMessage.query.filter_by(
        grade_id=current_user.grade_id, is_deleted=False
    ).order_by(ChatMessage.created_at.desc()).limit(50).all()
    messages.reverse()
    return render_template('student/chat.html', grade=grade, messages=messages)


@student_bp.route('/chat/report/<int:msg_id>', methods=['POST'])
@login_required
def report_message(msg_id):
    msg = ChatMessage.query.get_or_404(msg_id)
    existing = MessageReport.query.filter_by(message_id=msg_id, reporter_id=current_user.id).first()
    if not existing:
        report = MessageReport(
            message_id=msg_id,
            reporter_id=current_user.id,
            reason=request.form.get('reason', 'Inappropriate content')
        )
        db.session.add(report)
        db.session.commit()
    return jsonify({'status': 'reported'})


@student_bp.route('/announcements')
@login_required
@subscription_required
def announcements():
    ann = Announcement.query.filter(
        (Announcement.grade_id == current_user.grade_id) |
        (Announcement.grade_id == None)
    ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()
    return render_template('student/announcements.html', announcements=ann)


@student_bp.route('/announcements/mark-seen', methods=['POST'])
@login_required
def mark_announcement_seen():
    from flask import jsonify
    ann_id = request.json.get('id')
    seen = current_user.seen_announcements or ''
    ids = seen.split(',') if seen else []
    if str(ann_id) not in ids:
        ids.append(str(ann_id))
        current_user.seen_announcements = ','.join(ids)
        db.session.commit()
    return jsonify({'status': 'ok'})
