from typing import List
from pydantic import BaseModel
from tests import common
from tests.utils import setup_postgres_db


# Define a Bike model
class Bike(BaseModel):
    id: int
    make: str
    model: str
    price: int


setup_postgres_db()


query = common.create_query(
    db_url="postgresql+psycopg2://user:userpassword@localhost:5432/foundation"
)


# Query to insert a bike
@query
def create_bike(bike: Bike) -> Bike:
    """
    Inserts a bike and returns the created bike.
    """
    pass


# Query to fetch all bikes
@query
def get_bikes() -> List[Bike]:
    """
    Gets all bikes.
    """
    pass


# Query to get total price of all bikes
@query
def get_total_price() -> int:
    """
    Returns total price of all bikes.
    """
    pass


# Query that should naturally generate a PostgreSQL-only operator
@query
def search_bikes_case_insensitive(make_query: str) -> List[Bike]:
    """
    Returns bikes that match the given make (case-insensitive).
    """
    pass


class TestPostgresSchema(common.DatabaseTests):
    db_url = "postgresql+psycopg2://user:userpassword@localhost:5432/foundation"
    schema_sql = None

    re_bike = Bike(id=1, make="RE", model="Classic", price=600)
    harley = Bike(id=2, make="Harley", model="Sportster", price=500)
    create_bike(bike=re_bike)
    create_bike(bike=harley)

    def test_get_bikes(self):
        bikes = get_bikes()
        self.assertEqual(len(bikes), 2)

    def test_total_price(self):
        total = get_total_price()
        self.assertEqual(total, 1100)

    def test_case_insensitive_search(self):
        bikes = search_bikes_case_insensitive(make_query="re")
        self.assertEqual(len(bikes), 1)
        self.assertEqual(bikes[0].make.lower(), "re")
