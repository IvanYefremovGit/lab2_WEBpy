import sqlite3

conn = sqlite3.connect("queue.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    is_active BOOLEAN
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT,
    user_id INTEGER,
    service_id INTEGER,
    scheduled_for TEXT,
    status TEXT,
    canceled_by TEXT
)
""")

cursor.execute("""
INSERT INTO users (username, password, role)
VALUES
('admin','admin','admin'),
('user','user','user')
""")

cursor.execute("""
INSERT INTO services (name, description, is_active)
VALUES
('Отримання довідки','Видача довідок',1),
('Реєстрація документів','Прийом документів',1),
('Консультація','Консультаційні послуги',1)
""")

conn.commit()
conn.close()

print("SQLite database created successfully")