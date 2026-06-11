from flask_login import UserMixin
from core.extensions import db
from datetime import datetime
import random, string


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='student')  # student | teacher | moderator
    grade_id = db.Column(db.Integer, db.ForeignKey('grades.id'), nullable=True)
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    is_banned = db.Column(db.Boolean, default=False)
    last_ip = db.Column(db.String(50), nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    seen_announcements = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    grade = db.relationship('Grade', backref='students')
    subscription = db.relationship('SubscriptionCode', backref='student', uselist=False,
                                   primaryjoin="User.id == foreign(SubscriptionCode.used_by)")
    homework_submissions = db.relationship('HomeworkSubmission', backref='student', lazy=True)
    exam_results = db.relationship('ExamResult', backref='student', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='sender', lazy=True)


class Grade(db.Model):
    __tablename__ = 'grades'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    order = db.Column(db.Integer, default=1)
    courses = db.relationship('Course', backref='grade', lazy=True)
    announcements = db.relationship('Announcement', backref='grade', lazy=True)


class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    grade_id = db.Column(db.Integer, db.ForeignKey('grades.id'), nullable=False)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    units = db.relationship('Unit', backref='course', lazy=True, order_by='Unit.order')


class Unit(db.Model):
    __tablename__ = 'units'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    order = db.Column(db.Integer, default=1)
    lessons = db.relationship('Lesson', backref='unit', lazy=True, order_by='Lesson.order')


class Lesson(db.Model):
    __tablename__ = 'lessons'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=False)
    youtube_url = db.Column(db.String(300))
    pdf_filename = db.Column(db.String(200))
    order = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    exams = db.relationship('Exam', backref='lesson', lazy=True)


class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    grade_id = db.Column(db.Integer, db.ForeignKey('grades.id'), nullable=False)
    duration_minutes = db.Column(db.Integer, default=30)
    pass_score = db.Column(db.Integer, default=60)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship('Question', backref='exam', lazy=True, cascade='all, delete-orphan')
    results = db.relationship('ExamResult', backref='exam', lazy=True)
    grade = db.relationship('Grade', backref='exams')


class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(300), nullable=False)
    option_b = db.Column(db.String(300), nullable=False)
    option_c = db.Column(db.String(300), nullable=False)
    option_d = db.Column(db.String(300), nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)
    order = db.Column(db.Integer, default=1)


class ExamResult(db.Model):
    __tablename__ = 'exam_results'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0.0)
    answers = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class HomeworkSubmission(db.Model):
    __tablename__ = 'homework_submissions'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    status = db.Column(db.String(20), default='submitted')
    grade_given = db.Column(db.Integer)
    teacher_note = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    lesson = db.relationship('Lesson', backref='homework_submissions')


class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey('grades.id'), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey('grades.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False)
    violations = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    grade = db.relationship('Grade', backref='chat_messages')
    reports = db.relationship('MessageReport', backref='message', lazy=True)


class MessageReport(db.Model):
    __tablename__ = 'message_reports'
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.String(200))
    reviewed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SubscriptionCode(db.Model):
    __tablename__ = 'subscription_codes'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey('grades.id'), nullable=False)
    used_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    grade = db.relationship('Grade', backref='codes')

    @staticmethod
    def generate_code(grade_name):
        part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"ENG-{part1}-{part2}"

    def is_valid(self):
        return (self.is_active and self.used_by is None and self.expires_at > datetime.utcnow())
