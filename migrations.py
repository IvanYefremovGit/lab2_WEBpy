import sqlite3
from pymongo import MongoClient

# 🔌 MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["queue_db"]

# 📌 Явно створюємо колекцію tickets (для звіту)
if "tickets" not in db.list_collection_names():
    db.create_collection("tickets")

if "logs" not in db.list_collection_names():
    db.create_collection("logs")
# 🗑️ Очистимо колекції (щоб не дублювались)
db.users.delete_many({})
db.services.delete_many({})
db.tickets.delete_many({})

# 🔗 SQLite
sqlite_conn = sqlite3.connect("queue.db")
sqlite_cursor = sqlite_conn.cursor()

# =========================
# 📌 USERS
# =========================
sqlite_cursor.execute("SELECT id, username, password, role FROM users")
users = sqlite_cursor.fetchall()

user_map = {}  # старий id -> новий ObjectId

for u in users:
    old_id, username, password, role = u

    result = db.users.insert_one({
        "username": username,
        "password": password,
        "role": role
    })

    user_map[old_id] = str(result.inserted_id)


# =========================
# 📌 SERVICES
# =========================
sqlite_cursor.execute("SELECT id, name, description, is_active FROM services")
services = sqlite_cursor.fetchall()

service_map = {}

for s in services:
    old_id, name, description, is_active = s

    result = db.services.insert_one({
        "name": name,
        "description": description,
        "is_active": bool(is_active)
    })

    service_map[old_id] = str(result.inserted_id)


# =========================
# 📌 TICKETS
# =========================
sqlite_cursor.execute("""
SELECT ticket_number, user_id, service_id, scheduled_for, status, canceled_by
FROM tickets
""")

tickets = sqlite_cursor.fetchall()

for t in tickets:
    ticket_number, user_id, service_id, scheduled_for, status, canceled_by = t

    db.tickets.insert_one({
        "ticket_number": ticket_number,
        "user_id": user_map.get(user_id),
        "service_id": service_map.get(service_id),
        "scheduled_for": scheduled_for,
        "status": status,
        "canceled_by": canceled_by
    })


# 🔚 Закриваємо SQLite
sqlite_conn.close()

print("✅ Migration to MongoDB completed!")