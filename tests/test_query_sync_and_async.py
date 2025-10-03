import inspect
import os
import shutil
import unittest
from typing import List

from pydantic import BaseModel

from foundation_sql import db
from foundation_sql.db_drivers import AsyncpgAdapter
from foundation_sql.query import SQLQueryDecorator

SQLITE_DB_URL = "sqlite:///__test_sync.sqlite3"

# Attempt to ensure DATABASE_URL is available by reading .env if needed
if not os.environ.get("DATABASE_URL") and os.path.exists(
    os.path.join(os.path.dirname(__file__), "..", ".env")
):
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    os.environ.setdefault(key, val)
    except Exception:
        pass

ASYNC_DB_URL = os.environ.get(
    "DATABASE_URL"
)  # e.g., postgresql://user:pass@localhost:5432/dbname
CACHE_DIR_SYNC = "__sql__/__sql_sync__"
CACHE_DIR_ASYNC = "__sql__/__sql_async__"


class TestSQLQueryDecoratorSync(unittest.TestCase):
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
        # Ensure clean cache dir and seed templates for sync
        if os.path.exists(CACHE_DIR_SYNC):
            shutil.rmtree(CACHE_DIR_SYNC)
        os.makedirs(CACHE_DIR_SYNC, exist_ok=True)
        with open(os.path.join(CACHE_DIR_SYNC, "get_users.sql"), "w") as f:
            f.write("SELECT id, name FROM users ORDER BY id;")
        with open(os.path.join(CACHE_DIR_SYNC, "create_user.sql"), "w") as f:
            f.write(
                "INSERT INTO users (id, name) VALUES ({{ user.id }}, {{ user.name | tojson }});"
            )

        # Prepare SQLite DB file cleanly
        if os.path.exists("__test_sync.sqlite3"):
            os.remove("__test_sync.sqlite3")

    def setUp(self) -> None:
        # Initialize schema on SQLite using sync adapter
        self.database = db.Database(SQLITE_DB_URL)
        self.database.init_schema(schema_sql=self.TABLES_SCHEMA)
        # Clean table
        self.database.run_sql("DELETE FROM users;")

    def tearDown(self) -> None:
        # Close SQLAlchemy engine
        try:
            self.database.adapter.close()
        except Exception:
            pass
        db.DATABASES.clear()

    def test_sync_wrappers_and_execution(self):
        query = SQLQueryDecorator(
            schema=self.TABLES_SCHEMA, db_url=SQLITE_DB_URL, cache_dir=CACHE_DIR_SYNC
        )

        @query
        def get_users() -> List["TestSQLQueryDecoratorSync.User"]:
            pass

        @query
        def create_user(user: "TestSQLQueryDecoratorSync.User") -> int:
            pass

        # wrappers should be sync
        self.assertFalse(inspect.iscoroutinefunction(get_users))
        self.assertFalse(inspect.iscoroutinefunction(create_user))

        users = get_users()
        self.assertEqual(len(users), 0)
        rc = create_user(user=self.User(id=1, name="Alice"))
        self.assertEqual(rc, 1)
        users = get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].id, 1)
        self.assertEqual(users[0].name, "Alice")


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
        # Ensure clean cache dir and seed templates for async
        if os.path.exists(CACHE_DIR_ASYNC):
            shutil.rmtree(CACHE_DIR_ASYNC)
        os.makedirs(CACHE_DIR_ASYNC, exist_ok=True)
        with open(os.path.join(CACHE_DIR_ASYNC, "get_users.sql"), "w") as f:
            f.write("SELECT id, name FROM users ORDER BY id;")
        with open(os.path.join(CACHE_DIR_ASYNC, "create_user.sql"), "w") as f:
            f.write(
                "INSERT INTO users (id, name) VALUES ({{ user.id }}, {{ user.name | tojson }});"
            )

    async def asyncSetUp(self):
        # Initialize schema on Postgres using async adapter each test for isolation
        self.database = db.Database(ASYNC_DB_URL, adapter=AsyncpgAdapter(ASYNC_DB_URL))
        await self.database.init_schema_async(schema_sql=self.TABLES_SCHEMA)
        # Clean table
        await self.database.run_sql_async("DELETE FROM users;")

    async def asyncTearDown(self):
        await self.database.close_async()
        db.DATABASES.clear()

    async def test_async_wrappers_and_execution(self):
        query = SQLQueryDecorator(
            schema=self.TABLES_SCHEMA, db_url=ASYNC_DB_URL, cache_dir=CACHE_DIR_ASYNC
        )

        @query
        async def get_users() -> List["TestSQLQueryDecoratorAsync.User"]:
            pass

        @query
        async def create_user(user: "TestSQLQueryDecoratorAsync.User") -> int:
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
