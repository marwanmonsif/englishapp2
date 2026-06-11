from flask import Flask, redirect, url_for
from flask_login import current_user
from core.extensions import db, login_manager, socketio, mail
import os


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///englishapp.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'homework')
    app.config['PDF_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'pdfs')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # Mail config
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'maromonsif1@gmail.com'
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'zpur yzsg amww vdpt').replace(' ', '')
    app.config['MAIL_DEFAULT_SENDER'] = 'maromonsif1@gmail.com'

    # Fix Railway PostgreSQL URL
    db_url = app.config['SQLALCHEMY_DATABASE_URI']
    if db_url.startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace('postgres://', 'postgresql://', 1)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PDF_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app, cors_allowed_origins='*', async_mode='eventlet')
    mail.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    from core.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from datetime import datetime as dt

    @app.context_processor
    def inject_globals():
        return {'now': dt.utcnow()}

    # Blueprints
    from core.routes.auth import auth_bp
    from core.routes.student import student_bp
    from core.routes.teacher import teacher_bp
    import core.routes.chat

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            return redirect(url_for('student.dashboard'))
        return redirect(url_for('auth.login'))

    with app.app_context():
        db.create_all()
        seed_data()

    return app


def seed_data():
    from core.models import User, Grade, Course, Unit, Lesson, Exam, Question, Announcement, SubscriptionCode
    from werkzeug.security import generate_password_hash
    from datetime import datetime, timedelta

    if User.query.count() > 0:
        return

    grades_data = [('First Secondary', 1), ('Second Secondary', 2), ('Third Secondary', 3)]
    grades = []
    for name, order in grades_data:
        g = Grade(name=name, order=order)
        db.session.add(g)
        grades.append(g)
    db.session.flush()

    teacher = User(
        name='Mr. Monsif',
        email='teacher@englishclass.com',
        password_hash=generate_password_hash('teacher123'),
        role='teacher'
    )
    db.session.add(teacher)

    student = User(
        name='Ali Mohamed',
        email='student@demo.com',
        password_hash=generate_password_hash('student123'),
        role='student',
        grade_id=grades[0].id,
        phone='01234567890'
    )
    db.session.add(student)
    db.session.flush()

    sub_code = SubscriptionCode(
        code='ENG-DEMO-2025',
        grade_id=grades[0].id,
        used_by=student.id,
        expires_at=datetime.utcnow() + timedelta(days=365)
    )
    db.session.add(sub_code)

    for i in range(5):
        db.session.add(SubscriptionCode(
            code=SubscriptionCode.generate_code('First'),
            grade_id=grades[0].id,
            expires_at=datetime.utcnow() + timedelta(days=180)
        ))
    for i in range(3):
        db.session.add(SubscriptionCode(
            code=SubscriptionCode.generate_code('Second'),
            grade_id=grades[1].id,
            expires_at=datetime.utcnow() + timedelta(days=180)
        ))

    course = Course(
        title='English Language — Term 1',
        description='Complete English curriculum for First Secondary students.',
        grade_id=grades[0].id,
    )
    db.session.add(course)
    db.session.flush()

    unit1 = Unit(title='Unit 1: Present Tenses', course_id=course.id, order=1)
    unit2 = Unit(title='Unit 2: Vocabulary & Reading', course_id=course.id, order=2)
    db.session.add_all([unit1, unit2])
    db.session.flush()

    l1 = Lesson(title='Present Simple', unit_id=unit1.id, youtube_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', order=1)
    l2 = Lesson(title='Present Continuous', unit_id=unit1.id, youtube_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', order=2)
    l3 = Lesson(title='Reading Comprehension', unit_id=unit2.id, youtube_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', order=1)
    db.session.add_all([l1, l2, l3])
    db.session.flush()

    exam = Exam(title='Unit 1 Quiz', grade_id=grades[0].id, lesson_id=l1.id, duration_minutes=20, pass_score=60)
    db.session.add(exam)
    db.session.flush()

    questions = [
        ('Which sentence is correct?', 'She go to school.', 'She goes to school.', 'She going to school.', 'She goed to school.', 'B'),
        ('Choose the correct form:', 'He is play football now.', 'He plays football now.', 'He is playing football now.', 'He played football now.', 'C'),
        ('The present simple is used for:', 'Actions happening now.', 'Habitual actions.', 'Past completed actions.', 'Future plans only.', 'B'),
        ('Complete: "She ___ English every day."', 'study', 'studies', 'is studying', 'studied', 'B'),
        ('Which is NOT present simple?', 'I work hard.', 'They play tennis.', 'He is sleeping.', 'We eat lunch at noon.', 'C'),
    ]
    for i, (text, a, b, c, d, correct) in enumerate(questions, 1):
        db.session.add(Question(exam_id=exam.id, text=text, option_a=a, option_b=b,
                                option_c=c, option_d=d, correct_answer=correct, order=i))

    db.session.add(Announcement(
        title='Welcome to the New Term! 🎉',
        content='Welcome students! This platform is your go-to resource for all English lessons, exercises, and exams.',
        grade_id=None, is_pinned=True
    ))
    db.session.add(Announcement(
        title='Unit 1 Exam — Date Announced',
        content='The Unit 1 exam will be available online starting next week.',
        grade_id=grades[0].id, is_pinned=False
    ))
    db.session.commit()
