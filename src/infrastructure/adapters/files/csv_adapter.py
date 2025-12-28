"""
CSV file adapter using Pandas.

Provides CSV-specific implementation of the DatasourcePort.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from pandasql import sqldf

from src.domain.entities.datasource import Datasource
from src.domain.entities.result import (
    QueryResult,
    ResultFormat,
    ResultMetadata,
    ColumnInfo,
)
from src.domain.ports.datasource_port import DatasourcePort

logger = structlog.get_logger(__name__)


class CSVAdapter(DatasourcePort):
    """
    CSV file adapter using Pandas.

    Loads CSV files into DataFrames and executes SQL queries using pandasql.
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)
        self._dataframe: pd.DataFrame | None = None
        self._table_name: str = ""

    def _get_file_path(self) -> Path:
        """Get the file path from configuration."""
        if self._datasource.file_config is None:
            raise ValueError("File config is required for CSV datasource")
        return Path(self._datasource.file_config.path)

    async def connect(self) -> bool:
        """Load CSV file into DataFrame."""
        try:
            file_path = self._get_file_path()

            logger.info(
                "loading_csv_file",
                datasource_id=self._datasource.id,
                path=str(file_path),
            )

            if not file_path.exists():
                raise FileNotFoundError(f"CSV file not found: {file_path}")

            # Get configuration
            encoding = self._datasource.file_config.encoding if self._datasource.file_config else "utf-8"
            delimiter = self._datasource.file_config.delimiter if self._datasource.file_config else ","
            has_header = self._datasource.file_config.has_header if self._datasource.file_config else True

            # Load CSV in thread pool
            def _load_csv() -> pd.DataFrame:
                return pd.read_csv(
                    file_path,
                    encoding=encoding,
                    delimiter=delimiter,
                    header=0 if has_header else None,
                )

            loop = asyncio.get_event_loop()
            self._dataframe = await loop.run_in_executor(None, _load_csv)

            # Use filename without extension as table name
            self._table_name = file_path.stem.replace("-", "_").replace(" ", "_").lower()

            self._connected = True
            logger.info(
                "csv_loaded",
                datasource_id=self._datasource.id,
                rows=len(self._dataframe),
                columns=list(self._dataframe.columns),
            )
            return True

        except Exception as e:
            logger.error(
                "csv_load_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise ConnectionError(f"Failed to load CSV: {e}") from e

    async def disconnect(self) -> None:
        """Release DataFrame from memory."""
        self._dataframe = None
        self._connected = False
        logger.info("csv_unloaded", datasource_id=self._datasource.id)

    async def validate_connection(self) -> bool:
        """Check if DataFrame is loaded."""
        return self._dataframe is not None

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        max_results: int = 1000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """
        Execute SQL query against the CSV data using pandasql.

        The table name in the query should match the CSV filename (without extension).
        """
        if self._dataframe is None:
            raise ConnectionError("CSV file not loaded")

        start_time = datetime.utcnow()
        logger.info(
            "executing_csv_query",
            datasource_id=self._datasource.id,
            query_preview=query[:100] + "..." if len(query) > 100 else query,
        )

        try:
            result = await asyncio.wait_for(
                self._execute_query(query, max_results),
                timeout=timeout_seconds,
            )

            execution_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )

            logger.info(
                "csv_query_executed",
                datasource_id=self._datasource.id,
                row_count=len(result["data"]),
                execution_time_ms=execution_time_ms,
            )

            return QueryResult(
                query_id="",
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
                "csv_query_timeout",
                datasource_id=self._datasource.id,
                timeout_seconds=timeout_seconds,
            )
            raise TimeoutError(f"Query timed out after {timeout_seconds} seconds")

        except Exception as e:
            logger.error(
                "csv_query_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise ValueError(f"Query execution failed: {e}") from e

    async def _execute_query(
        self,
        query: str,
        max_results: int,
    ) -> dict[str, Any]:
        """Execute SQL query using pandasql."""

        def _run_query() -> dict[str, Any]:
            if self._dataframe is None:
                raise ConnectionError("DataFrame not loaded")

            # Make DataFrame available to pandasql using the table name
            env = {self._table_name: self._dataframe}

            # Replace common table name placeholders
            normalized_query = query.replace("{{table}}", self._table_name)
            normalized_query = normalized_query.replace("$table", self._table_name)

            # Execute query
            result_df = sqldf(normalized_query, env)

            # Get total rows
            total_rows = len(result_df)
            was_truncated = total_rows > max_results

            # Limit results
            if was_truncated:
                result_df = result_df.head(max_results)

            # Build column info
            columns = [
                ColumnInfo(
                    name=str(col),
                    data_type=str(result_df[col].dtype),
                    nullable=result_df[col].isnull().any(),
                )
                for col in result_df.columns
            ]

            # Convert to list of dicts
            data = result_df.to_dict(orient="records")

            return {
                "data": data,
                "total_rows": total_rows,
                "was_truncated": was_truncated,
                "columns": columns,
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_query)

    async def get_schema(self) -> dict[str, list[dict[str, Any]]]:
        """Get CSV schema (column info)."""
        if self._dataframe is None:
            raise ConnectionError("CSV file not loaded")

        columns = []
        for col in self._dataframe.columns:
            columns.append({
                "name": str(col),
                "type": str(self._dataframe[col].dtype),
                "nullable": bool(self._dataframe[col].isnull().any()),
                "sample_values": self._dataframe[col].head(3).tolist(),
            })

        return {self._table_name: columns}

    async def get_tables(self) -> list[str]:
        """Get table name (CSV filename)."""
        return [self._table_name] if self._table_name else []
