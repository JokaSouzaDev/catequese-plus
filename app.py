from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from functools import wraps
from urllib.parse import unquote
import os
import hashlib

app = Flask(__name__)

database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif database_url and database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

# No Vercel, SQLite serve apenas como fallback de demonstração e não é persistente.
# Em produção, configure DATABASE_URL apontando para PostgreSQL.
if not database_url:
    sqlite_path = '/tmp/catequese-bootstrap.db' if os.environ.get('VERCEL') else 'catequese.db'
    database_url = f'sqlite:///{sqlite_path}'

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or hashlib.sha256(
    (database_url + '|catequese-plus-session-key').encode('utf-8')
).hexdigest()
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('VERCEL'))

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'joka22092008@proton.me').strip().lower()
ADMIN_PASSWORD_HASH = os.environ.get(
    'ADMIN_PASSWORD_HASH',
    'scrypt:32768:8:1$P8Mm6sTvX5GXf8Dy$c2ca2c32c63f0bc691da2275f850f42edddcd96de6a68e61cf4029baac91328728744b3c40ffa44646febc6fa0b5e33765ddd942ddd7cd2119514cb2c890407f'
)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Entre na sua conta para continuar.'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rooms = db.relationship('Room', backref='owner', lazy=True, cascade='all, delete-orphan')

class AccessControl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    consent_tracking = db.Column(db.Boolean, nullable=False, default=False)
    signup_ip = db.Column(db.String(64), default='')
    ip_city = db.Column(db.String(120), default='')
    ip_region = db.Column(db.String(120), default='')
    ip_country = db.Column(db.String(20), default='')
    ip_postal_code = db.Column(db.String(32), default='')
    browser_lat = db.Column(db.String(40), default='')
    browser_lon = db.Column(db.String(40), default='')
    browser_accuracy = db.Column(db.String(40), default='')
    user_agent = db.Column(db.Text, default='')
    device_info = db.Column(db.Text, default='')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime)
    user = db.relationship('User', backref=db.backref('access_control', uselist=False, cascade='all, delete-orphan'))


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), default='')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    students = db.relationship('Student', backref='room', lazy=True, cascade='all, delete-orphan')
    notes = db.relationship('Note', backref='room', lazy=True, cascade='all, delete-orphan')
    attendance_days = db.relationship('AttendanceDay', backref='room', lazy=True, cascade='all, delete-orphan')

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    records = db.relationship('AttendanceRecord', backref='student', lazy=True, cascade='all, delete-orphan')

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)

class AttendanceDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attendance_date = db.Column(db.Date, nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    records = db.relationship('AttendanceRecord', backref='attendance_day', lazy=True, cascade='all, delete-orphan')
    __table_args__ = (db.UniqueConstraint('attendance_date', 'room_id', name='uq_room_attendance_date'),)

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), nullable=False, default='presente')
    justification = db.Column(db.String(500), default='')
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    attendance_day_id = db.Column(db.Integer, db.ForeignKey('attendance_day.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('student_id', 'attendance_day_id', name='uq_student_day'),)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        return view(*args, **kwargs)
    return wrapped

def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.headers.get('X-Real-IP') or request.remote_addr or ''

def get_vercel_geo():
    return {
        'city': unquote(request.headers.get('X-Vercel-IP-City', '') or ''),
        'region': request.headers.get('X-Vercel-IP-Country-Region', '') or '',
        'country': request.headers.get('X-Vercel-IP-Country', '') or '',
        'postal_code': request.headers.get('X-Vercel-IP-Postal-Code', '') or '',
    }

def ensure_access_record(user, default_status='approved'):
    control = AccessControl.query.filter_by(user_id=user.id).first()
    if not control:
        control = AccessControl(
            user_id=user.id,
            status=default_status,
            consent_tracking=False,
            requested_at=datetime.utcnow(),
            reviewed_at=datetime.utcnow() if default_status != 'pending' else None,
        )
        db.session.add(control)
        db.session.commit()
    return control

@app.before_request
def enforce_current_user_access():
    if not current_user.is_authenticated:
        return None
    control = AccessControl.query.filter_by(user_id=current_user.id).first()
    if not control:
        control = ensure_access_record(current_user, 'approved')
    if control.status != 'approved':
        logout_user()
        flash('Seu acesso não está autorizado no momento.', 'error')
        return redirect(url_for('login'))
    return None

def owned_room(room_id):
    room = db.session.get(Room, room_id)
    if not room or room.user_id != current_user.id:
        abort(404)
    return room

@app.route('/api/health')
def health():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({
            'status': 'ok',
            'database': 'postgresql' if database_url.startswith('postgresql') else 'sqlite'
        }), 200
    except Exception as exc:
        return jsonify({'status': 'error', 'database': 'unavailable'}), 503

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        consent = request.form.get('consent_tracking') == 'on'

        if not name or not email or len(password) < 6:
            flash('Preencha os dados e use uma senha com pelo menos 6 caracteres.', 'error')
        elif not consent:
            flash('Para solicitar acesso, é necessário aceitar o registro das informações técnicas descritas.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Este e-mail já possui cadastro ou solicitação de acesso.', 'error')
        else:
            geo = get_vercel_geo()
            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.flush()
            control = AccessControl(
                user_id=user.id,
                status='pending',
                consent_tracking=True,
                signup_ip=get_client_ip(),
                ip_city=geo['city'],
                ip_region=geo['region'],
                ip_country=geo['country'],
                ip_postal_code=geo['postal_code'],
                browser_lat=request.form.get('geo_lat', '').strip(),
                browser_lon=request.form.get('geo_lon', '').strip(),
                browser_accuracy=request.form.get('geo_accuracy', '').strip(),
                user_agent=request.headers.get('User-Agent', ''),
                device_info=request.form.get('device_info', '').strip(),
                requested_at=datetime.utcnow(),
            )
            db.session.add(control)
            db.session.commit()
            return render_template('pending.html', email=email)
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            control = ensure_access_record(user, 'approved')
            if control.status == 'pending':
                flash('Seu cadastro está aguardando aprovação do administrador.', 'error')
                return render_template('login.html')
            if control.status == 'denied':
                flash('Seu acesso foi negado pelo administrador.', 'error')
                return render_template('login.html')
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('E-mail ou senha incorretos.', 'error')
    return render_template('login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_authenticated'):
        return redirect(url_for('admin_panel'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session.clear()
            session['admin_authenticated'] = True
            session['admin_email'] = ADMIN_EMAIL
            return redirect(url_for('admin_panel'))
        flash('Credenciais administrativas inválidas.', 'error')
    return render_template('admin_login.html')

@app.route('/admin')
@admin_required
def admin_panel():
    requests = AccessControl.query.join(User).order_by(
        db.case(
            (AccessControl.status == 'pending', 0),
            (AccessControl.status == 'approved', 1),
            else_=2
        ),
        AccessControl.requested_at.desc()
    ).all()
    return render_template('admin_panel.html', requests=requests)

@app.route('/admin/acesso/<int:control_id>/aprovar', methods=['POST'])
@admin_required
def approve_access(control_id):
    control = db.session.get(AccessControl, control_id)
    if not control:
        abort(404)
    control.status = 'approved'
    control.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f'Acesso de {control.user.name} aprovado.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/acesso/<int:control_id>/negar', methods=['POST'])
@admin_required
def deny_access(control_id):
    control = db.session.get(AccessControl, control_id)
    if not control:
        abort(404)
    control.status = 'denied'
    control.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f'Acesso de {control.user.name} negado.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/sair')
def admin_logout():
    session.pop('admin_authenticated', None)
    session.pop('admin_email', None)
    return redirect(url_for('admin_login'))

@app.route('/sair')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/painel', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        name = request.form['name'].strip()
        description = request.form.get('description', '').strip()
        if name:
            db.session.add(Room(name=name, description=description, user_id=current_user.id))
            db.session.commit()
            flash('Sala criada com sucesso.', 'success')
        return redirect(url_for('dashboard'))
    rooms = Room.query.filter_by(user_id=current_user.id).order_by(Room.id.desc()).all()
    return render_template('dashboard.html', rooms=rooms)

@app.route('/sala/<int:room_id>')
@login_required
def room_detail(room_id):
    room = owned_room(room_id)
    notes = Note.query.filter_by(room_id=room.id).order_by(Note.created_at.desc()).all()
    days = AttendanceDay.query.filter_by(room_id=room.id).order_by(AttendanceDay.attendance_date.desc()).all()
    return render_template('room.html', room=room, notes=notes, days=days)

@app.route('/sala/<int:room_id>/aluno', methods=['POST'])
@login_required
def add_student(room_id):
    room = owned_room(room_id)
    name = request.form['name'].strip()
    if name:
        db.session.add(Student(name=name, room_id=room.id))
        db.session.commit()
        flash('Aluno adicionado.', 'success')
    return redirect(url_for('room_detail', room_id=room.id))

@app.route('/sala/<int:room_id>/anotacao', methods=['POST'])
@login_required
def add_note(room_id):
    room = owned_room(room_id)
    content = request.form['content'].strip()
    if content:
        db.session.add(Note(content=content, room_id=room.id))
        db.session.commit()
        flash('Anotação salva.', 'success')
    return redirect(url_for('room_detail', room_id=room.id))

@app.route('/sala/<int:room_id>/chamada', methods=['GET', 'POST'])
@login_required
def attendance(room_id):
    room = owned_room(room_id)
    selected = request.values.get('date') or date.today().isoformat()
    try:
        selected_date = datetime.strptime(selected, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()

    day = AttendanceDay.query.filter_by(room_id=room.id, attendance_date=selected_date).first()
    if not day:
        day = AttendanceDay(room_id=room.id, attendance_date=selected_date)
        db.session.add(day)
        db.session.flush()

    if request.method == 'POST':
        for student in room.students:
            status = request.form.get(f'status_{student.id}', 'presente')
            justification = request.form.get(f'justification_{student.id}', '').strip()
            record = AttendanceRecord.query.filter_by(student_id=student.id, attendance_day_id=day.id).first()
            if not record:
                record = AttendanceRecord(student_id=student.id, attendance_day_id=day.id)
                db.session.add(record)
            record.status = status
            record.justification = justification if status == 'justificada' else ''
        db.session.commit()
        flash('Chamada registrada com sucesso.', 'success')
        return redirect(url_for('attendance', room_id=room.id, date=selected_date.isoformat()))

    db.session.commit()
    records = {r.student_id: r for r in AttendanceRecord.query.filter_by(attendance_day_id=day.id).all()}
    return render_template('attendance.html', room=room, selected_date=selected_date, records=records)

@app.route('/sala/<int:room_id>/historico/<int:day_id>')
@login_required
def attendance_history(room_id, day_id):
    room = owned_room(room_id)
    day = db.session.get(AttendanceDay, day_id)
    if not day or day.room_id != room.id:
        abort(404)
    records = AttendanceRecord.query.filter_by(attendance_day_id=day.id).all()
    return render_template('history.html', room=room, day=day, records=records)

with app.app_context():
    db.create_all()
    existing_users = User.query.all()
    changed = False
    for existing_user in existing_users:
        if not AccessControl.query.filter_by(user_id=existing_user.id).first():
            db.session.add(AccessControl(
                user_id=existing_user.id,
                status='approved',
                consent_tracking=False,
                requested_at=datetime.utcnow(),
                reviewed_at=datetime.utcnow(),
            ))
            changed = True
    if changed:
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
