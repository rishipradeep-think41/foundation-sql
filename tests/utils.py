# utils.py
import os
import sqlite3

BIKES_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "bikes.db")
)

def create_bike_db():
    os.makedirs(os.path.dirname(BIKES_DB_PATH), exist_ok=True) 


    if os.path.exists(BIKES_DB_PATH):
        os.remove(BIKES_DB_PATH)

    conn = sqlite3.connect(BIKES_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE bikes (
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        price INTEGER NOT NULL
    );
    """)
    conn.commit()
    conn.close()
