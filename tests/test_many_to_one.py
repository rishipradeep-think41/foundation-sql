import os
import shutil
from typing import List, Optional

from pydantic import BaseModel

from tests import common


class Workspace(BaseModel):
    id: int
    name: str


class Task(BaseModel):
    id: int
    workspace: Workspace
    title: str
    description: Optional[str] = None


TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
"""

query = common.create_query(schema=TABLES_SCHEMA)

CACHE_DIR = "__sql__"


class TestWorkspaceTasks(common.DatabaseTests):
    schema_sql = TABLES_SCHEMA

    @classmethod
    def setUpClass(cls) -> None:
        # Ensure clean cache dir and seed SQLite-friendly templates
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Create workspace: insert then fetch by last_insert_rowid()
        with open(os.path.join(CACHE_DIR, "create_workspace.sql"), "w") as f:
            f.write(
                """
                INSERT INTO workspaces (name) VALUES ({{ name | tojson }});
                SELECT id, name FROM workspaces WHERE id = last_insert_rowid();
                """.strip()
            )

        # Add task to workspace: insert then fetch row
        with open(os.path.join(CACHE_DIR, "add_task_to_workspace.sql"), "w") as f:
            f.write(
                """
                INSERT INTO tasks (workspace_id, title, description)
                VALUES (
                    {{ workspace.id }},
                    {{ title | tojson }},
                    {{ description | default(None) | tojson }}
                );
                SELECT 
                    id as "id",
                    workspace_id as "workspace.id",
                    title as "title",
                    description as "description"
                FROM tasks 
                WHERE id = last_insert_rowid();
                """.strip()
            )

        # Get tasks for workspace: join with dotted aliases for nesting
        with open(os.path.join(CACHE_DIR, "get_tasks_for_workspace.sql"), "w") as f:
            f.write(
                """
                SELECT 
                    t.id as "id",
                    t.workspace_id as "workspace.id",
                    w.name as "workspace.name",
                    t.title as "title",
                    t.description as "description"
                FROM tasks t
                JOIN workspaces w ON w.id = t.workspace_id
                WHERE w.id = {{ workspace.id }}
                ORDER BY t.id;
                """.strip()
            )


@query
def create_workspace(name: str) -> Workspace:
    """
    Inserts a new workspace and returns the Workspace object.
    """
    pass


@query
def add_task_to_workspace(
    workspace: Workspace, title: str, description: Optional[str] = None
) -> Task:
    """
    Inserts a new task into the workspace and returns the Task object.
    """
    pass


@query
def get_tasks_for_workspace(workspace: Workspace) -> List[Task]:
    """
    Returns all tasks for a workspace as Task objects with nested workspace.
    """
    pass

    def test_workspace_tasks(self):
        # Add a workspace
        ws = create_workspace(name="Project Alpha")
        self.assertIsInstance(ws, Workspace)

        # Add tasks
        task1 = add_task_to_workspace(
            workspace=ws, title="Setup repo", description="Initialize git repository"
        )
        task2 = add_task_to_workspace(
            workspace=ws, title="Write docs", description="Document the setup process"
        )
        self.assertIsInstance(task1, Task)
        self.assertIsInstance(task2, Task)

        # Fetch tasks
        tasks = get_tasks_for_workspace(workspace=ws)
        self.assertEqual(len(tasks), 2)
        titles = {t.title for t in tasks}
        self.assertSetEqual(titles, {"Setup repo", "Write docs"})
        for t in tasks:
            self.assertEqual(t.workspace.id, ws.id)
            self.assertEqual(t.workspace.name, ws.name)
