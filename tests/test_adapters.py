import os
import unittest
from typing import Any, Dict, List

from foundation_sql.db_drivers import SQLAlchemyAdapter
from foundation_sql import db


SYNC_DB_URL = os.environ.get("DATABASE_URL")


TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
"""

INSERT_TEMPLATE = """
INSERT INTO items (id, name) VALUES ({{ id }}, {{ name | tojson }});
"""

SELECT_TEMPLATE = """
SELECT id, name FROM items ORDER BY id;
"""


class TestSQLAlchemyAdapter(unittest.TestCase):
    def setUp(self) -> None:
        if not SYNC_DB_URL:
            raise unittest.SkipTest("DATABASE_URL not set; skipping Postgres-only tests")
        self.adapter = SQLAlchemyAdapter(SYNC_DB_URL)
        # init schema
        self.adapter.init_schema(TEST_SCHEMA)
        # ensure clean state for each test run
        try:
            self.adapter.run_sql("DELETE FROM items;", {})
        except Exception:
            pass

    def tearDown(self) -> None:
        try:
            self.adapter.close()
        finally:
            # Clear Database singletons that might have been created
            db.DATABASES.clear()

    def test_insert_and_select(self):
        # insert 2 rows
        rc1 = self.adapter.run_sql(INSERT_TEMPLATE, {"id": 1, "name": "alpha"})
        rc2 = self.adapter.run_sql(INSERT_TEMPLATE, {"id": 2, "name": "beta"})
        self.assertIsInstance(rc1, int)
        self.assertIsInstance(rc2, int)
        self.assertEqual(rc1 + rc2, 2)

        rows = self.adapter.run_sql(SELECT_TEMPLATE, {})
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["name"], "alpha")

    def test_database_facade_run_sql_parity(self):
        # Ensure Database facade wraps adapter correctly
        database = db.Database(SYNC_DB_URL, adapter=self.adapter)
        # seed two rows using adapter path
        _ = self.adapter.run_sql(INSERT_TEMPLATE, {"id": 1, "name": "alpha"})
        _ = self.adapter.run_sql(INSERT_TEMPLATE, {"id": 2, "name": "beta"})
        # Insert
        affected = database.run_sql(INSERT_TEMPLATE, id=3, name="gamma")
        self.assertEqual(affected, 1)
        # Select should return QueryResult wrapper
        result = database.run_sql(SELECT_TEMPLATE)
        self.assertTrue(hasattr(result, "first"))
        self.assertEqual(result.count(), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
