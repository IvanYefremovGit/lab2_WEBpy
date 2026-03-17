from database import get_connection


def seed_data():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO users (username, password, role)
            VALUES (%s,%s,%s)
            """,
            ("admin", "admin", "admin"),
        )

    cursor.execute("SELECT id FROM users WHERE username='user'")
    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO users (username, password, role)
            VALUES (%s,%s,%s)
            """,
            ("user", "user", "user"),
        )

    cursor.execute("SELECT COUNT(*) FROM services")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.execute(
            """
            INSERT INTO services (name, description, is_active)
            VALUES (%s,%s,%s)
            """,
            ("Отримання довідки", "Видача довідок", True),
        )

        cursor.execute(
            """
            INSERT INTO services (name, description, is_active)
            VALUES (%s,%s,%s)
            """,
            ("Реєстрація документів", "Прийом та реєстрація", True),
        )

        cursor.execute(
            """
            INSERT INTO services (name, description, is_active)
            VALUES (%s,%s,%s)
            """,
            ("Консультація", "Консультаційні послуги", True),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed_data()
    print("Seed data added successfully")