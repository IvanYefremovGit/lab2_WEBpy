import psycopg

def get_connection():
    conn = psycopg.connect(
        host="localhost",
        dbname="queue_db",
        user="postgres",
        password="",
        port=5432
    )
    return conn
