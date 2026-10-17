"""Работа с базой данных SQLite."""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))  # куда класть БД и файлы
DB_PATH = DATA_DIR / "school.db"
UPLOAD_DIR = DATA_DIR / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT 'Другое',
    role TEXT NOT NULL DEFAULT 'teacher',      -- teacher | admin
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    kind TEXT NOT NULL,                        -- olympiad | contest | development | event | other
    description TEXT NOT NULL DEFAULT '',
    event_date TEXT,                           -- дата мероприятия, YYYY-MM-DD
    deadline TEXT,                             -- срок подачи заявок, YYYY-MM-DD
    link TEXT,                                 -- внешняя ссылка
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | approved | rejected
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    student_class TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    token TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin123"  # первый вход — смените пароль в профиле


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        exists = conn.execute(
            "SELECT 1 FROM users WHERE login = ?", (ADMIN_LOGIN,)
        ).fetchone()
        if not exists:
            from . import security

            conn.execute(
                "INSERT INTO users (login, password_hash, full_name, subject, role) "
                "VALUES (?, ?, ?, ?, 'admin')",
                (ADMIN_LOGIN, security.hash_password(ADMIN_PASSWORD),
                 "Администратор школы", "Другое"),
            )
        conn.commit()
    finally:
        conn.close()
