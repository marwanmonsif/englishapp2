from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from core.extensions import db
from core.models import User, Grade
import secrets, random, string
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('student.dashboard') if current_user.role == 'student' else url_for('teacher.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            if user.is_banned:
                flash('Your account has been banned. Contact your teacher.', 'error')
                return redirect(url_for('auth.login'))

            # Single device check — skip for teacher and moderator
            if user.role == 'student':
                current_ip = get_real_ip()
                if user.last_ip and user.last_ip != current_ip:
                    user.is_banned = True
                    user.last_ip = None
                    db.session.commit()
                    flash('Your account has been banned for logging in from multiple devices. Contact your teacher.', 'error')
                    return redirect(url_for('auth.login'))
                user.last_ip = current_ip
                db.session.commit()

            login_user(user, remember=True)
            if user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            return redirect(url_for('student.dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('student.dashboard'))

    grades = Grade.query.order_by(Grade.order).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        grade_id = request.form.get('grade_id')

        if not all([name, email, password, grade_id]):
            flash('All fields are required.', 'error')
            return render_template('auth/register.html', grades=grades)

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('auth/register.html', grades=grades)

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/register.html', grades=grades)

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            phone=phone,
            grade_id=int(grade_id),
            role='student',
            last_ip=get_real_ip()
        )
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        flash('Account created! Please activate your subscription.', 'success')
        return redirect(url_for('student.activate'))

    return render_template('auth/register.html', grades=grades)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            reset_code = ''.join(random.choices(string.digits, k=6))
            user.reset_token = reset_code
            user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=30)
            db.session.commit()

            try:
                from core.services.email import send_reset_email
                send_reset_email(user.email, user.name, reset_code)
                flash('Reset code sent to your email!', 'success')
            except Exception as e:
                flash('Could not send email. Please contact your teacher.', 'error')
        else:
            flash('If this email is registered, a reset code has been sent.', 'success')

        return redirect(url_for('auth.reset_password'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        code = request.form.get('code', '').strip()
        new_password = request.form.get('new_password', '')

        user = User.query.filter_by(email=email, reset_token=code).first()

        if not user:
            flash('Invalid email or code.', 'error')
            return render_template('auth/reset_password.html')

        if user.reset_token_expiry < datetime.utcnow():
            flash('Reset code has expired. Please request a new one.', 'error')
            return redirect(url_for('auth.forgot_password'))

        if len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/reset_password.html')

        user.password_hash = generate_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        user.last_ip = None  # Reset IP so they can login again
        db.session.commit()

        flash('Password changed successfully! Please login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    if current_user.is_authenticated and current_user.role == 'student':
        current_user.last_ip = None
        db.session.commit()
    logout_user()
    return redirect(url_for('auth.login'))
