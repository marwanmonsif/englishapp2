from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from core.extensions import db
from core.models import User, Grade

auth_bp = Blueprint('auth', __name__)


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
            role='student'
        )
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        flash('Account created! Please activate your subscription.', 'success')
        return redirect(url_for('student.activate'))

    return render_template('auth/register.html', grades=grades)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
