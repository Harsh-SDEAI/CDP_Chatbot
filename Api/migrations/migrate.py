"""
Run database migrations for CDP Chatbot.

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
        full_sql = f.read()

    # Split on GO statements (SQL Server batch separator)
    batches = [b.strip() for b in full_sql.split("\nGO") if b.strip()]

    db = get_db_connection()
    cursor = db.cursor()

    for i, batch in enumerate(batches, 1):
        if not batch or batch.isspace():
            continue
        try:
            cursor.execute(batch)
            db.commit()
            print(f"Batch {i}: OK")
        except Exception as e:
            print(f"Batch {i}: {e}")
            db.rollback()

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    run_migration()
