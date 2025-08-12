from __future__ import annotations

import logging
import re  # Add missing import
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from jinja2sql import Jinja2SQL
from datetime import datetime
import asyncpg

logger = logging.getLogger(__name__)


class EngineAdapter(ABC):
    """Abstract adapter for DB engines (sync and async)."""

    # ---------- Sync API ----------
    @abstractmethod
    def init_schema(self, schema_sql: str) -> None:
        ...

    @abstractmethod
    def run_sql(self, template: str, data: Dict[str, Any]) -> Any:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    # ---------- Async API (optional) ----------
    async def init_pool_async(self) -> None:  # pragma: no cover - to be implemented by async adapters
        raise NotImplementedError

    async def init_schema_async(self, schema_sql: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def run_sql_async(self, template: str, data: Dict[str, Any]) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def close_async(self) -> None:  # pragma: no cover
        raise NotImplementedError


class SQLAlchemyAdapter(EngineAdapter):
    """Synchronous adapter backed by SQLAlchemy engine."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.engine: Engine = create_engine(self.dsn)
        # Use a valid Jinja2SQL param style compatible with SQLAlchemy bound params
        # "named" produces :name parameters which SQLAlchemy understands via text() bindings
        self.j2sql = Jinja2SQL(param_style="named")

    def init_schema(self, schema_sql: str) -> None:
        with self.engine.begin() as conn:
            try:
                for statement in schema_sql.split(';'):
                    if statement.strip():
                        conn.execute(text(statement))
            except SQLAlchemyError as e:
                raise RuntimeError(f'Failed to initialize schema: {str(e)}') from e

    def run_sql(self, template: str, data: Dict[str, Any]) -> Any:
        # ensure now is available
        if 'now' not in data:
            data['now'] = datetime.now

        try:
            # Normalize templates: remove explicit tojson filters to allow binding
            normalized = re.sub(r"\{\{\s*([^}]+?)\s*\|\s*tojson\s*\}\}", r"{{ \1 }}", template)
            query, params = self.j2sql.from_string(normalized, context=data)
        except Exception as e:
            raise ValueError(
                f"Failed to render SQL. Likely SQL template & Parameter mismatch: {str(e)}"
            ) from e

        with self.engine.connect() as conn:
            with conn.begin():
                try:
                    statements = [stmt.strip() for stmt in query.split(';') if stmt.strip()]
                    total_rows = 0
                    last_result = None

                    logger.debug(f"Executing statements: {len(statements)}")
                    for statement in statements:
                        logger.debug(f"Executing statement: {statement} {params}")
                        result = conn.execute(text(statement), params)
                        total_rows += result.rowcount
                        if result.returns_rows:
                            last_result = result

                    if last_result and last_result.returns_rows:
                        rows = [dict(row._mapping) for row in last_result]
                        logger.debug(f"Returning rows: {rows}")
                        # Return the same shape as Database currently does: a QueryResult-like object
                        # The Database facade will wrap rows if needed; here we just return rows
                        return rows

                    return total_rows
                except SQLAlchemyError as e:
                    raise RuntimeError(
                        f"Failed to execute SQL: {str(e)}\nRendered SQL: {query}"
                    ) from e

    def close(self) -> None:
        try:
            self.engine.dispose()
        except Exception:
            logger.exception("Error disposing SQLAlchemy engine")


class AsyncpgAdapter(EngineAdapter):
    """Adapter for asyncpg (async PostgreSQL driver)."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
        # jinja2sql will render SQL & parameters in asyncpg style ($1, $2, ...)
        self.j2sql = Jinja2SQL(param_style="asyncpg")

    async def init_pool_async(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(self.dsn)

    async def close_async(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def init_schema_async(self, schema_sql: str) -> None:
        await self.init_pool_async()
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            # Execute statements sequentially to ensure order
            for statement in [s.strip() for s in schema_sql.split(';') if s.strip()]:
                try:
                    logger.debug(f"Executing schema statement: {statement}")
                    await conn.execute(statement)
                except Exception as e:
                    logger.error(f"Failed to execute schema statement: {statement}")
                    raise RuntimeError(f"Failed to execute schema statement: {str(e)}") from e

    async def run_sql_async(self, template: str, data: Dict[str, Any]) -> Any:
        await self.init_pool_async()
        assert self.pool is not None

        if 'now' not in data:
            data['now'] = datetime.now

        # Special handling for templates without parameters
        if '{{' not in template:
            # No template variables, execute directly
            async with self.pool.acquire() as conn:
                is_select = template.strip().lower().startswith("select")
                if is_select:
                    records = await conn.fetch(template)
                    return [dict(r) for r in records]
                else:
                    status = await conn.execute(template)
                    return _parse_rowcount(status)

        try:
            # Add the same template normalization as SQLAlchemyAdapter
            # Normalize templates: remove explicit tojson filters to allow binding
            normalized = re.sub(r"\{\{\s*([^}]+?)\s*\|\s*tojson\s*\}\}", r"{{ \1 }}", template)
            # jinja2sql generates SQL with $1, $2... placeholders and params in correct order
            query, params_list = self.j2sql.from_string(normalized, context=data)
            
            # Debug: log parameter types
            logger.debug(f"Rendered query: {query}")
            logger.debug(f"Parameter values: {params_list}")
            logger.debug(f"Parameter types: {[(type(p).__name__, p) for p in params_list]}")
            
        except Exception as e:
            raise ValueError(
                f"Failed to render SQL. Likely SQL template & Parameter mismatch: {str(e)}"
            ) from e

        async with self.pool.acquire() as conn:
            try:
                # Handle multiple statements like SQLAlchemyAdapter
                statements = [stmt.strip() for stmt in query.split(';') if stmt.strip()]
                total_rows = 0
                last_result = None

                logger.debug(f"Executing {len(statements)} statement(s)")
                for i, statement in enumerate(statements):
                    logger.debug(f"Statement {i+1}: {statement}")
                    
                    is_select = statement.strip().lower().startswith("select")
                    
                    if is_select:
                        last_result = await conn.fetch(statement, *params_list)
                        total_rows += len(last_result)
                        logger.debug(f"SELECT returned {len(last_result)} rows")
                    else:
                        # Check if this is a schema operation or data operation
                        is_schema_op = any(keyword in statement.upper() for keyword in 
                                         ['CREATE', 'DROP', 'ALTER', 'TRUNCATE'])
                        
                        if is_schema_op:
                            # Schema operations typically don't use parameters
                            logger.debug("Executing as schema operation (no parameters)")
                            status = await conn.execute(statement)
                        else:
                            # Data operations use parameters
                            logger.debug(f"Executing as data operation with parameters: {params_list}")
                            status = await conn.execute(statement, *params_list)
                            
                        stmt_rows = _parse_rowcount(status)
                        total_rows += stmt_rows
                        logger.debug(f"Statement affected {stmt_rows} rows")

                # Return results similar to SQLAlchemyAdapter
                if last_result is not None:
                    rows = [dict(r) for r in last_result]
                    logger.debug(f"Returning {len(rows)} rows")
                    return rows
                
                logger.debug(f"Returning row count: {total_rows}")
                return total_rows
                
            except Exception as e:
                error_msg = (f"Failed to execute SQL: {str(e)}\n"
                           f"Rendered SQL: {query}\n"
                           f"Parameters: {params_list}\n"
                           f"Parameter types: {[type(p).__name__ for p in params_list]}")
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

    # Sync methods are not supported for asyncpg adapter
    def init_schema(self, schema_sql: str) -> None:  # pragma: no cover - sync not supported
        raise NotImplementedError("Use init_schema_async with AsyncpgAdapter")

    def run_sql(self, template: str, data: Dict[str, Any]) -> Any:  # pragma: no cover - sync not supported
        raise NotImplementedError("Use run_sql_async with AsyncpgAdapter")

    def close(self) -> None:  # pragma: no cover - sync not supported
        raise NotImplementedError("Use close_async with AsyncpgAdapter")


def _parse_rowcount(status: str) -> int:
    """Parse rowcount from asyncpg status like 'INSERT 0 1', 'UPDATE 3', etc."""
    try:
        parts = status.split()
        # Common patterns: 'INSERT 0 1' (rowcount is last), 'UPDATE 3' (last), 'DELETE 2'
        return int(parts[-1])
    except Exception:
        return 0