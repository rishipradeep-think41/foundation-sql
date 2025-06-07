import unittest
import os
from foundation_sql import db
from foundation_sql.query import SQLQueryDecorator
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

# DB_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

def create_query (schema: Optional[str] = None, db_url : Optional[str] = None):
    final_db_url = (
        db_url or 
        os.environ.get("DATABASE_URL") or 
        "sqlite:///:memory:"
    )
    return SQLQueryDecorator(schema=schema, 
                   db_url=final_db_url, 
                   api_key=os.getenv("OPENAI_API_KEY"),
                   base_url=os.getenv("OPENAI_API_BASE_URL"),
                   model=os.getenv("OPENAI_MODEL"))

class DatabaseTests(unittest.TestCase):
    """Base test class for database-driven tests with common setup and helper methods."""

    db_url = "sqlite:///:memory:"
    schema_sql = None
    schema_path = None

    def setUp(self):
        """Create a fresh database connection for each test."""
        #Re-initialize the schema for each test to ensure clean state
        if (self.schema_sql or self.schema_path) and self.db_url:
            db.get_db(self.db_url).init_schema(schema_sql=self.schema_sql, schema_path=self.schema_path)
        else:
            pass
        

    def tearDown(self):
        """Close the database connection after each test."""
        for _, connection in db.DATABASES.items():
            connection.get_engine().dispose()
        
        db.DATABASES.clear()


