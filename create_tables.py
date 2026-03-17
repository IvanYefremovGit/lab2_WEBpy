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