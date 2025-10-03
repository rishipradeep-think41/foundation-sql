"""
Database operations module for Foundation (adapter-based).
"""

import logging
import os
from types import NoneType
from typing import Dict, Any, Optional, Type, Union, List
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import MetaData
from sqlalchemy.schema import CreateTable
from jinja2sql import Jinja2SQL
from datetime import datetime
from foundation_sql.db_drivers import EngineAdapter, SQLAlchemyAdapter
from foundation_sql.db_drivers import AsyncpgAdapter

NESTED_SPLITTER = "."
# Singleton instance
DATABASES = {}

# logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)



class Database:
    """Database operations for Foundation delegated to an EngineAdapter."""
    
    def __init__(self, db_url: Optional[str] = None, adapter: Optional[EngineAdapter] = None) -> None:
        """Initialize the database facade.
        
        Args:
            db_url: Database URL (e.g., postgresql://user:pass@host/db, sqlite:///path/to/db)
                   If not provided, will use DATABASE_URL environment variable
            adapter: Optional explicit adapter. If not provided, a default sync adapter is created.
        """
        self.db_url = db_url or os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError('Database URL must be provided either through constructor or DATABASE_URL environment variable')
        
        # Default to sync SQLAlchemy adapter unless explicitly provided
        self.adapter: EngineAdapter = adapter or SQLAlchemyAdapter(self.db_url)

    def get_engine(self) -> Engine:
        """Get the underlying SQLAlchemy engine if available.

        Returns:
            SQLAlchemy Engine instance
        """
        # Only available for SQLAlchemyAdapter
        if isinstance(self.adapter, SQLAlchemyAdapter):
            return self.adapter.engine
        raise RuntimeError("Engine is not available for this adapter")

    def init_schema(self, schema_sql:Optional[str]=None, schema_path: Optional[str] = None) -> None:
        """Initialize the database schema if it doesn't exist.

        This method runs the schema creation script in an idempotent way.
        All objects are created with IF NOT EXISTS clause, so running this
        multiple times is safe and won't modify existing objects.

        Args:
            schema_path: Path to the schema SQL file.
                        If not provided, will use the default schema at data/tables.sql
        """
        if not schema_sql:
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
        # Delegate to adapter
        self.adapter.init_schema(schema_sql)

    def run_sql(self, sql_template: str, **context) -> Any:
        """Run an SQL template string with jinja2sql for rendering and parameter substitution.
        
        Args:
            sql_template: SQL template string with jinja2sql syntax
            **context: Context variables for template rendering
            
        Returns:
            For SELECT queries: A QueryResult object with methods for data access
            For INSERT/UPDATE/DELETE queries: The number of rows affected
        """
        # Add datetime.now function to context if needed
        if 'now' not in context:
            context['now'] = datetime.now
            
        # Delegate to adapter; it returns either list[dict] rows or int rowcount
        result = self.adapter.run_sql(sql_template, context)
        if isinstance(result, int):
            return result
        # assume list of dicts
        return QueryResult(result)

    # ---------- Async delegates (Phase 2) ----------
    async def init_schema_async(self, schema_sql: Optional[str] = None, schema_path: Optional[str] = None) -> None:
        if not hasattr(self.adapter, 'init_schema_async'):
            raise NotImplementedError("Async schema init not supported by this adapter")
        if not schema_sql:
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
        await self.adapter.init_schema_async(schema_sql)  # type: ignore[attr-defined]

    async def run_sql_async(self, sql_template: str, **context) -> Any:
        if not hasattr(self.adapter, 'run_sql_async'):
            raise NotImplementedError("Async run_sql not supported by this adapter")
        if 'now' not in context:
            context['now'] = datetime.now
        result = await self.adapter.run_sql_async(sql_template, context)  # type: ignore[attr-defined]
        if isinstance(result, int):
            return result
        return QueryResult(result)

    async def close_async(self) -> None:
        if hasattr(self.adapter, 'close_async'):
            await self.adapter.close_async()  # type: ignore[attr-defined]
                    

    def execute(self, sql: str, params: Optional[Union[tuple, dict, List[tuple]]] = None) -> Any:
        """
        Execute a raw SQL statement with optional parameters.
        
        Args:
            sql (str): SQL statement to execute
            params (Optional[Union[tuple, dict, List[tuple]]]): 
                Optional parameters for the SQL statement
                - Single tuple for single parameter set
                - List of tuples for multiple parameter sets (bulk insert)
                - Dictionary for named parameters
    
        Returns:
            Any: Result of the execution
        """
        # Only supported on SQLAlchemy adapter path for now
        if not isinstance(self.adapter, SQLAlchemyAdapter):
            raise NotImplementedError("execute() is only supported for SQLAlchemy adapter")

        with self.adapter.engine.connect() as connection:
            try:
                # Replace '?' placeholders with SQLAlchemy named parameters
                if '?' in sql:
                    # Count the number of placeholders
                    placeholder_count = sql.count('?')
                    
                    # Replace '?' with named parameters
                    named_sql = sql.replace('?', ':{}'.format)
                    
                    # Prepare parameters
                    if params is None:
                        named_params = {}
                    elif isinstance(params, (tuple, list)):
                        # Convert tuple/list to named dictionary
                        named_params = {f'p{i}': val for i, val in enumerate(params)}
                        named_sql = named_sql.format(p=lambda i: f':p{i}')
                    elif isinstance(params, dict):
                        named_params = params
                    else:
                        raise ValueError("Invalid parameter type. Must be tuple, dict, or list of tuples.")
                    
                    # Execute with named parameters
                    result = connection.execute(text(named_sql), named_params)
                else:
                    # If no '?' placeholders, use as-is
                    result = connection.execute(text(sql), params or {})
                
                # If it's a SELECT query, return the rows
                if result.returns_rows:
                    return result.fetchall()
                
                # For INSERT, UPDATE, DELETE, return the number of rows affected
                return result.rowcount
            
            except SQLAlchemyError as e:
                raise RuntimeError(f"Database execution error: {str(e)}") from e


