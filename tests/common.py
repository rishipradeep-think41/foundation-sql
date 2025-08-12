import unittest
import os
from foundation_sql import db
from foundation_sql.query import SQLQueryDecorator
import re

from dotenv import load_dotenv
load_dotenv()

# Force SQLite in-memory for all tests that use this common module.
# Async/Postgres-specific tests manage their own DATABASE_URL and are skipped if absent.
DB_URL = "sqlite:///:memory:"

def create_query(schema):
    return SQLQueryDecorator(
        schema=schema,
        db_url=DB_URL,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE_URL"),
        model=os.getenv("OPENAI_MODEL"),
        repair=2,
    )

class DatabaseTests(unittest.TestCase):
    """Base test class for database-driven tests with common setup and helper methods."""

    db_url = DB_URL
    schema_sql = None
    schema_path = None

    def setUp(self):
        """Create a fresh database connection for each test."""
        # Re-initialize the schema for each test to ensure clean state
        if (self.schema_sql or self.schema_path) and self.db_url:
            db.get_db(self.db_url).init_schema(schema_sql=self.schema_sql, schema_path=self.schema_path)
            # Capture table names from schema_sql for teardown cleanup
            self._tables_to_drop = []
            if self.schema_sql:
                for raw in self.schema_sql.split(';'):
                    stmt = raw.strip()
                    if not stmt:
                        continue
                    m = re.search(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", stmt, re.IGNORECASE)
                    if m:
                        self._tables_to_drop.append(m.group(1))
        else:
            raise ValueError("At least one of schema_sql, schema_path must be provided along with db_url")
        

    def tearDown(self):
        """Close the database connection after each test."""
        # Best-effort cleanup of tables created by this test to avoid cross-test interference
        try:
            if getattr(self, "_tables_to_drop", None):
                database = db.get_db(self.db_url)
                # Drop in reverse order to reduce FK issues
                for t in reversed(self._tables_to_drop):
                    try:
                        database.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
                    except Exception:
                        pass
        finally:
            for _, connection in db.DATABASES.items():
                connection.get_engine().dispose()
            db.DATABASES.clear()
        db.DATABASES.clear()
