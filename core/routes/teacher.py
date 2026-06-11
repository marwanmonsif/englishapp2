from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from core.extensions import db
from core.models import (User, Grade, Course, Unit, Lesson, Exam, Question,
                         ExamResult, HomeworkSubmission, Announcement,
                         ChatMessage, SubscriptionCode, MessageReport)
from datetime import datetime, timedelta
import os, json

teacher_bp = Blueprint('teacher', __name__)

ALLOWED_PDF = {'pdf'}

def teacher_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash('Access denied.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@teacher_bp.route('/teacher/dashboard')
@login_required
@teacher_required
def dashboard():
    students = User.query.filter_by(role='student').count()
    courses = Course.query.count()
    exams = Exam.query.count()
    results = ExamResult.query.count()
    recent_students = User.query.filter_by(role='student').order_by(User.created_at.desc()).limit(5).all()
    recent_submissions = HomeworkSubmission.query.order_by(HomeworkSubmission.submitted_at.desc()).limit(5).all()
    reports = MessageReport.query.filter_by(reviewed=False).count()

    return render_template('teacher/dashboard.html',
                           students=students, courses=courses,
                           exams=exams, results=results,
                           recent_students=recent_students,
                           recent_submissions=recent_submissions,
                           reports=reports)


# ─── STUDENTS ──────────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/students')
@login_required
@teacher_required
def students():
    q = request.args.get('q', '')
    query = User.query.filter_by(role='student')
    if q:
        query = query.filter(User.name.ilike(f'%{q}%') | User.email.ilike(f'%{q}%'))
    students = query.order_by(User.created_at.desc()).all()
    subs = {s.used_by: s for s in SubscriptionCode.query.filter(SubscriptionCode.used_by != None).all()}
    return render_template('teacher/students.html', students=students, subs=subs, q=q)


@teacher_bp.route('/teacher/students/<int:student_id>/ban', methods=['POST'])
@login_required
@teacher_required
def ban_student(student_id):
    student = User.query.get_or_404(student_id)
    student.is_banned = not student.is_banned
    db.session.commit()
    flash(f'Student {"banned" if student.is_banned else "unbanned"}.', 'success')
    return redirect(url_for('teacher.students'))


# ─── COURSES ───────────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/courses')
@login_required
@teacher_required
def courses():
    courses = Course.query.order_by(Course.created_at.desc()).all()
    grades = Grade.query.order_by(Grade.order).all()
    return render_template('teacher/courses.html', courses=courses, grades=grades)


@teacher_bp.route('/teacher/courses/add', methods=['POST'])
@login_required
@teacher_required
def add_course():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    grade_id = request.form.get('grade_id')
    if not title or not grade_id:
        flash('Title and grade are required.', 'error')
        return redirect(url_for('teacher.courses'))
    course = Course(title=title, description=description, grade_id=int(grade_id))
    db.session.add(course)
    db.session.commit()
    flash('Course added.', 'success')
    return redirect(url_for('teacher.courses'))


@teacher_bp.route('/teacher/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
@teacher_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    grades = Grade.query.order_by(Grade.order).all()
    if request.method == 'POST':
        course.title = request.form.get('title', course.title).strip()
        course.description = request.form.get('description', course.description).strip()
        course.grade_id = int(request.form.get('grade_id', course.grade_id))
        course.is_published = 'is_published' in request.form
        db.session.commit()
        flash('Course updated.', 'success')
        return redirect(url_for('teacher.courses'))
    return render_template('teacher/edit_course.html', course=course, grades=grades)


@teacher_bp.route('/teacher/courses/<int:course_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted.', 'success')
    return redirect(url_for('teacher.courses'))


@teacher_bp.route('/teacher/courses/<int:course_id>')
@login_required
@teacher_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('teacher/course_detail.html', course=course)


# ─── UNITS ─────────────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/courses/<int:course_id>/units/add', methods=['POST'])
@login_required
@teacher_required
def add_unit(course_id):
    course = Course.query.get_or_404(course_id)
    title = request.form.get('title', '').strip()
    if title:
        order = len(course.units) + 1
        unit = Unit(title=title, description=request.form.get('description', ''), course_id=course_id, order=order)
        db.session.add(unit)
        db.session.commit()
        flash('Unit added.', 'success')
    return redirect(url_for('teacher.course_detail', course_id=course_id))


@teacher_bp.route('/teacher/units/<int:unit_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_unit(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    course_id = unit.course_id
    db.session.delete(unit)
    db.session.commit()
    flash('Unit deleted.', 'success')
    return redirect(url_for('teacher.course_detail', course_id=course_id))


# ─── LESSONS ───────────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/units/<int:unit_id>/lessons/add', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_lesson(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        youtube_url = request.form.get('youtube_url', '').strip()
        description = request.form.get('description', '').strip()
        pdf_filename = None

        if 'pdf_file' in request.files:
            pdf = request.files['pdf_file']
            if pdf and pdf.filename and pdf.filename.rsplit('.', 1)[-1].lower() in ALLOWED_PDF:
                fname = secure_filename(f"lesson_{unit_id}_{datetime.utcnow().timestamp()}_{pdf.filename}")
                pdf.save(os.path.join(current_app.config['PDF_FOLDER'], fname))
                pdf_filename = fname

        order = len(unit.lessons) + 1
        lesson = Lesson(title=title, description=description, unit_id=unit_id,
                        youtube_url=youtube_url, pdf_filename=pdf_filename, order=order)
        db.session.add(lesson)
        db.session.commit()
        flash('Lesson added.', 'success')
        return redirect(url_for('teacher.course_detail', course_id=unit.course_id))

    return render_template('teacher/add_lesson.html', unit=unit)


@teacher_bp.route('/teacher/lessons/<int:lesson_id>/edit', methods=['GET', 'POST'])
@login_required
@teacher_required
def edit_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if request.method == 'POST':
        lesson.title = request.form.get('title', lesson.title).strip()
        lesson.description = request.form.get('description', '').strip()
        lesson.youtube_url = request.form.get('youtube_url', '').strip()

        if 'pdf_file' in request.files:
            pdf = request.files['pdf_file']
            if pdf and pdf.filename and pdf.filename.rsplit('.', 1)[-1].lower() in ALLOWED_PDF:
                fname = secure_filename(f"lesson_{lesson_id}_{datetime.utcnow().timestamp()}_{pdf.filename}")
                pdf.save(os.path.join(current_app.config['PDF_FOLDER'], fname))
                lesson.pdf_filename = fname

        db.session.commit()
        flash('Lesson updated.', 'success')
        return redirect(url_for('teacher.course_detail', course_id=lesson.unit.course_id))

    return render_template('teacher/edit_lesson.html', lesson=lesson)


@teacher_bp.route('/teacher/lessons/<int:lesson_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    course_id = lesson.unit.course_id
    db.session.delete(lesson)
    db.session.commit()
    flash('Lesson deleted.', 'success')
    return redirect(url_for('teacher.course_detail', course_id=course_id))


@teacher_bp.route('/teacher/pdf/<filename>')
@login_required
def serve_pdf(filename):
    return send_from_directory(current_app.config['PDF_FOLDER'], filename)


# ─── EXAMS ─────────────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/exams')
@login_required
@teacher_required
def exams():
    exams = Exam.query.order_by(Exam.created_at.desc()).all()
    grades = Grade.query.order_by(Grade.order).all()
    return render_template('teacher/exams.html', exams=exams, grades=grades)


@teacher_bp.route('/teacher/exams/add', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_exam():
    grades = Grade.query.order_by(Grade.order).all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        grade_id = int(request.form.get('grade_id'))
        duration = int(request.form.get('duration_minutes', 30))
        pass_score = int(request.form.get('pass_score', 60))

        exam = Exam(title=title, grade_id=grade_id, duration_minutes=duration, pass_score=pass_score)
        db.session.add(exam)
        db.session.flush()

        q_texts = request.form.getlist('q_text[]')
        q_a = request.form.getlist('q_a[]')
        q_b = request.form.getlist('q_b[]')
        q_c = request.form.getlist('q_c[]')
        q_d = request.form.getlist('q_d[]')
        q_correct = request.form.getlist('q_correct[]')

        for i, text in enumerate(q_texts):
            if text.strip():
                q = Question(
                    exam_id=exam.id,
                    text=text.strip(),
                    option_a=q_a[i] if i < len(q_a) else '',
                    option_b=q_b[i] if i < len(q_b) else '',
                    option_c=q_c[i] if i < len(q_c) else '',
                    option_d=q_d[i] if i < len(q_d) else '',
                    correct_answer=q_correct[i] if i < len(q_correct) else 'A',
                    order=i + 1
                )
                db.session.add(q)

        db.session.commit()
        flash('Exam created.', 'success')
        return redirect(url_for('teacher.exams'))

    return render_template('teacher/add_exam.html', grades=grades)


@teacher_bp.route('/teacher/exams/<int:exam_id>')
@login_required
@teacher_required
def exam_detail(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    results = ExamResult.query.filter_by(exam_id=exam_id).all()
    return render_template('teacher/exam_detail.html', exam=exam, results=results)


@teacher_bp.route('/teacher/exams/<int:exam_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    db.session.delete(exam)
    db.session.commit()
    flash('Exam deleted.', 'success')
    return redirect(url_for('teacher.exams'))


# ─── SUBSCRIPTIONS ─────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/codes')
@login_required
@teacher_required
def codes():
    codes = SubscriptionCode.query.order_by(SubscriptionCode.created_at.desc()).all()
    grades = Grade.query.order_by(Grade.order).all()
    return render_template('teacher/codes.html', codes=codes, grades=grades)


@teacher_bp.route('/teacher/codes/generate', methods=['POST'])
@login_required
@teacher_required
def generate_codes():
    grade_id = int(request.form.get('grade_id'))
    count = int(request.form.get('count', 1))
    days = int(request.form.get('days', 180))
    grade = Grade.query.get_or_404(grade_id)

    for _ in range(min(count, 50)):
        code_str = SubscriptionCode.generate_code(grade.name)
        while SubscriptionCode.query.filter_by(code=code_str).first():
            code_str = SubscriptionCode.generate_code(grade.name)

        code = SubscriptionCode(
            code=code_str,
            grade_id=grade_id,
            expires_at=datetime.utcnow() + timedelta(days=days)
        )
        db.session.add(code)

    db.session.commit()
    flash(f'{count} code(s) generated.', 'success')
    return redirect(url_for('teacher.codes'))


@teacher_bp.route('/teacher/codes/<int:code_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_code(code_id):
    code = SubscriptionCode.query.get_or_404(code_id)
    db.session.delete(code)
    db.session.commit()
    flash('Code deleted.', 'success')
    return redirect(url_for('teacher.codes'))


# ─── ANNOUNCEMENTS ─────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/announcements')
@login_required
@teacher_required
def announcements():
    ann = Announcement.query.order_by(Announcement.created_at.desc()).all()
    grades = Grade.query.order_by(Grade.order).all()
    return render_template('teacher/announcements.html', announcements=ann, grades=grades)


@teacher_bp.route('/teacher/announcements/add', methods=['POST'])
@login_required
@teacher_required
def add_announcement():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    grade_id = request.form.get('grade_id') or None
    is_pinned = 'is_pinned' in request.form

    ann = Announcement(title=title, content=content,
                       grade_id=int(grade_id) if grade_id else None,
                       is_pinned=is_pinned)
    db.session.add(ann)
    db.session.commit()
    flash('Announcement posted.', 'success')
    return redirect(url_for('teacher.announcements'))


@teacher_bp.route('/teacher/announcements/<int:ann_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_announcement(ann_id):
    ann = Announcement.query.get_or_404(ann_id)
    db.session.delete(ann)
    db.session.commit()
    flash('Announcement deleted.', 'success')
    return redirect(url_for('teacher.announcements'))


# ─── CHAT MODERATION ───────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/chat')
@login_required
@teacher_required
def chat_moderation():
    reports = MessageReport.query.filter_by(reviewed=False).order_by(MessageReport.created_at.desc()).all()
    grades = Grade.query.order_by(Grade.order).all()
    return render_template('teacher/chat_moderation.html', reports=reports, grades=grades)


@teacher_bp.route('/teacher/chat/messages/<int:grade_id>')
@login_required
@teacher_required
def grade_messages(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    messages = ChatMessage.query.filter_by(grade_id=grade_id).order_by(ChatMessage.created_at.desc()).limit(100).all()
    return render_template('teacher/grade_messages.html', grade=grade, messages=messages)


@teacher_bp.route('/teacher/chat/delete/<int:msg_id>', methods=['POST'])
@login_required
@teacher_required
def delete_message(msg_id):
    msg = ChatMessage.query.get_or_404(msg_id)
    msg.is_deleted = True
    db.session.commit()
    return jsonify({'status': 'deleted'})


@teacher_bp.route('/teacher/chat/report/<int:report_id>/review', methods=['POST'])
@login_required
@teacher_required
def review_report(report_id):
    report = MessageReport.query.get_or_404(report_id)
    report.reviewed = True
    db.session.commit()
    return jsonify({'status': 'reviewed'})


# ─── HOMEWORK ──────────────────────────────────────────────────────────────────

@teacher_bp.route('/teacher/homework')
@login_required
@teacher_required
def homework():
    submissions = HomeworkSubmission.query.order_by(HomeworkSubmission.submitted_at.desc()).all()
    return render_template('teacher/homework.html', submissions=submissions)


@teacher_bp.route('/teacher/homework/<int:sub_id>/grade', methods=['POST'])
@login_required
@teacher_required
def grade_homework(sub_id):
    sub = HomeworkSubmission.query.get_or_404(sub_id)
    sub.grade_given = int(request.form.get('grade', 0))
    sub.teacher_note = request.form.get('note', '')
    sub.status = 'graded'
    db.session.commit()
    flash('Homework graded.', 'success')
    return redirect(url_for('teacher.homework'))


@teacher_bp.route('/teacher/homework/download/<filename>')
@login_required
@teacher_required
def download_homework(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


# ─── MODERATOR MANAGEMENT ──────────────────────────────────────────────────────

@teacher_bp.route('/teacher/students/<int:student_id>/make-moderator', methods=['POST'])
@login_required
@teacher_required
def make_moderator(student_id):
    student = User.query.get_or_404(student_id)
    student.role = 'moderator' if student.role == 'student' else 'student'
    db.session.commit()
    flash(f'{"Moderator assigned" if student.role == "moderator" else "Moderator removed"}.', 'success')
    return redirect(url_for('teacher.students'))
