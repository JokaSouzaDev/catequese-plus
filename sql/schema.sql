-- Catequese+ PostgreSQL schema
CREATE TABLE IF NOT EXISTS "user" (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(180) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS room (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(255) DEFAULT '',
  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student (
  id SERIAL PRIMARY KEY,
  name VARCHAR(140) NOT NULL,
  room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS note (
  id SERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance_day (
  id SERIAL PRIMARY KEY,
  attendance_date DATE NOT NULL,
  room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
  CONSTRAINT uq_room_attendance_date UNIQUE (attendance_date, room_id)
);

CREATE TABLE IF NOT EXISTS attendance_record (
  id SERIAL PRIMARY KEY,
  status VARCHAR(20) NOT NULL DEFAULT 'presente',
  justification VARCHAR(500) DEFAULT '',
  student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
  attendance_day_id INTEGER NOT NULL REFERENCES attendance_day(id) ON DELETE CASCADE,
  CONSTRAINT uq_student_day UNIQUE (student_id, attendance_day_id)
);

CREATE INDEX IF NOT EXISTS idx_room_user_id ON room(user_id);
CREATE INDEX IF NOT EXISTS idx_student_room_id ON student(room_id);
CREATE INDEX IF NOT EXISTS idx_note_room_id ON note(room_id);
CREATE INDEX IF NOT EXISTS idx_attendance_day_room_id ON attendance_day(room_id);
CREATE INDEX IF NOT EXISTS idx_attendance_record_day_id ON attendance_record(attendance_day_id);
CREATE INDEX IF NOT EXISTS idx_attendance_record_student_id ON attendance_record(student_id);
