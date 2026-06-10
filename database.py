import sqlite3
from typing import List, Optional, Tuple

class Database:
    def __init__(self, db_path: str = "road_signs_bot.db"):
        self.db_path = db_path
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблиця користувачів
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    study_language TEXT NOT NULL,
                    translation_language TEXT NOT NULL,
                    theme TEXT DEFAULT 'light',
                    selected_category TEXT DEFAULT 'all',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Міграція для існуючих баз даних (додаємо колонки, якщо їх немає)
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'light'")
            except sqlite3.OperationalError:
                pass # Колонка вже існує

            try:
                cursor.execute("ALTER TABLE users ADD COLUMN selected_category TEXT DEFAULT 'all'")
            except sqlite3.OperationalError:
                pass
            
            # Таблиця вивчених знаків
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_signs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    sign_id TEXT NOT NULL,
                    learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(user_id, sign_id)
                )
            """)
            
            conn.commit()
    
    def add_user(self, user_id: int, study_language: str, translation_language: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, study_language, translation_language, theme, selected_category)
                VALUES (?, ?, ?, COALESCE((SELECT theme FROM users WHERE user_id = ?), 'light'), COALESCE((SELECT selected_category FROM users WHERE user_id = ?), 'all'))
            """, (user_id, study_language, translation_language, user_id, user_id))
            conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Tuple]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, study_language, translation_language, theme, selected_category
                FROM users WHERE user_id = ?
            """, (user_id,))
            return cursor.fetchone()
    
    def update_user_theme(self, user_id: int, theme: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET theme = ? WHERE user_id = ?", (theme, user_id))
            conn.commit()

    def update_user_categories(self, user_id: int, categories: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET selected_category = ? WHERE user_id = ?", (categories, user_id))
            conn.commit()

    def update_user_languages(self, user_id: int, study_language: str, translation_language: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET study_language = ?, translation_language = ?
                WHERE user_id = ?
            """, (study_language, translation_language, user_id))
            conn.commit()
    
    def add_learned_sign(self, user_id: int, sign_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO learned_signs (user_id, sign_id)
                VALUES (?, ?)
            """, (user_id, sign_id))
            conn.commit()
    
    def get_learned_signs(self, user_id: int) -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sign_id FROM learned_signs
                WHERE user_id = ?
            """, (user_id,))
            return [row[0] for row in cursor.fetchall()]
    
    def reset_learned_signs(self, user_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM learned_signs WHERE user_id = ?
            """, (user_id,))
            conn.commit()
