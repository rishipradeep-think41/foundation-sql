from typing import List
from tests import common
from pydantic import BaseModel
import os
import shutil


class User(BaseModel):
    id: str
    name: str
    email: str
    role: str

TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'user', 'guest')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
)
"""

query = common.create_query(schema=TABLES_SCHEMA)

@query
def get_users() -> List[User]:
    """
    Gets all users.
    """
    pass

@query
def create_user(user: User) -> int:
    """
    Creates a new user.
    """
    pass

class TestQuery(common.DatabaseTests):

    schema_sql = TABLES_SCHEMA
    CACHE_DIR = "__sql__"

    @classmethod
    def setUpClass(cls) -> None:
        # Ensure clean cache dir and seed SQLite-friendly templates for this test
        if os.path.exists(cls.CACHE_DIR):
            shutil.rmtree(cls.CACHE_DIR)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)

        # Deterministic SELECT mapping to Pydantic model fields
        with open(os.path.join(cls.CACHE_DIR, "get_users.sql"), "w") as f:
            f.write(
                (
                    """
                    SELECT 
                        id as "id",
                        name as "name",
                        email as "email",
                        role as "role"
                    FROM users
                    ORDER BY id;
                    """
                ).strip()
            )

        # Deterministic INSERT using provided user fields (string id in this schema)
        with open(os.path.join(cls.CACHE_DIR, "create_user.sql"), "w") as f:
            f.write(
                (
                    """
                    INSERT INTO users (id, name, email, role)
                    VALUES (
                        {{ user.id }},
                        {{ user.name | tojson }},
                        {{ user.email | tojson }},
                        {{ user.role | tojson }}
                    );
                    """
                ).strip()
            )
        
    def test_users(self):
        users = get_users()
        self.assertEqual(len(users), 0)
        
        user = User(id="xxx", name="John Doe", email="john@example.com", role="user")
        create_user(user=user)
        
        users = get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0], user)
