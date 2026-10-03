from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
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
    if os.environ.get('VERCEL'):
        raise RuntimeError('DATABASE_URL is required in Vercel production.')
    database_url = 'sqlite:///catequese.db'

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or hashlib.sha256(
    (database_url + '|catequese-plus-session-key').encode('utf-8')
).hexdigest()
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('VERCEL'))

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
        if not name or not email or len(password) < 6:
            flash('Preencha os dados e use uma senha com pelo menos 6 caracteres.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'error')
        else:
            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('dashboard'))
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
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('E-mail ou senha incorretos.', 'error')
    return render_template('login.html')

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

if __name__ == '__main__':
    app.run(debug=True)
