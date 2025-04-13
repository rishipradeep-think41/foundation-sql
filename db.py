"""
Database operations module for Foundation.
"""

import os
from typing import Dict, Any, Optional, Type, Union, List
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from jinja2sql import Jinja2SQL
from enum import Enum
from datetime import datetime

NESTED_SPLITTER = "."

j2sql = Jinja2SQL()



class Database:
    """Database operations for Foundation."""
    
    def __init__(self, db_url: Optional[str] = None) -> None:
        """Initialize the database.
        
        Args:
            db_url: SQLAlchemy database URL (e.g., postgresql://user:pass@host/db, sqlite:///path/to/db)
                   If not provided, will use DATABASE_URL environment variable
        """
        self.db_url = db_url or os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError('Database URL must be provided either through constructor or DATABASE_URL environment variable')
        
        # Create SQLAlchemy engine
        self.engine = create_engine(self.db_url)

    def get_engine(self) -> Engine:
        """Get the SQLAlchemy engine.

        Returns:
            SQLAlchemy Engine instance
        """
        return self.engine

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

        # Connect and execute schema in a transaction
        with self.engine.begin() as conn:
            try:
                for statement in schema_sql.split(';'):
                    if statement.strip():
                        conn.execute(text(statement))
            except SQLAlchemyError as e:
                raise RuntimeError(f'Failed to initialize schema: {str(e)}') from e

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
            
        # Use jinja2sql to render the template and get SQL with parameters
        try:
            query, params = j2sql.from_string(
                sql_template,
                context=context
            )
        except Exception as e:
            raise ValueError(f"Failed to render SQL. Likely SQL template & Parameter mismatch: {str(e)}") from e
        
        # Execute the SQL with parameters in a transaction
        with self.engine.connect() as conn:
            with conn.begin():
                try:
                    # Split the query into individual statements for SQLite
                    statements = [stmt.strip() for stmt in query.split(';') if stmt.strip()]
                    
                    # Track total rows affected
                    total_rows = 0
                    last_result = None
                    
                    # Execute each statement
                    for statement in statements:
                        result = conn.execute(text(statement), params)
                        total_rows += result.rowcount
                        
                        # Store the last result for potential return
                        if result.returns_rows:
                            last_result = result
                    
                    # If last result is a SELECT, return its rows
                    if last_result and last_result.returns_rows:
                        # Convert SQLAlchemy Row objects to plain dictionaries
                        # to avoid leaking SQLAlchemy implementation details
                        rows = [dict(row._mapping) for row in last_result]
                        return QueryResult(rows)
                    
                    # If no rows affected, return 0
                    return total_rows
                except SQLAlchemyError as e:
                    # The transaction will be rolled back automatically
                    raise RuntimeError(f"Failed to execute SQL: {str(e)}\nRendered SQL: {query}") from e
                    

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
        with self.engine.connect() as connection:
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


# Singleton instance
_db_instance = None

def get_db(db_url: Optional[str] = None) -> Database:
    """Get the database instance.
    
    Args:
        db_url: Optional database URL to use
        
    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_url)
    return _db_instance

def run_sql(sql_template: str, **context) -> Any:
    """Run an SQL template string with jinja2sql for rendering and parameter substitution.
    
    Args:
        sql_template: SQL template string with jinja2sql syntax
        **context: Context variables for template rendering
        
    Returns:
        For SELECT queries: A QueryResult object with methods for data access
        For INSERT/UPDATE/DELETE queries: The number of rows affected
    """
    return get_db().run_sql(sql_template, **context)


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
    
    # print(data, model_class)
    # Step 1: Unflatten the dictionary to create a nested structure
    unflattened_data = unflatten_dict(data)
    # Step 2: Create the model instance
    return model_class(**unflattened_data)


def unflatten_dict(flat_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a flattened dictionary with keys like 'parent__child__grandchild' 
    into a nested dictionary structure.
    
    Args:
        flat_dict: Dictionary with flattened keys using double-underscore notation
        
    Returns:
        Nested dictionary structure where nested objects with all None values 
        are replaced by None at the parent level.
    """
    # Group keys by common prefixes to pre-check for all-None values
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



if __name__ == "__main__":
    # Example usage
    db = get_db(db_url="sqlite:///local.db")
    db.init_schema()
