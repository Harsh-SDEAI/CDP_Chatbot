"""
Migration script — Creates the Concierge_Chatbot database and chat_history table
in SQL Server.

Usage:
  1. Set MSSQL_CONN_STR in your .env file (see .env.example)
  2. Run:  python migrate_chat_history.py
"""

import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()


def run_migration():
    conn_str = os.getenv("MSSQL_CONN_STR")
    if not conn_str:
        print("ERROR: MSSQL_CONN_STR not found in .env file.")
        print("Copy .env.example to .env and fill in your connection string.")
        return

    # ── Step 1: Connect to master to create the database if needed ────────
    # Build a master connection string by replacing the DATABASE part
    master_conn_str = conn_str.replace("DATABASE=Concierge_Chatbot", "DATABASE=master")

    print("[1/3] Connecting to SQL Server (master)...")
    try:
        master_conn = pyodbc.connect(master_conn_str, autocommit=True)
        cursor = master_conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT name FROM sys.databases WHERE name = 'Concierge_Chatbot'"
        )
        if cursor.fetchone() is None:
            print("[2/3] Creating database Concierge_Chatbot...")
            cursor.execute("CREATE DATABASE Concierge_Chatbot")
            print("       Database created.")
        else:
            print("[2/3] Database Concierge_Chatbot already exists. Skipping.")

        master_conn.close()
    except Exception as e:
        print(f"ERROR connecting to master: {e}")
        print("If the database already exists, this is fine — continuing...")

    # ── Step 2: Connect to Concierge_Chatbot and create the table ─────────
    print("[3/3] Creating chat_history table...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_NAME = 'chat_history'"
        )
        if cursor.fetchone() is None:
            cursor.execute("""
                CREATE TABLE chat_history (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    session_id VARCHAR(36) NOT NULL,
                    question NVARCHAR(MAX) NOT NULL,
                    answer NVARCHAR(MAX) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    user_name NVARCHAR(255) DEFAULT 'Anonymous',
                    timestamp DATETIME DEFAULT GETDATE()
                )
            """)
            cursor.execute(
                "CREATE INDEX idx_session_id ON chat_history(session_id)"
            )
            conn.commit()
            print("       Table chat_history created with index.")
        else:
            print("       Table chat_history already exists. Skipping.")

        # Add new columns if they don't exist (for existing tables)
        for col_name, col_def in [
            ("status", "VARCHAR(50) DEFAULT 'pending'"),
            ("user_name", "NVARCHAR(255) DEFAULT 'Anonymous'"),
        ]:
            cursor.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = 'chat_history' AND COLUMN_NAME = ?",
                (col_name,),
            )
            if cursor.fetchone() is None:
                cursor.execute(f"ALTER TABLE chat_history ADD {col_name} {col_def}")
                conn.commit()
                print(f"       Added column '{col_name}' to chat_history.")
            else:
                print(f"       Column '{col_name}' already exists. Skipping.")

        conn.close()
    except Exception as e:
        print(f"ERROR creating table: {e}")
        return

    print("\nMigration complete! You can now run the API.")


if __name__ == "__main__":
    run_migration()
