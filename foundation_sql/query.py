import functools
import inspect
import os
from importlib import resources as impresources
from typing import Any, Callable, Dict, Optional

from foundation_sql import db
from foundation_sql.cache import SQLTemplateCache
from foundation_sql.gen import SQLGenerator
from foundation_sql.prompt import FunctionSpec, SQLPromptGenerator

DEFAULT_SYSTEM_PROMPT = impresources.read_text("foundation_sql", "prompts.md")


class SQLQueryDecorator:
    """
    Advanced decorator for generating and executing SQL queries with comprehensive features.

    Supports:
    - Dynamic SQL template generation
    - Configurable LLM backend
    - Persistent template caching
    - Robust error handling and regeneration

    Attributes:
        name (Optional[str]): Custom name for SQL template
        regen (Optional[bool]): SQL template regeneration strategy
        config (SQLGeneratorConfig): Configuration for SQL generation
    """

    def __init__(
        self,
        name: Optional[str] = None,
        regen: Optional[bool] = None,
        repair: Optional[int] = 0,
        schema: Optional[str] = None,
        schema_path: Optional[str] = None,
        schema_inspect: bool = False,
        system_prompt: Optional[str] = None,
        system_prompt_path: Optional[str] = None,
        cache_dir: Optional[str] = "__sql__",
        db_url: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize the SQL query decorator.

        Args:
            name (Optional[str]): Custom name for SQL file/folder.
                                  Defaults to function name.
            regen (Optional[bool]): SQL template regeneration strategy.
            config (Optional[SQLGeneratorConfig]): Custom configuration
                                                   for SQL generation.
        """
        self.name = name
        self.regen = regen
        self.cache_dir = cache_dir
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        if not self.db_url:
            raise ValueError(
                "Database URL not provided either through constructor or DATABASE_URL environment variable"
            )

        if schema_inspect:
            if schema or schema_path:
                raise ValueError(
                    "Cannot provide 'schema' or 'schema_path' when 'schema_inspect' is True."
                )
            self.schema = db.extract_schema_from_db(self.db_url)
        else:
            if not schema and not schema_path:
                raise ValueError(
                    "Must provide either 'schema' or 'schema_path' when 'schema_inspect' is False."
                )
            self.schema = schema or self.load_file(schema_path)

        if system_prompt or system_prompt_path:
            self.system_prompt = system_prompt or self.load_file(system_prompt_path)
        else:
            self.system_prompt = DEFAULT_SYSTEM_PROMPT

        self.db_url = db_url
        if not self.db_url:
            raise ValueError(
                "Database URL not provided either through constructor or DATABASE_URL environment variable"
            )

        # Initialize cache and SQL generator
        self.cache = SQLTemplateCache(cache_dir=cache_dir)

        self.sql_generator = SQLGenerator(
            api_key=api_key, base_url=base_url, model=model
        )

        self.repair = repair

    def __call__(self, func: Callable) -> Callable:
        template_name = self.name or f"{func.__name__}.sql"
        fn_spec = FunctionSpec(func)
        prompt_generator = SQLPromptGenerator(
            fn_spec, template_name, self.system_prompt, self.schema
        )

        def sql_gen(
            kwargs: Dict[str, Any],
            error: Optional[str] = None,
            prev_template: Optional[str] = None,
        ):
            if self.regen or not self.cache.exists(template_name) or error:
                prompt = prompt_generator.generate_prompt(kwargs, error, prev_template)
                sql_template = self.sql_generator.generate_sql(prompt)
                self.cache.set(template_name, sql_template)
            else:
                sql_template = self.cache.get(template_name)
            return sql_template

        def _parse_result(result_data: Any):
            if fn_spec.wrapper == "list":
                return [
                    db.parse_query_to_pydantic(row, fn_spec.return_type)
                    for row in result_data.all()
                ]
            elif isinstance(result_data, int):
                return result_data
            elif fn_spec.return_type is int:
                # Best-effort mapping from non-int results to int
                # 1) QueryResult-like object
                if hasattr(result_data, "scalar") and callable(
                    getattr(result_data, "scalar")
                ):
                    try:
                        return int(result_data.scalar())
                    except (ValueError, TypeError):
                        pass
                # 2) List of rows
                if isinstance(result_data, list):
                    try:
                        return int(len(result_data))
                    except Exception:
                        pass
                # 3) Dict payloads: common keys or single numeric value
                if isinstance(result_data, dict):
                    for k in ("result", "count", "affected", "rowcount"):
                        v = result_data.get(k)
                        if isinstance(v, int):
                            return v
                    vals = list(result_data.values())
                    if len(vals) == 1 and isinstance(vals[0], int):
                        return vals[0]
                # Fallback
                return 0
            else:
                first_row = result_data.first()
                return (
                    db.parse_query_to_pydantic(first_row, fn_spec.return_type)
                    if first_row
                    else None
                )

        is_async = inspect.iscoroutinefunction(func)
        executor = WrapSqlExecution(
            func=func,
            db_url=self.db_url,
            repair=self.repair,
            sql_gen=sql_gen,
            parse_result=_parse_result,
        )
        return executor.build_wrapper(is_async)

    def load_file(self, path: str) -> str:
        """
        Load predefined table schemas.

        Returns:
            str: SQL schema definitions
        """
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"Schema file not found at {path}")

        with open(path, "r") as f:
            return f.read()


class WrapSqlExecution:

    def __init__(
        self,
        func: Callable,
        db_url: str,
        repair: Optional[int],
        sql_gen: Callable[[Dict[str, Any], Optional[str], Optional[str]], str],
        parse_result: Callable[[Any], Any],
    ) -> None:
        self.func = func
        self.db_url = db_url
        self.repair = repair
        self.sql_gen = sql_gen
        self._parse_result = parse_result

    async def _execute_async(self, **kwargs: Any):
        last_exc = None
        error = None
        sql_template = None
        attempts = (
            self.repair + 1 if isinstance(self.repair, int) and self.repair >= 0 else 1
        )
        database = db.get_db_with_adapter(self.db_url, "async")

        for _ in range(attempts):
            sql_template = self.sql_gen(kwargs, error, sql_template)
            try:
                result_data = await database.run_sql_async(sql_template, **kwargs)
                try:
                    return self._parse_result(result_data)
                except Exception as parse_err:
                    last_exc = parse_err
                    error = f"Parsing/Validation error: {parse_err}"
                    continue
            except Exception as exec_err:
                last_exc = exec_err
                error = f"Execution error: {exec_err}"
                continue

        if last_exc:
            raise last_exc
        raise RuntimeError("SQL generation failed without explicit exception")

    def _execute_sync(self, **kwargs: Any):
        last_exc = None
        error = None
        sql_template = None
        attempts = (
            self.repair + 1 if isinstance(self.repair, int) and self.repair >= 0 else 1
        )

        for _ in range(attempts):
            sql_template = self.sql_gen(kwargs, error, sql_template)
            try:
                result_data = db.run_sql(self.db_url, sql_template, **kwargs)
                try:
                    return self._parse_result(result_data)
                except Exception as parse_err:
                    last_exc = parse_err
                    error = f"Parsing/Validation error: {parse_err}"
                    continue
            except Exception as exec_err:
                last_exc = exec_err
                error = f"Execution error: {exec_err}"
                continue

        if last_exc:
            raise last_exc
        raise RuntimeError("SQL generation failed without explicit exception")

    def build_wrapper(self, is_async: bool):
        if is_async:

            @functools.wraps(self.func)
            async def async_wrapper(**kwargs: Any):
                return await self._execute_async(**kwargs)

            return async_wrapper
        else:

            @functools.wraps(self.func)
            def sync_wrapper(**kwargs: Any):
                return self._execute_sync(**kwargs)

            return sync_wrapper
