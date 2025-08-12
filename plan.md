# Foundation DB Layer Refactor Plan

This document outlines the implementation plan for refactoring the Foundation DB layer to support both synchronous and asynchronous operations using a pluggable adapter architecture.

## Phase 1: Core Abstraction and Synchronous Implementation

This phase focuses on establishing the core `EngineAdapter` abstraction and refactoring the existing synchronous functionality to use the new `SQLAlchemyAdapter`.

### Checklist

-   [x] **Create `foundation_sql/db_drivers.py` file.**
    -   This file will house the `EngineAdapter` abstract class and its concrete implementations.
-   [x] **Adapter Selection & Factory (Sync by default, explicit async flag via decorator).**
    -   Add an adapter factory in `foundation_sql/db.py` that instantiates adapters.
    -   Keep existing public functions stable; do not change `db.run_sql(db_url, template, **ctx)` or `db.get_db(db_url)` signatures.
    -   Introduce a new helper for internal use only (by the decorator): `get_db_with_adapter(db_url, mode: Literal["sync","async"])` or equivalent, so existing API remains unchanged.
    -   The decorator controls adapter selection via an explicit flag (see Phase 2) and uses the helper to obtain the correct `Database`/adapter.
-   [x] **Define `EngineAdapter` Abstract Base Class in `db_drivers.py`.**
    -   Create `EngineAdapter` with the following abstract methods:
        -   `init_schema(self, schema_sql: str)`
        -   `run_sql(self, template: str, data: dict)`
        -   `close(self)`
        -   `init_pool_async(self)`
        -   `init_schema_async(self, schema_sql: str)`
        -   `run_sql_async(self, template: str, data: dict)`
        -   `close_async(self)`
-   [x] **Implement `SQLAlchemyAdapter` in `db_drivers.py`.**
    -   Create a class `SQLAlchemyAdapter` that inherits from `EngineAdapter`.
    -   Move the `sqlalchemy` engine creation and execution logic from `foundation_sql/db.py` into this class.
    -   Implement the synchronous methods:
        -   `__init__(self, dsn: str)`:
            -   Initialize `sqlalchemy.create_engine` with the given DSN.
            -   Store the engine instance.
        -   `init_schema(self, schema_sql: str)`:
            -   Implement the schema initialization logic currently in `db.Database.init_schema`.
        -   `run_sql(self, template: str, data: dict)`:
            -   Implement the SQL execution logic currently in `db.Database.run_sql`.
        -   `close(self)`:
            -   Dispose of the SQLAlchemy engine.
    -   Jinja2SQL configuration for sync:
        -   Use `Jinja2SQL(param_style="sqlalchemy")` (or default) to produce `:name` bindings compatible with SQLAlchemy.
-   [x] **Refactor `foundation_sql/db.py` to use the Adapter Pattern.**
    -   Modify the `Database` class `__init__` method to accept an `EngineAdapter` instance.
    -   The `Database` class will delegate calls to the adapter's methods (`init_schema`, `run_sql`).
    -   Remove the direct `sqlalchemy` dependencies from `db.py` that are now handled by the `SQLAlchemyAdapter`.
    -   The `get_db` function will be updated to instantiate the `Database` class with the appropriate adapter.
    -   Maintain backward compatibility by keeping `get_db(db_url)` and `run_sql(db_url, template, **ctx)` unchanged; add internal helper `get_db_with_adapter(db_url, mode)` for the decorator’s explicit selection.
-   [x] **Update `foundation_sql/query.py` to align with the new DB structure.**
    -   The `SQLQueryDecorator` currently calls `db.run_sql`. Ensure this continues to work with the refactored `db.py`.

## Phase 2: Asynchronous Implementation with `asyncpg`

This phase introduces asynchronous support by implementing the `AsyncpgAdapter` and updating the core `db.py` and `query.py` to handle async operations.

### Checklist

-   [x] **Add `asyncpg` to `requirements.txt`.**
-   [x] **Implement `AsyncpgAdapter` in `db_drivers.py`.**
    -   Create a class `AsyncpgAdapter` that inherits from `EngineAdapter`.
    -   `__init__(self, dsn: str)`:
        -   Store the DSN.
        -   Initialize `Jinja2SQL(param_style="asyncpg", enable_async=True)`.
    -   Implement the asynchronous methods:
        -   `init_pool_async(self)`
        -   `close_async(self)`
        -   `init_schema_async(self, schema_sql: str)`
        -   `run_sql_async(self, template: str, data: dict)`
-   [x] **Update `foundation_sql/db.py` for Async Support.**
    -   Add `async` methods to the `Database` class (`init_schema_async`, `run_sql_async`, etc.).
    -   These methods will delegate to the corresponding `async` methods on the adapter instance.
-   [x] **Update `foundation_sql/query.py` for Async Support.**
    -   Modify the `SQLQueryDecorator` to be async-aware and to explicitly control adapter selection via a flag.
    -   Add explicit adapter selection flag, e.g., `adapter_mode: Literal["sync","async"] = "sync"` (or `async_mode: bool = False`).
        -   If `adapter_mode == "async"` (or `async_mode is True`), the decorator uses `get_db_with_adapter(db_url, "async")` and async execution APIs.
        -   Else it uses the sync adapter path.
    -   Decorator async-awareness design:
        -   If the wrapped user function is `async def` OR `adapter_mode == "async"`, return an `async def wrapper`.
        -   Otherwise return a sync `def wrapper`.
        -   Unify template generation, caching, and result parsing across both paths to ensure parity.
        -   Keep the parsing behavior consistent with current logic (support `wrapper == 'list'`, `parse_query_to_pydantic`, integer rowcounts, and first-row mapping).
    -   Public API stability:
        -   Existing `db.run_sql(db_url, template, **ctx)` and `db.get_db(db_url)` remain available and unchanged.
        -   The decorator should use the new internal helper to pick adapter without altering public function signatures.

## Phase 3: Testing, Documentation, and Finalization

This phase ensures the new implementation is robust, well-documented, and easy to use.

### Checklist

-   [ ] **Create Unit Tests for Both Adapters.**
    -   Write tests for `SQLAlchemyAdapter` to ensure existing sync functionality is not broken.
    -   Write new tests for `AsyncpgAdapter` to verify all async functionality.
    -   Add tests for `SQLQueryDecorator` covering:
        -   Sync path vs async path (wrapper type selection, execution, and parity of results)
        -   Template caching and regeneration
        -   Adapter selection via `adapter_mode` flag
-   [ ] **Update `README.md` and Add Examples.**
    -   Document the new adapter-based architecture.
    -   Provide clear examples for both sync and async usage, including explicit adapter selection in the decorator and examples showing sync vs async wrappers.
-   [ ] **Update `prompts.md`**
    -   Reflect the new async capabilities in the prompts documentation if necessary.
-   [ ] **Code Review and Refinement.**
    -   Perform a final review of the code for clarity, consistency, and adherence to best practices.
    -   Verify public API stability (`db.run_sql`, `db.get_db`) and mark any new helper (e.g., `get_db_with_adapter`) as internal-only in docs.