from typing import List
from tests import common
from pydantic import BaseModel
from tests.utils import setup_mysql_db


class Bike(BaseModel):
    id: int = None  # Optional for inserts
    make: str
    model: str
    price: int


setup_mysql_db()

query = common.create_query(
    db_url=f"mysql+pymysql://user:userpassword@localhost:3306/foundation"
)


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
    Get the total price of all the bikes
    """
    pass


@query
def get_last_inserted_id() -> int:
    """
    Returns the last auto-incremented ID inserted into the session
    """
    pass


class TestSchemaDiscovery(common.DatabaseTests):
    db_url = f"mysql+pymysql://user:userpassword@localhost:3306/foundation"
    schema_sql = None

    re_bike = Bike(make="RE", model="Classic", price=600)
    create_bike(bike=re_bike)

    harley_bike = Bike(make="Harley", model="A very good one", price=500)
    create_bike(bike=harley_bike)

    def test_get_bikes(self):
        bikes = get_bikes()
        self.assertEqual(len(bikes), 2)

    def test_last_insert_id(self):
        new_bike = Bike(make="Yamaha", model="FZ", price=800)
        create_bike(bike=new_bike)

        last_id = get_last_inserted_id()
        self.assertTrue(isinstance(last_id, int) and last_id > 0)

    def test_total_price(self):
        price = get_total_price()
        self.assertEqual(price, 1900)
