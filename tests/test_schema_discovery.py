from typing import List
from tests import common
from pydantic import BaseModel
from tests.utils import BIKES_DB_PATH, create_bike_db

class Bike(BaseModel):
    make: str
    model: str
    price: int


create_bike_db()

query = common.create_query(db_url=f"sqlite:///{BIKES_DB_PATH}")

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


class TestSchemaDiscovery(common.DatabaseTests):
    db_url = f"sqlite:///{BIKES_DB_PATH}"
    schema_sql = None

    def test_schema_discovery(self):

        re_bike = Bike(make="RE", model="Classic", price=600)
        create_bike(bike=re_bike)

        harley_bike = Bike(make="Harley", model="A very good one", price=500)
        create_bike(bike = harley_bike)

        bikes = get_bikes()
        self.assertEqual(len(bikes), 2)

        price = get_total_price()
        self.assertEqual(price,1100)