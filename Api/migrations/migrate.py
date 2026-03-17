"""
Run database migrations for CDP Chatbot (PostgreSQL).

Usage:
    python migrations/migrate.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_db_connection


def run_migration():
    sql_path = os.path.join(os.path.dirname(__file__), "001_create_tables.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute(sql)
        db.commit()
        print("Migration complete — tables created successfully.")
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    run_migration()
