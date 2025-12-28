"""
Base SQL Adapter using SQLAlchemy.

Provides common functionality for all SQL database adapters.
"""

import asyncio
from abc import abstractmethod
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import create_engine, text, inspect, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.domain.entities.datasource import Datasource
from src.domain.entities.result import (
    QueryResult,
    ResultFormat,
    ResultMetadata,
    ColumnInfo,
)
from src.domain.ports.datasource_port import DatasourcePort

logger = structlog.get_logger(__name__)


class QueryExecutionError(Exception):
    """Raised when query execution fails."""

    pass


class BaseSQLAdapter(DatasourcePort):
    """
    Base adapter for SQL databases using SQLAlchemy.

    Provides common functionality for connection management, query execution,
    and schema introspection. Specific database adapters extend this class.
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)
        self._engine: Engine | None = None
        self._metadata: MetaData | None = None

    @property
    @abstractmethod
    def dialect(self) -> str:
        """Return the SQLAlchemy dialect string for this database type."""
        pass

    def _get_connection_url(self) -> str:
        """Get the connection URL for SQLAlchemy."""
        if self._datasource.connection_config is None:
            raise ValueError("Connection config is required for SQL datasources")
        return self._datasource.connection_config.connection_string

    async def connect(self) -> bool:
        """Establish connection to the database."""
        try:
            connection_url = self._get_connection_url()

            # Mask credentials in logs
            safe_url = self._mask_credentials(connection_url)
            logger.info("connecting_to_database", datasource_id=self._datasource.id, url=safe_url)

            pool_size = self._datasource.connection_config.pool_size if self._datasource.connection_config else 5

            self._engine = create_engine(
                connection_url,
                pool_size=pool_size,
                pool_pre_ping=True,
                echo=False,
            )

            # Test connection
            await self.validate_connection()

            self._connected = True
            logger.info("database_connected", datasource_id=self._datasource.id)
            return True

        except Exception as e:
            logger.error(
                "database_connection_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise ConnectionError(f"Failed to connect to database: {e}") from e

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
        self._connected = False
        logger.info("database_disconnected", datasource_id=self._datasource.id)

    async def validate_connection(self) -> bool:
        """Validate database connection is healthy."""
        if not self._engine:
            return False

        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.warning(
                "connection_validation_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            return False

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        max_results: int = 1000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """Execute a SQL query and return results."""
        if not self._engine:
            raise QueryExecutionError("Not connected to database")

        start_time = datetime.utcnow()
        logger.info(
            "executing_query",
            datasource_id=self._datasource.id,
            query_preview=query[:100] + "..." if len(query) > 100 else query,
        )

        try:
            # Run query with timeout
            result = await asyncio.wait_for(
                self._execute_query(query, params, max_results),
                timeout=timeout_seconds,
            )

            execution_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )

            logger.info(
                "query_executed",
                datasource_id=self._datasource.id,
                row_count=len(result["data"]),
                execution_time_ms=execution_time_ms,
            )

            return QueryResult(
                query_id="",  # Will be set by calling service
                format=ResultFormat.TABULAR,
                data=result["data"],
                metadata=ResultMetadata(
                    total_rows=result["total_rows"],
                    returned_rows=len(result["data"]),
                    was_truncated=result["was_truncated"],
                    columns=result["columns"],
                    execution_time_ms=execution_time_ms,
                    datasource_id=self._datasource.id,
                    datasource_name=self._datasource.name,
                ),
            )

        except asyncio.TimeoutError:
            logger.error(
                "query_timeout",
                datasource_id=self._datasource.id,
                timeout_seconds=timeout_seconds,
            )
            raise QueryExecutionError(f"Query timed out after {timeout_seconds} seconds")

        except SQLAlchemyError as e:
            logger.error(
                "query_execution_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise QueryExecutionError(f"Query execution failed: {e}") from e

    async def _execute_query(
        self,
        query: str,
        params: dict[str, Any] | None,
        max_results: int,
    ) -> dict[str, Any]:
        """Execute query in thread pool to not block event loop."""

        def _run_query() -> dict[str, Any]:
            if self._engine is None:
                raise QueryExecutionError("Engine not initialized")

            with self._engine.connect() as conn:
                result = conn.execute(text(query), params or {})

                # Get column info - keys() returns column names as strings
                column_names = list(result.keys())
                columns = [
                    ColumnInfo(
                        name=col_name,
                        data_type="unknown",  # Type info not available from CursorResult.keys()
                        nullable=True,
                    )
                    for col_name in column_names
                ] if column_names else []

                # Fetch results with limit
                rows = []
                total_rows = 0
                was_truncated = False

                for row in result:
                    total_rows += 1
                    if len(rows) < max_results:
                        rows.append(dict(row._mapping))
                    else:
                        was_truncated = True

                return {
                    "data": rows,
                    "total_rows": total_rows,
                    "was_truncated": was_truncated,
                    "columns": columns,
                }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_query)

    async def get_schema(self) -> dict[str, list[dict[str, Any]]]:
        """Get database schema (tables and columns)."""
        if not self._engine:
            raise QueryExecutionError("Not connected to database")

        def _get_schema() -> dict[str, list[dict[str, Any]]]:
            if self._engine is None:
                return {}

            inspector = inspect(self._engine)
            schema: dict[str, list[dict[str, Any]]] = {}

            for table_name in inspector.get_table_names():
                columns = []
                for column in inspector.get_columns(table_name):
                    columns.append({
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": column.get("nullable", True),
                        "default": str(column.get("default")) if column.get("default") else None,
                        "primary_key": column.get("primary_key", False),
                    })
                schema[table_name] = columns

            return schema

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_schema)

    async def get_tables(self) -> list[str]:
        """Get list of table names."""
        if not self._engine:
            raise QueryExecutionError("Not connected to database")

        def _get_tables() -> list[str]:
            if self._engine is None:
                return []
            inspector = inspect(self._engine)
            return inspector.get_table_names()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_tables)

    @staticmethod
    def _mask_credentials(url: str) -> str:
        """Mask password in connection URL for logging."""
        import re
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)
