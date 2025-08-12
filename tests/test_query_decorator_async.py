import os
import shutil
import unittest
import inspect
from typing import List

from pydantic import BaseModel

from foundation_sql.query import SQLQueryDecorator
from foundation_sql.db_drivers import AsyncpgAdapter
from foundation_sql import db


ASYNC_DB_URL = os.environ.get("DATABASE_URL")  # e.g., postgresql://user:pass@localhost:5432/dbname
CACHE_DIR = "__sql__"


@unittest.skipUnless(ASYNC_DB_URL, "Async tests require DATABASE_URL Postgres DSN")
class TestSQLQueryDecoratorAsync(unittest.IsolatedAsyncioTestCase):
    class User(BaseModel):
        id: int
        name: str

    TABLES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """

    @classmethod
    def setUpClass(cls) -> None:
        # Ensure clean cache dir and seed templates
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, "get_users.sql"), "w") as f:
            f.write("SELECT id, name FROM users ORDER BY id;")
        with open(os.path.join(CACHE_DIR, "create_user.sql"), "w") as f:
            f.write("INSERT INTO users (id, name) VALUES ({{ user.id }}, {{ user.name | tojson }});")

    async def asyncSetUp(self):
        # Initialize schema on Postgres using async adapter each test for isolation
        self.database = db.Database(ASYNC_DB_URL, adapter=AsyncpgAdapter(ASYNC_DB_URL))
        await self.database.init_schema_async(schema_sql=self.TABLES_SCHEMA)
        # Clean table
        await self.database.run_sql_async("DELETE FROM users;")

    async def asyncTearDown(self):
        await self.database.close_async()
        db.DATABASES.clear()

    async def test_async_wrapper_and_execution(self):
        query = SQLQueryDecorator(schema=self.TABLES_SCHEMA, db_url=ASYNC_DB_URL, cache_dir=CACHE_DIR, adapter_mode="async")

        @query
        def get_users() -> List["TestSQLQueryDecoratorAsync.User"]:
            pass

        @query
        def create_user(user: "TestSQLQueryDecoratorAsync.User") -> int:
            pass

        # wrappers should be async
        self.assertTrue(inspect.iscoroutinefunction(get_users))
        self.assertTrue(inspect.iscoroutinefunction(create_user))

        users = await get_users()
        self.assertEqual(len(users), 0)
        rc = await create_user(user=self.User(id=1, name="Alice"))
        self.assertEqual(rc, 1)
        users = await get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].id, 1)
        self.assertEqual(users[0].name, "Alice")

    async def test_async_adapter_direct_use(self):
        adapter = AsyncpgAdapter(ASYNC_DB_URL)
        await adapter.init_pool_async()
        await adapter.init_schema_async(self.TABLES_SCHEMA)
        rc = await adapter.run_sql_async("INSERT INTO users (id, name) VALUES ({{ id }}, {{ name | tojson }});", {"id": 2, "name": "Bob"})
        self.assertEqual(rc, 1)
        rows = await adapter.run_sql_async("SELECT id, name FROM users ORDER BY id;", {})
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        await adapter.close_async()


if __name__ == "__main__":
    unittest.main(verbosity=2)
