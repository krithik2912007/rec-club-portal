"""
db.py — Raw MySQL connection helper.
Keeps all queries identical to the Flask version.
Django ORM is NOT used — all SQL is raw for 1:1 feature parity.
"""
import os
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta, date

db_config = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "user":     os.environ.get("DB_USER",     "clubuser"),
    "password": os.environ.get("DB_PASSWORD", "kiki"),
    "database": os.environ.get("DB_NAME",     "club_portal_v11"),
    "autocommit": False,
}

connection_pool = pooling.MySQLConnectionPool(
    pool_name="club_portal_pool",
    pool_size=20,
    pool_reset_session=True,
    **db_config
)


def get_connection():
    try:
        conn = connection_pool.get_connection()
        if not conn.is_connected():
            conn.reconnect(attempts=3, delay=2)
        return conn
    except mysql.connector.Error as err:
        print("Database connection error:", err)
        raise


def get_cursor():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    return cursor, conn


def close_connection(cursor, conn):
    try:
        if cursor: cursor.close()
        if conn:   conn.close()
    except Exception:
        pass


def serialize_row(row):
    if row is None:
        return None
    result = {}
    for key, val in row.items():
        if isinstance(val, timedelta):
            total = int(val.total_seconds())
            result[key] = "{:02d}:{:02d}".format(total // 3600, (total % 3600) // 60)
        elif isinstance(val, datetime):
            result[key] = val.strftime("%Y-%m-%d %H:%M")
        elif isinstance(val, date):
            result[key] = val.strftime("%Y-%m-%d")
        else:
            result[key] = val
    return result


def serialize_rows(rows):
    return [serialize_row(r) for r in rows]


def log_activity(cursor, message, actor_id=None, entity_type=None, entity_id=None):
    try:
        cursor.execute(
            "INSERT INTO activity_logs(message, actor_id, entity_type, entity_id) VALUES(%s,%s,%s,%s)",
            (message, actor_id, entity_type, entity_id)
        )
    except Exception:
        try:
            cursor.execute("INSERT INTO activity_logs(message) VALUES(%s)", (message,))
        except Exception as e:
            print(f"[log_activity] Failed: {e}")
