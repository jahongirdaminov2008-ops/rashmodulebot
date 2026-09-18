import sqlite3
from contextlib import closing
from datetime import datetime

from config import DB_PATH


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id  TEXT PRIMARY KEY,
                full_name   TEXT NOT NULL,
                telegram_id INTEGER UNIQUE,
                registered_at TEXT
            );

            CREATE TABLE IF NOT EXISTS tests (
                test_id      TEXT PRIMARY KEY,
                name         TEXT,
                file_id      TEXT,
                open_count   INTEGER DEFAULT 0,
                closed_count INTEGER DEFAULT 0,
                created_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id        TEXT,
                student_id     TEXT,
                open_answers   TEXT,
                closed_answers TEXT,
                submitted_at   TEXT,
                UNIQUE(test_id, student_id)
            );

            CREATE TABLE IF NOT EXISTS results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id     TEXT,
                student_id  TEXT,
                raw_score   INTEGER,
                max_score   INTEGER,
                theta       REAL,
                percent     REAL,
                daraja      TEXT,
                computed_at TEXT,
                UNIQUE(test_id, student_id)
            );
            """
        )
        conn.commit()


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- students ----------

def add_student(student_id: str, full_name: str):
    with closing(_conn()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO students (student_id, full_name, telegram_id, registered_at) "
            "VALUES (?, ?, COALESCE((SELECT telegram_id FROM students WHERE student_id=?), NULL), NULL)",
            (student_id, full_name, student_id),
        )
        conn.commit()


def link_student(student_id: str, telegram_id: int) -> bool:
    with closing(_conn()) as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE student_id=?", (student_id,)
        ).fetchone()
        if row is None or row["telegram_id"] is not None:
            return False
        conn.execute(
            "UPDATE students SET telegram_id=?, registered_at=? WHERE student_id=?",
            (telegram_id, datetime.now().isoformat(), student_id),
        )
        conn.commit()
        return True


def get_student_by_telegram(telegram_id: int):
    with closing(_conn()) as conn:
        return conn.execute(
            "SELECT * FROM students WHERE telegram_id=?", (telegram_id,)
        ).fetchone()


def list_students():
    with closing(_conn()) as conn:
        return conn.execute("SELECT * FROM students ORDER BY student_id").fetchall()


# ---------- tests ----------

def add_test(test_id: str, name: str, file_id: str, open_count: int, closed_count: int):
    with closing(_conn()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tests (test_id, name, file_id, open_count, closed_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (test_id, name, file_id, open_count, closed_count, datetime.now().isoformat()),
        )
        conn.commit()


def get_test(test_id: str):
    with closing(_conn()) as conn:
        return conn.execute("SELECT * FROM tests WHERE test_id=?", (test_id,)).fetchone()


def list_tests():
    with closing(_conn()) as conn:
        return conn.execute("SELECT * FROM tests ORDER BY created_at DESC").fetchall()


# ---------- submissions ----------

def has_submitted(test_id: str, student_id: str) -> bool:
    with closing(_conn()) as conn:
        row = conn.execute(
            "SELECT 1 FROM submissions WHERE test_id=? AND student_id=?",
            (test_id, student_id),
        ).fetchone()
        return row is not None


def save_open_answers(test_id: str, student_id: str, open_answers: str):
    with closing(_conn()) as conn:
        conn.execute(
            "INSERT INTO submissions (test_id, student_id, open_answers, submitted_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(test_id, student_id) DO UPDATE SET open_answers=excluded.open_answers",
            (test_id, student_id, open_answers, datetime.now().isoformat()),
        )
        conn.commit()


def save_closed_answers(test_id: str, student_id: str, closed_answers: str):
    with closing(_conn()) as conn:
        conn.execute(
            "UPDATE submissions SET closed_answers=?, submitted_at=? "
            "WHERE test_id=? AND student_id=?",
            (closed_answers, datetime.now().isoformat(), test_id, student_id),
        )
        conn.commit()


def list_submissions(test_id: str):
    with closing(_conn()) as conn:
        return conn.execute(
            """
            SELECT s.student_id, st.full_name, s.open_answers, s.closed_answers
            FROM submissions s
            JOIN students st ON st.student_id = s.student_id
            WHERE s.test_id = ?
            ORDER BY s.student_id
            """,
            (test_id,),
        ).fetchall()


# ---------- results ----------

def save_results(test_id: str, results: list[dict]):
    with closing(_conn()) as conn:
        for r in results:
            conn.execute(
                "INSERT INTO results (test_id, student_id, raw_score, max_score, theta, percent, daraja, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(test_id, student_id) DO UPDATE SET "
                "raw_score=excluded.raw_score, max_score=excluded.max_score, theta=excluded.theta, "
                "percent=excluded.percent, daraja=excluded.daraja, computed_at=excluded.computed_at",
                (
                    test_id, r["student_id"], r["raw_score"], r["max_score"],
                    r["theta"], r["percent"], r["daraja"], datetime.now().isoformat(),
                ),
            )
        conn.commit()


def get_result(test_id: str, student_id: str):
    with closing(_conn()) as conn:
        return conn.execute(
            "SELECT * FROM results WHERE test_id=? AND student_id=?",
            (test_id, student_id),
        ).fetchone()
