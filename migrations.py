import sqlite3
import psycopg2

from database import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS services (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    ticket_number TEXT,
    user_id INTEGER REFERENCES users(id),
    service_id INTEGER REFERENCES services(id),
    scheduled_for TIMESTAMP,
    status TEXT,
    canceled_by TEXT
);
""")

conn.commit()
conn.close()

sqlite_conn = sqlite3.connect("queue.db")
sqlite_cursor = sqlite_conn.cursor()

pg_conn = psycopg2.connect(
    dbname="queue_db",
    user="postgres",
    password="28032006",
    host="localhost",
    port="5432"
)
pg_cursor = pg_conn.cursor()


sqlite_cursor.execute("SELECT username, password, role FROM users")
users = sqlite_cursor.fetchall()

for u in users:
    pg_cursor.execute(
        """
        INSERT INTO users (username, password, role)
        VALUES (%s,%s,%s)
        ON CONFLICT (username) DO NOTHING
        """,
        u
    )


sqlite_cursor.execute("SELECT name, description, is_active FROM services")
services = sqlite_cursor.fetchall()

for s in services:
    name, description, is_active = s

    is_active = bool(is_active)

    pg_cursor.execute(
        """
        INSERT INTO services (name, description, is_active)
        VALUES (%s,%s,%s)
        """,
        (name, description, is_active)
    )


sqlite_cursor.execute(
    """
    SELECT ticket_number, user_id, service_id, scheduled_for, status, canceled_by
    FROM tickets
    """
)

tickets = sqlite_cursor.fetchall()

for t in tickets:
    pg_cursor.execute(
        """
        INSERT INTO tickets
        (ticket_number, user_id, service_id, scheduled_for, status, canceled_by)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        t
    )


pg_conn.commit()

sqlite_conn.close()
pg_conn.close()

print("Migration completed successfully")