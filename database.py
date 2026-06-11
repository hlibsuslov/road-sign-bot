import logging
import sqlite3
import time
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2


class Database:
    """SQLite-шар бота.

    Схема v2:
      meta          — службова таблиця (версія схеми) для контрольованих міграцій
      users         — налаштування користувача
      sign_progress — стан кожного знаку в системі інтервальних повторень
                      (box Лейтнера, лічильники відповідей, розклад повторень)
      daily_stats   — агрегована денна статистика відповідей (для серій та точності)
    """

    def __init__(self, db_path: str = "road_signs_bot.db"):
        self.db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ==================== Схема та міграції ====================

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            row = cursor.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            version = int(row["value"]) if row else 0

            if version < SCHEMA_VERSION:
                logger.info("Міграція БД: v%s -> v%s", version, SCHEMA_VERSION)
                self._migrate(cursor, version)
                cursor.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            conn.commit()

    def _migrate(self, cursor: sqlite3.Cursor, from_version: int):
        # v2: користувачі, прогрес із розкладом повторень, денна статистика
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                study_language TEXT NOT NULL,
                translation_language TEXT NOT NULL,
                theme TEXT NOT NULL DEFAULT 'light',
                selected_category TEXT NOT NULL DEFAULT 'all',
                created_at INTEGER NOT NULL,
                last_active_at INTEGER NOT NULL
            )
        """)
        # стара таблиця users могла бути без нових колонок
        existing_cols = {r["name"] for r in cursor.execute("PRAGMA table_info(users)")}
        if "last_active_at" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN last_active_at INTEGER NOT NULL DEFAULT 0")
        if "theme" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'")
        if "selected_category" not in existing_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN selected_category TEXT NOT NULL DEFAULT 'all'")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sign_progress (
                user_id INTEGER NOT NULL,
                sign_id TEXT NOT NULL,
                box INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                introduced_at INTEGER NOT NULL,
                last_review_at INTEGER,
                next_review_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, sign_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_progress_due
            ON sign_progress (user_id, next_review_at)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                user_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                answered INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day),
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)

        # Перенесення зі старої схеми: learned_signs -> sign_progress (як вивчені)
        has_learned = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='learned_signs'"
        ).fetchone()
        if has_learned:
            now = int(time.time())
            rows = cursor.execute("SELECT user_id, sign_id FROM learned_signs").fetchall()
            for r in rows:
                cursor.execute("""
                    INSERT OR IGNORE INTO sign_progress
                        (user_id, sign_id, box, correct_count, wrong_count,
                         introduced_at, last_review_at, next_review_at)
                    VALUES (?, ?, 4, 1, 0, ?, ?, ?)
                """, (r["user_id"], r["sign_id"], now, now, now + 7 * 86400))
            cursor.execute("DROP TABLE learned_signs")
            logger.info("Перенесено %s записів зі старої таблиці learned_signs", len(rows))

    # ==================== Користувачі ====================

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

    def upsert_user(self, user_id: int, study_language: str, translation_language: str):
        now = int(time.time())
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO users (user_id, study_language, translation_language, created_at, last_active_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    study_language = excluded.study_language,
                    translation_language = excluded.translation_language,
                    last_active_at = excluded.last_active_at
            """, (user_id, study_language, translation_language, now, now))
            conn.commit()

    def touch_user(self, user_id: int):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_active_at = ? WHERE user_id = ?",
                (int(time.time()), user_id),
            )
            conn.commit()

    def update_user_theme(self, user_id: int, theme: str):
        with self.get_connection() as conn:
            conn.execute("UPDATE users SET theme = ? WHERE user_id = ?", (theme, user_id))
            conn.commit()

    def update_user_categories(self, user_id: int, categories: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET selected_category = ? WHERE user_id = ?",
                (categories, user_id),
            )
            conn.commit()

    # ==================== Прогрес вивчення ====================

    def get_progress_map(self, user_id: int) -> Dict[str, sqlite3.Row]:
        """Весь прогрес користувача: sign_id -> рядок прогресу."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sign_progress WHERE user_id = ?", (user_id,)
            ).fetchall()
            return {r["sign_id"]: r for r in rows}

    def get_progress(self, user_id: int, sign_id: str) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM sign_progress WHERE user_id = ? AND sign_id = ?",
                (user_id, sign_id),
            ).fetchone()

    def introduce_sign(self, user_id: int, sign_id: str, box: int, next_review_at: int):
        """Створює запис прогресу для щойно показаного знаку."""
        now = int(time.time())
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO sign_progress
                    (user_id, sign_id, box, introduced_at, next_review_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, sign_id, box, now, next_review_at))
            conn.commit()

    def set_box(self, user_id: int, sign_id: str, box: int, next_review_at: int):
        """Пряме встановлення рівня (наприклад, «вже знаю» на картці)."""
        now = int(time.time())
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO sign_progress
                    (user_id, sign_id, box, introduced_at, last_review_at, next_review_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, sign_id) DO UPDATE SET
                    box = excluded.box,
                    last_review_at = excluded.last_review_at,
                    next_review_at = excluded.next_review_at
            """, (user_id, sign_id, box, now, now, next_review_at))
            conn.commit()

    def record_answer(self, user_id: int, sign_id: str, correct: bool,
                      new_box: int, next_review_at: int):
        """Атомарно фіксує відповідь: прогрес знаку + денна статистика."""
        now = int(time.time())
        today = date.today().isoformat()
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE sign_progress SET
                    box = ?,
                    correct_count = correct_count + ?,
                    wrong_count = wrong_count + ?,
                    last_review_at = ?,
                    next_review_at = ?
                WHERE user_id = ? AND sign_id = ?
            """, (new_box, 1 if correct else 0, 0 if correct else 1,
                  now, next_review_at, user_id, sign_id))
            conn.execute("""
                INSERT INTO daily_stats (user_id, day, answered, correct)
                VALUES (?, ?, 1, ?)
                ON CONFLICT (user_id, day) DO UPDATE SET
                    answered = answered + 1,
                    correct = correct + excluded.correct
            """, (user_id, today, 1 if correct else 0))
            conn.execute(
                "UPDATE users SET last_active_at = ? WHERE user_id = ?", (now, user_id)
            )
            conn.commit()

    def reset_progress(self, user_id: int):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM sign_progress WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM daily_stats WHERE user_id = ?", (user_id,))
            conn.commit()
        logger.info("Прогрес користувача %s скинуто", user_id)

    # ==================== Статистика ====================

    def get_answer_totals(self, user_id: int) -> tuple:
        """(всього відповідей, з них правильних) за весь час."""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(answered), 0) AS answered,
                       COALESCE(SUM(correct), 0) AS correct
                FROM daily_stats WHERE user_id = ?
            """, (user_id,)).fetchone()
            return row["answered"], row["correct"]

    def get_active_days(self, user_id: int) -> List[str]:
        """Дні з активністю (ISO-дати), від нових до старих — для підрахунку серії."""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT day FROM daily_stats
                WHERE user_id = ? AND answered > 0
                ORDER BY day DESC
            """, (user_id,)).fetchall()
            return [r["day"] for r in rows]

    def get_day_stats(self, user_id: int, day: str) -> tuple:
        """(відповідей, правильних) за конкретний день."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT answered, correct FROM daily_stats WHERE user_id = ? AND day = ?",
                (user_id, day),
            ).fetchone()
            return (row["answered"], row["correct"]) if row else (0, 0)
