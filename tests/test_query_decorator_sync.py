import os
import shutil
import unittest
import inspect
from typing import List

from pydantic import BaseModel
from tests import common
from foundation_sql.query import SQLQueryDecorator
from foundation_sql import db

DB_URL = os.environ.get("DATABASE_URL")
CACHE_DIR = "__sql__"


class User(BaseModel):
    id: int
    name: str


TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
"""


class TestSQLQueryDecoratorSync(common.DatabaseTests):
    schema_sql = TABLES_SCHEMA

    @classmethod
    def setUpClass(cls) -> None:
        # Ensure clean cache dir
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)
        # Seed SQL templates so no LLM calls are needed
        with open(os.path.join(CACHE_DIR, "get_users.sql"), "w") as f:
            f.write("SELECT id, name FROM users ORDER BY id;")
        with open(os.path.join(CACHE_DIR, "create_user.sql"), "w") as f:
            f.write("INSERT INTO users (id, name) VALUES ({{ user.id }}, {{ user.name | tojson }});")

    def setUp(self):
        super().setUp()
        # Ensure clean table state for each test
        database = db.get_db(self.db_url)
        database.run_sql("DELETE FROM users;")

    def test_sync_wrapper_and_execution(self):
        query = SQLQueryDecorator(schema=TABLES_SCHEMA, db_url=self.db_url, cache_dir=CACHE_DIR, adapter_mode="sync")

        @query
        def get_users() -> List[User]:
            """Get all users"""
            pass

        @query
        def create_user(user: User) -> int:
            """Create user"""
            pass

        # wrapper should be sync
        self.assertFalse(inspect.iscoroutinefunction(get_users))
        self.assertFalse(inspect.iscoroutinefunction(create_user))

        # execute
        users = get_users()
        self.assertEqual(len(users), 0)
        rc = create_user(user=User(id=1, name="Alice"))
        self.assertEqual(rc, 1)
        users = get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].id, 1)
        self.assertEqual(users[0].name, "Alice")

    def test_template_caching(self):
        # Pre-seeded template exists; decorator should reuse without regeneration
        query = SQLQueryDecorator(schema=TABLES_SCHEMA, db_url=self.db_url, cache_dir=CACHE_DIR, adapter_mode="sync")

        @query
        def get_users() -> List[User]:
            pass

        # Change cached SQL to return in reverse order to observe effect
        with open(os.path.join(CACHE_DIR, "get_users.sql"), "w") as f:
            f.write("SELECT id, name FROM users ORDER BY id DESC;")

        # Insert two rows and ensure order follows cached SQL
        database = db.get_db(self.db_url)
        database.run_sql("INSERT INTO users (id, name) VALUES (1, 'A');")
        database.run_sql("INSERT INTO users (id, name) VALUES (2, 'B');")

        users = get_users()
        self.assertEqual([u.id for u in users], [2, 1])

    def test_adapter_selection_flag_async_wrapper_for_sync_func(self):
        # When adapter_mode="async", even a sync function should return async wrapper
        query = SQLQueryDecorator(schema=TABLES_SCHEMA, db_url=self.db_url, cache_dir=CACHE_DIR, adapter_mode="async")

        @query
        def get_users_async() -> List[User]:
            pass

        self.assertTrue(inspect.iscoroutinefunction(get_users_async))


if __name__ == "__main__":
    unittest.main(verbosity=2)
