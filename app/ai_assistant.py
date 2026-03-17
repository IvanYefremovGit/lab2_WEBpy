import ollama
from database import get_connection
from datetime import datetime, timedelta


def ask_ai(question: str):

    from .routers.public import build_free_times

    question_lower = question.lower()

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()


    if "послуг" in question_lower or "services" in question_lower:

        cursor.execute("SELECT name FROM services WHERE is_active = TRUE")
        services = cursor.fetchall()

        conn.close()

        services_list = ", ".join([s[0] for s in services])

        return f"Доступні послуги: {services_list}"



    if "скільки" in question_lower and "черг" in question_lower:

        cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE status IN ('waiting','approved')
        """)

        count = cursor.fetchone()[0]

        conn.close()

        return f"Зараз у черзі {count} записів."



    if "сьогодні" in question_lower:

        cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE DATE(scheduled_for) = CURRENT_DATE
        """)

        count = cursor.fetchone()[0]

        conn.close()

        return f"На сьогодні створено {count} записів."



    if "сьогодні" in question_lower and "час" in question_lower:

        today = now.strftime("%Y-%m-%d")

        free_times = build_free_times(conn, today)

        conn.close()

        if not free_times:
            return "На сьогодні вже немає доступних слотів."

        return f"Доступні слоти сьогодні: {', '.join(free_times[:10])}"



    if "завтра" in question_lower and "час" in question_lower:

        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        free_times = build_free_times(conn, tomorrow)

        conn.close()

        if not free_times:
            return "На завтра немає доступних слотів."

        return f"Доступні слоти на завтра: {', '.join(free_times[:10])}"


    if "найближч" in question_lower or "коли можна" in question_lower:

        for i in range(3):  # сьогодні + 2 дні вперед
            date = (now + timedelta(days=i)).strftime("%Y-%m-%d")

            free_times = build_free_times(conn, date)

            if free_times:
                conn.close()
                return f"Найближчий доступний час: {date} {free_times[0]}"

        conn.close()
        return "Немає доступних слотів у найближчі дні."


    if "зайнят" in question_lower or "заброньован" in question_lower:

        today = now.strftime("%Y-%m-%d")

        cursor.execute("""
        SELECT TO_CHAR(scheduled_for, 'HH24:MI')
        FROM tickets
        WHERE DATE(scheduled_for) = CURRENT_DATE
        AND status IN ('waiting','approved')
        """)

        times = cursor.fetchall()

        conn.close()

        if not times:
            return "Наразі немає зайнятих слотів."

        booked = ", ".join([t[0] for t in times])

        return f"Зайняті слоти сьогодні: {booked}"


    cursor.execute("SELECT name FROM services WHERE is_active = TRUE")
    services = cursor.fetchall()

    conn.close()

    services_list = ", ".join([s[0] for s in services])

    system_prompt = f"""
You are an AI assistant for an electronic queue system.

Current time: {now.strftime("%Y-%m-%d %H:%M")}

Available services:
{services_list}

Working hours: 08:00 - 17:00
Time step: 10 minutes

You can answer about:
- queue
- services
- booking time

If you don't know the answer, say you don't know.
"""

    response = ollama.chat(
        model="mistral",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ]
    )

    return response["message"]["content"]