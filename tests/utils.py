# utils.py
import os
import sqlite3
from sqlalchemy import create_engine, text

BIKES_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "bikes.db")
)


def create_bike_db():
    os.makedirs(os.path.dirname(BIKES_DB_PATH), exist_ok=True)

    if os.path.exists(BIKES_DB_PATH):
        os.remove(BIKES_DB_PATH)

    conn = sqlite3.connect(BIKES_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE bikes (
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        price INTEGER NOT NULL
    );
    """
    )
    conn.commit()
    conn.close()


def setup_mysql_db():
    engine = create_engine(
        "mysql+pymysql://user:userpassword@localhost:3306/foundation"
    )
    with engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS bikes;"))
        connection.execute(
            text(
                """
            CREATE TABLE bikes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                make VARCHAR(255) NOT NULL,
                model VARCHAR(255) NOT NULL,
                price INT NOT NULL
            );
        """
            )
        )
        connection.commit()


def setup_postgres_db():
    engine = create_engine(
        "postgresql+psycopg2://user:userpassword@localhost:5432/foundation"
    )
    with engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS bikes;"))
        connection.execute(
            text(
                """
            CREATE TABLE bikes (
                id SERIAL PRIMARY KEY,
                make VARCHAR(255) NOT NULL,
                model VARCHAR(255) NOT NULL,
                price INT NOT NULL
            );
        """
            )
        )
        connection.commit()