class QueryResult:
    """A clean abstraction over query results that doesn't leak implementation details."""
    
    def __init__(self, rows: List[Dict[str, Any]]):
        """Initialize with a list of row dictionaries.
        
        Args:
            rows: List of dictionaries representing database rows
        """
        self.rows = rows
    
    def first(self) -> Optional[Dict[str, Any]]:
        """Get the first row as a dictionary or None if no rows.
        
        Returns:
            First row as a dictionary or None
        """
        return self.rows[0] if self.rows else None
    
    def all(self) -> List[Dict[str, Any]]:
        """Get all rows as a list of dictionaries.
        
        Returns:
            List of dictionaries representing all rows
        """
        return self.rows

    def count(self) -> int:
        """Get the number of rows.
        
        Returns:
            Number of rows
        """
        return len(self.rows)
    
    def is_empty(self) -> bool:
        """Check if the result contains any rows.
        
        Returns:
            True if no rows, False otherwise
        """
        return len(self.rows) == 0
    

# Function to load the schema from the database
def extract_schema_from_db(db_url: str) -> str:
    """Extract the schema from the database.
    
    Args:
        db_url: Database URL to use
        
    Returns:
        Schema as a string
    """
    engine = create_engine(db_url)
    metadata = MetaData()
    metadata.reflect(bind=engine)

    schema_lines = []
    for table in metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(engine))
        schema_lines.append(ddl + ";")

    return "\n\n".join(schema_lines)


def get_db(db_url: str) -> Database:
    """Get the database instance.
    
    Args:
        db_url: Database URL to use
        
    Returns:
        Database instance
    """
    if db_url not in DATABASES:
        DATABASES[db_url] = Database(db_url)
    
    return DATABASES[db_url]

def get_db_with_adapter(db_url: str, mode: str) -> Database:
    """Internal helper for selecting adapter explicitly.
    mode: "sync" | "async" (async not implemented yet)
    """
    if mode == "sync":
        return Database(db_url, adapter=SQLAlchemyAdapter(db_url))
    if mode == "async":
        return Database(db_url, adapter=AsyncpgAdapter(db_url))
    raise ValueError(f"Unknown adapter mode: {mode}")

def run_sql(db_url: str, sql_template: str, **context) -> Any:
    """Run an SQL template string with jinja2sql for rendering and parameter substitution.
    
    Args:
        sql_template: SQL template string with jinja2sql syntax
        **context: Context variables for template rendering
        
    Returns:
        For SELECT queries: A QueryResult object with methods for data access
        For INSERT/UPDATE/DELETE queries: The number of rows affected
    """
    return get_db(db_url).run_sql(sql_template, **context)


def parse_query_to_pydantic(data: Dict[str, Any], model_class: Type[BaseModel]) -> Optional[BaseModel]:
    """Parse query result data into a Pydantic model, handling nested models.
    
    Args:
        data: Dictionary containing query results with optional nested fields
        model_class: The Pydantic model class to instantiate
        
    Returns:
        Instance of the Pydantic model or None if data is None
    """
    if not data:
        return None    

    unflattened_data = unflatten_dict(data)

    # Check the response type and transform accordingly
    if model_class == int:
        # FIX : STILL ONLY GETS FIRST LINE OF RESPONSE
        return int(next(iter(unflattened_data.values())))
    elif model_class == NoneType:
        return None
    
    return model_class(**unflattened_data)



def unflatten_dict(flat_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a flattened dictionary with keys like 'parent.child.grandchild' (using NESTED_SPLITTER)
    into a nested dictionary structure.
    
    Args:
        flat_dict: Dictionary with flattened keys using NESTED_SPLITTER for nesting
        
    Returns:
        Nested dictionary structure where nested objects with all None values 
        are replaced by None at the parent level.
    """
    grouped_keys = {}
    direct_keys = {}
    
    # First, categorize the keys
    for key, value in flat_dict.items():
        if NESTED_SPLITTER in key:
            prefix, rest = key.split(NESTED_SPLITTER, 1)
            if prefix not in grouped_keys:
                grouped_keys[prefix] = {}
            grouped_keys[prefix][rest] = value
        else:
            direct_keys[key] = value
    
    # Process each group and add to result
    result = dict(direct_keys)  # Start with the direct keys
    
    for prefix, nested_dict in grouped_keys.items():
        # Check if this prefix contains nested structures
        has_nested = any(NESTED_SPLITTER in key for key in nested_dict.keys())
        
        if has_nested:
            # Recursively unflatten the nested structure
            nested_result = unflatten_dict(nested_dict)
            
            # Check if all values in the nested result are None after unflattening
            is_all_none = False
            if isinstance(nested_result, dict):
                is_all_none = all(v is None for v in nested_result.values())
            
            result[prefix] = None if is_all_none else nested_result
        else:
            # Check if all values are None for a flat nested dict
            is_all_none = all(v is None for v in nested_dict.values())
            result[prefix] = None if is_all_none else nested_dict
    
    return result
