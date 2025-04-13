import unittest
from foundation_sql import db
import dotenv

dotenv.load_dotenv()

class DatabaseTests(unittest.TestCase):
    """Base test class for database-driven tests with common setup and helper methods."""

    db_url = "sqlite:///:memory:"
    schema_sql = None
    schema_path = None

    def setUp(self):
        """Create a fresh database connection for each test."""
        # Reset the global database instance
        db._db_instance = db.Database(self.db_url)

        # Re-initialize the schema for each test to ensure clean state
        if self.schema_sql or self.schema_path:
            db._db_instance.init_schema(schema_sql=self.schema_sql, schema_path=self.schema_path)
        else:
            raise ValueError("At least one of schema_sql or schema_path must be provided")

    def tearDown(self):
        """Close the database connection after each test."""
        db._db_instance.get_engine().dispose()
