import os
import sqlite3
from typing import List

from pydantic import BaseModel

from tests import common

# --- Start of moved code from tests/utils.py ---

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


# --- End of moved code ---


class Bike(BaseModel):
    make: str
    model: str
    price: int


create_bike_db()

query = common.create_query(db_url=f"sqlite:///{BIKES_DB_PATH}", schema_inspect=True)


@query
def get_bikes() -> List[Bike]:
    """
    Gets all bikes.
    """
    pass


@query
def create_bike(bike: Bike) -> Bike:
    """
    Creates a new bike.
    """
    pass


@query
def get_total_price() -> int:
    """
    Calculates the total price of all the bikes.
    """
    pass


class TestSchemaDiscovery(common.DatabaseTests):
    db_url = f"sqlite:///{BIKES_DB_PATH}"
    schema_sql = None

    def test_schema_discovery(self):

        re_bike = Bike(make="RE", model="Classic", price=600)
        create_bike(bike=re_bike)

        harley_bike = Bike(make="Harley", model="A very good one", price=500)
        create_bike(bike=harley_bike)

        bikes = get_bikes()
        self.assertEqual(len(bikes), 2)

        price = get_total_price()
        self.assertEqual(price, 1100)
