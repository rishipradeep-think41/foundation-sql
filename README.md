# SQL Query Generator (Experimental)

A Python-based SQL query generator that helps in generating and managing SQL queries.

## Installation

You can install the package directly from Github. We will publish it to PyPi once we move it to beta.

```bash
pip install git+ssh://git@github.com/think41/foundation-sql.git#egg=foundation_sql
```

## Usage

```python
from foundation_sql.query import SQLQueryDecorator

query = SQLQueryDecorator(
    # Required Parameters
    schema=<schema_definition>, # Schema definition DDL as script
    db_url=<database_url>, # Database connection URL
    base_url=<base_url>, # Open AI Compatible base URL
    api_key=<model_api_key>, # API Key
    model=<llm_model_name> # Model to use for generation

    # Optional Parameters
    system_prompt=<prompt>, # Override the default system prompt
    cache_dir=<relative_path>, # where to store the sql file - defaults to __sql__
    name=<name> # name of the sql file - defaults to method name
)
```

Once defined, it can be used as a decorator e.g.

```
@query
def get_users_with_profile() -> List[UserWithProfile]:
    """
    Gets all users with their profiles.
    """
    pass

@query
def create_user_with_profile(user: UserWithProfile) -> int:
    """
    Creates a new user with a profile.
    """
    pass
```

The parameter types are assumed to be pydantic objects. The method docstring is used in the prompt to explain the functionality. When run the first time, it would generate a sql file in cache_dir folder. Next runs would automatically use it. Here is a sample test that demonstrates usage

```python
import os
from typing import List
import unittest
from foundation_sql import db, query
from pydantic import BaseModel


DB_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

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

query = query.SQLQueryDecorator(schema=TABLES_SCHEMA,
            db_url=DB_URL,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE_URL"),
            model=os.getenv("OPENAI_MODEL"))

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

class TestQuery(unittest.TestCase):

    db_url = DB_URL
    schema_sql = TABLES_SCHEMA
    schema_path = None

    def setUp(self):
        """Create a fresh database connection for each test."""
        # Re-initialize the schema for each test to ensure clean state
        if (self.schema_sql or self.schema_path) and self.db_url:
            db.get_db(self.db_url).init_schema(schema_sql=self.schema_sql, schema_path=self.schema_path)
        else:
            raise ValueError("At least one of schema_sql, schema_path must be provided along with db_url")

    def test_users(self):
        users = get_users()
        self.assertEqual(len(users), 0)

        user = User(id="xxx", name="John Doe", email="john@example.com", role="user")
        create_user(user=user)

        users = get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0], user)

    def tearDown(self):
        """Close the database connection after each test."""
        for _, connection in db.DATABASES.items():
            connection.get_engine().dispose()

        db.DATABASES.clear()
```

Running these tests would generate the following SQL files

```sql
#__sql__/create_user.sql
-- def create_user(user: tests.test_simple_query.User) -> int
-- Creates a new user.
-- Expects user.name, user.email and user.role to be defined
INSERT INTO `users` (
    `id`,
    `name`,
    `email`,
    `role`
)
VALUES (
    {{user.id|default(None)}},
    {{user.name}},
    {{user.email}},
    {{user.role}}
);
```

```sql
#__sql__/get_users.sql

-- def get_users() -> List[tests.test_simple_query.User]
-- Gets all users.
SELECT
    `id` as `id`,
    `name` as `name`,
    `email` as `email`,
    `role` as `role`
FROM
    `users`
```

## Development Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env_template` to `.env` and configure your environment variables:
   ```bash
   cp .env_template .env
   ```

## Run tests

```bash
docker compose up --build
python -m unittest discover tests
```

Run a particular test file

```bash
python -m unittest -v tests/{test_file.py}
```

## Project Structure

- `query.py`: Main query generation logic
- `db.py`: Database connection and management
- `cache.py`: Caching functionality
- `tests/`: Test suite
- `__sql__/`: Generated SQL queries
- `.env`: Environment variables
- `.env_template`: Template for environment variables
- `requirements.txt`: Project dependencies
- `README.md`: Project documentation
