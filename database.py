import logging
import sqlite3
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 4

# Профіль користувача (v4). Лише поля з явною метою: звертання, мова, нагадування у
# зручний час, план підготовки. Без історії імен (references/user-profile.md §0).
PROFILE_COLUMNS = (
    ("first_name", "TEXT"),
    ("last_name", "TEXT"),
    ("username", "TEXT"),
    ("language_code", "TEXT"),
    ("is_tg_premium", "INTEGER NOT NULL DEFAULT 0"),
    ("profile_updated_at", "INTEGER"),
    ("acq_kind", "TEXT NOT NULL DEFAULT 'organic'"),
    ("acq_value", "TEXT"),
    ("timezone", "TEXT"),
    ("reminders", "INTEGER NOT NULL DEFAULT 1"),
    ("licence_class", "TEXT NOT NULL DEFAULT 'B'"),
    ("exam_date", "TEXT"),
    ("daily_goal", "INTEGER NOT NULL DEFAULT 10"),
)
PROFILE_EDITABLE = {"timezone", "reminders", "licence_class", "exam_date", "daily_goal"}


class Database:
    """SQLite-шар бота.

    Схема v2:
      meta          — службова таблиця (версія схеми) для контрольованих міграцій
      users         — налаштування користувача
      sign_progress — стан кожного знаку в системі інтервальних повторень
                      (box Лейтнера, лічильники відповідей, розклад повторень)
      daily_stats   — агрегована денна статистика відповідей (для серій та точності)
    v3:
      payments      — кожен платіж Stars один раз (ключ — telegram_payment_charge_id)
      subscriptions — поточна підписка користувача (термін — з successful_payment)
      exams         — тести в Mini App: питання, відповіді, результат
    v4:
      users + профіль (telegram-bot-ui references/user-profile.md): ім'я, username,
              мова клієнта, звідки прийшов (/start payload), часовий пояс, нагадування,
              категорія прав, дата іспиту, денна мета
      theory_answers — прогрес по питаннях теорії
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

        # v3: оплата Stars і тести
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                charge_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL,
                payload TEXT NOT NULL,
                expires_at INTEGER,
                is_recurring INTEGER NOT NULL DEFAULT 0,
                is_first_recurring INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                refunded_at INTEGER
            )
        """)
        payment_cols = {r["name"] for r in cursor.execute("PRAGMA table_info(payments)")}
        if "refunded_at" not in payment_cols:
            cursor.execute("ALTER TABLE payments ADD COLUMN refunded_at INTEGER")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                charge_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                is_canceled INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                questions TEXT NOT NULL,
                answers TEXT,
                correct INTEGER,
                total INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                finished_at INTEGER
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exams_user ON exams (user_id, created_at)")
        sub_cols = {r["name"] for r in cursor.execute("PRAGMA table_info(subscriptions)")}
        if "first_charge_id" not in sub_cols:
            # the charge that started the subscription: editUserStarSubscription needs it,
            # while charge_id follows the current (renewed) period
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN first_charge_id TEXT")

        # v4: профіль і теорія
        cols = {r["name"] for r in cursor.execute("PRAGMA table_info(users)")}
        for name, ddl in PROFILE_COLUMNS:
            if name not in cols:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS theory_answers (
                user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                last_correct INTEGER NOT NULL DEFAULT 0,
                last_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, question_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        """)

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

    def get_daily_series(self, user_id: int, days: int = 14) -> List[int]:
        """Відповіді за останні `days` днів, від найстарішого до сьогодні (0 — без активності)."""
        today = date.today()
        keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT day, answered FROM daily_stats WHERE user_id = ? AND day >= ?",
                (user_id, keys[0]),
            ).fetchall()
        by_day = {r["day"]: r["answered"] for r in rows}
        return [by_day.get(k, 0) for k in keys]

    def get_day_stats(self, user_id: int, day: str) -> tuple:
        """(відповідей, правильних) за конкретний день."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT answered, correct FROM daily_stats WHERE user_id = ? AND day = ?",
                (user_id, day),
            ).fetchone()
            return (row["answered"], row["correct"]) if row else (0, 0)

    # ==================== Оплата (Stars) ====================

    def record_payment(self, *, charge_id: str, user_id: int, amount: int, currency: str,
                       payload: str, expires_at: Optional[int], is_recurring: bool,
                       is_first_recurring: bool) -> bool:
        """Зберігає платіж. False — цей charge_id уже оброблено (повторна доставка)."""
        with self.get_connection() as conn:
            cur = conn.execute("""
                INSERT OR IGNORE INTO payments
                    (charge_id, user_id, amount, currency, payload, expires_at,
                     is_recurring, is_first_recurring, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (charge_id, user_id, amount, currency, payload, expires_at,
                  int(is_recurring), int(is_first_recurring), int(time.time())))
            conn.commit()
            return cur.rowcount == 1

    def apply_subscription_payment(self, *, charge_id: str, user_id: int, amount: int,
                                   currency: str, payload: str, expires_at: int,
                                   is_recurring: bool, is_first_recurring: bool) -> bool:
        """Payment row and subscription period in one transaction. False = already applied."""
        now = int(time.time())
        with self.get_connection() as conn:
            cur = conn.execute("""
                INSERT OR IGNORE INTO payments
                    (charge_id, user_id, amount, currency, payload, expires_at,
                     is_recurring, is_first_recurring, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (charge_id, user_id, amount, currency, payload, expires_at,
                  int(is_recurring), int(is_first_recurring), now))
            if cur.rowcount != 1:
                return False
            conn.execute("""
                INSERT INTO subscriptions (user_id, charge_id, first_charge_id, expires_at, is_canceled, updated_at)
                VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    charge_id = excluded.charge_id,
                    first_charge_id = CASE WHEN ? THEN excluded.first_charge_id
                                           ELSE COALESCE(subscriptions.first_charge_id, excluded.first_charge_id) END,
                    expires_at = MAX(subscriptions.expires_at, excluded.expires_at),
                    is_canceled = 0,
                    updated_at = excluded.updated_at
            """, (user_id, charge_id, charge_id, expires_at, now, int(is_first_recurring or not is_recurring)))
            conn.commit()
            return True

    def apply_refund(self, user_id: int, charge_id: str) -> bool:
        """A refunded charge ends access now. False = unknown charge or already refunded."""
        now = int(time.time())
        with self.get_connection() as conn:
            cur = conn.execute(
                "UPDATE payments SET refunded_at = ? WHERE charge_id = ? AND user_id = ? AND refunded_at IS NULL",
                (now, charge_id, user_id),
            )
            if cur.rowcount != 1:
                return False
            conn.execute(
                "UPDATE subscriptions SET expires_at = ?, is_canceled = 1, updated_at = ? "
                "WHERE user_id = ? AND charge_id = ?",
                (now - 86400, now, user_id, charge_id),
            )
            conn.commit()
            return True

    def open_exam_count(self, user_id: int, since: int) -> int:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM exams WHERE user_id = ? AND finished_at IS NULL AND created_at > ?",
                (user_id, since),
            ).fetchone()[0]

    def exam_starts_since(self, user_id: int, since: int) -> int:
        """All test attempts (finished or not) since `since` — the daily budget."""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM exams WHERE user_id = ? AND created_at > ?", (user_id, since),
            ).fetchone()[0]

    def purge_old_exams(self, older_than: int) -> int:
        """Retention: tests older than the cutoff are deleted (results live in the chat message)."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM exams WHERE created_at < ?", (older_than,))
            conn.commit()
            return cur.rowcount

    def upsert_subscription(self, user_id: int, charge_id: str, expires_at: int):
        """Новий або продовжений період. Термін береться з successful_payment, не рахується."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO subscriptions (user_id, charge_id, expires_at, is_canceled, updated_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    charge_id = excluded.charge_id,
                    expires_at = MAX(subscriptions.expires_at, excluded.expires_at),
                    is_canceled = 0,
                    updated_at = excluded.updated_at
            """, (user_id, charge_id, expires_at, int(time.time())))
            conn.commit()

    def get_subscription(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
            ).fetchone()

    def set_subscription_canceled(self, user_id: int, canceled: bool):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE subscriptions SET is_canceled = ?, updated_at = ? WHERE user_id = ?",
                (int(canceled), int(time.time()), user_id),
            )
            conn.commit()

    # ==================== Тести (Mini App) ====================

    def create_exam(self, exam_id: str, user_id: int, questions: str, total: int):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO exams (id, user_id, questions, total, created_at) VALUES (?, ?, ?, ?, ?)",
                (exam_id, user_id, questions, total, int(time.time())),
            )
            conn.commit()

    def get_exam(self, exam_id: str) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()

    def finish_exam(self, exam_id: str, answers: str, correct: int) -> bool:
        """Фіксує результат один раз. False — тест уже завершено."""
        with self.get_connection() as conn:
            cur = conn.execute("""
                UPDATE exams SET answers = ?, correct = ?, finished_at = ?
                WHERE id = ? AND finished_at IS NULL
            """, (answers, correct, int(time.time()), exam_id))
            conn.commit()
            return cur.rowcount == 1

    def recent_exams(self, user_id: int, limit: int = 5) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute("""
                SELECT id, correct, total, created_at, finished_at FROM exams
                WHERE user_id = ? AND finished_at IS NOT NULL
                ORDER BY finished_at DESC LIMIT ?
            """, (user_id, limit)).fetchall()

    # ==================== Профіль ====================

    def touch_identity(self, user_id: int, *, first_name: str, last_name: Optional[str],
                       username: Optional[str], language_code: Optional[str], is_premium: bool) -> None:
        """Поточний знімок з Telegram (без історії). Пише лише коли щось змінилося."""
        now = int(time.time())
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE users SET first_name = ?, last_name = ?, username = ?, language_code = ?,
                       is_tg_premium = ?, profile_updated_at = ?, last_active_at = ?
                WHERE user_id = ? AND (
                    first_name IS NOT ? OR last_name IS NOT ? OR username IS NOT ?
                    OR language_code IS NOT ? OR is_tg_premium IS NOT ?)
            """, (first_name, last_name, username, language_code, int(is_premium), now, now,
                  user_id, first_name, last_name, username, language_code, int(is_premium)))
            conn.commit()

    def set_acquisition(self, user_id: int, kind: str, value: Optional[str]) -> None:
        """Звідки прийшов користувач. Пишеться один раз і не перезаписується."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET acq_kind = ?, acq_value = ? WHERE user_id = ? AND acq_kind = 'organic' AND acq_value IS NULL",
                (kind, value, user_id),
            )
            conn.commit()

    def update_profile(self, user_id: int, fields: Dict) -> None:
        fields = {k: v for k, v in fields.items() if k in PROFILE_EDITABLE}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.get_connection() as conn:
            conn.execute(f"UPDATE users SET {sets} WHERE user_id = ?", (*fields.values(), user_id))
            conn.commit()

    def delete_user_data(self, user_id: int) -> None:
        """/deletedata: профіль, прогрес, статистика, тести. Платежі лишаються для обліку."""
        with self.get_connection() as conn:
            for table in ("theory_answers", "exams", "sign_progress", "daily_stats", "users"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            conn.commit()

    # ==================== Теорія ====================

    def record_theory_answer(self, user_id: int, question_id: str, correct: bool) -> None:
        now = int(time.time())
        today = date.today().isoformat()
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO theory_answers (user_id, question_id, correct_count, wrong_count, last_correct, last_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, question_id) DO UPDATE SET
                    correct_count = correct_count + excluded.correct_count,
                    wrong_count = wrong_count + excluded.wrong_count,
                    last_correct = excluded.last_correct,
                    last_at = excluded.last_at
            """, (user_id, question_id, int(correct), int(not correct), int(correct), now))
            conn.execute("""
                INSERT INTO daily_stats (user_id, day, answered, correct) VALUES (?, ?, 1, ?)
                ON CONFLICT (user_id, day) DO UPDATE SET
                    answered = answered + 1, correct = correct + excluded.correct
            """, (user_id, today, int(correct)))
            conn.commit()

    def theory_progress(self, user_id: int) -> Dict[str, sqlite3.Row]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM theory_answers WHERE user_id = ?", (user_id,)
            ).fetchall()
            return {r["question_id"]: r for r in rows}
