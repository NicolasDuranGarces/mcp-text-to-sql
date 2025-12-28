"""
Excel file adapter using Pandas with openpyxl.

Provides Excel-specific implementation of the DatasourcePort.
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


class ExcelAdapter(DatasourcePort):
    """
    Excel file adapter using Pandas.

    Loads Excel files into DataFrames and executes SQL queries using pandasql.
    Supports .xlsx and .xls formats.
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)
        self._dataframes: dict[str, pd.DataFrame] = {}
        self._active_sheet: str = ""

    def _get_file_path(self) -> Path:
        """Get the file path from configuration."""
        if self._datasource.file_config is None:
            raise ValueError("File config is required for Excel datasource")
        return Path(self._datasource.file_config.path)

    async def connect(self) -> bool:
        """Load Excel file into DataFrames."""
        try:
            file_path = self._get_file_path()

            logger.info(
                "loading_excel_file",
                datasource_id=self._datasource.id,
                path=str(file_path),
            )

            if not file_path.exists():
                raise FileNotFoundError(f"Excel file not found: {file_path}")

            # Get configuration
            sheet_name = self._datasource.file_config.sheet_name if self._datasource.file_config else None

            # Load Excel in thread pool
            def _load_excel() -> dict[str, pd.DataFrame]:
                if sheet_name:
                    # Load specific sheet
                    df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
                    return {sheet_name: df}
                else:
                    # Load all sheets
                    return pd.read_excel(file_path, sheet_name=None, engine="openpyxl")

            loop = asyncio.get_event_loop()
            self._dataframes = await loop.run_in_executor(None, _load_excel)

            # Normalize sheet names for SQL compatibility
            normalized: dict[str, pd.DataFrame] = {}
            for name, df in self._dataframes.items():
                safe_name = str(name).replace("-", "_").replace(" ", "_").lower()
                normalized[safe_name] = df

            self._dataframes = normalized

            # Set active sheet (first one by default)
            if self._dataframes:
                self._active_sheet = list(self._dataframes.keys())[0]

            self._connected = True
            logger.info(
                "excel_loaded",
                datasource_id=self._datasource.id,
                sheets=list(self._dataframes.keys()),
            )
            return True

        except Exception as e:
            logger.error(
                "excel_load_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise ConnectionError(f"Failed to load Excel: {e}") from e

    async def disconnect(self) -> None:
        """Release DataFrames from memory."""
        self._dataframes.clear()
        self._connected = False
        logger.info("excel_unloaded", datasource_id=self._datasource.id)

    async def validate_connection(self) -> bool:
        """Check if DataFrames are loaded."""
        return len(self._dataframes) > 0

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        max_results: int = 1000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """
        Execute SQL query against Excel data using pandasql.

        Table names in the query should match sheet names (normalized).
        """
        if not self._dataframes:
            raise ConnectionError("Excel file not loaded")

        start_time = datetime.utcnow()
        logger.info(
            "executing_excel_query",
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
                "excel_query_executed",
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
                "excel_query_timeout",
                datasource_id=self._datasource.id,
                timeout_seconds=timeout_seconds,
            )
            raise TimeoutError(f"Query timed out after {timeout_seconds} seconds")

        except Exception as e:
            logger.error(
                "excel_query_failed",
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
            if not self._dataframes:
                raise ConnectionError("DataFrames not loaded")

            # Make all DataFrames available to pandasql
            env = dict(self._dataframes)

            # Replace common table name placeholders
            normalized_query = query.replace("{{sheet}}", self._active_sheet)
            normalized_query = normalized_query.replace("$sheet", self._active_sheet)

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
        """Get Excel schema (all sheets and their columns)."""
        if not self._dataframes:
            raise ConnectionError("Excel file not loaded")

        schema: dict[str, list[dict[str, Any]]] = {}

        for sheet_name, df in self._dataframes.items():
            columns = []
            for col in df.columns:
                columns.append({
                    "name": str(col),
                    "type": str(df[col].dtype),
                    "nullable": bool(df[col].isnull().any()),
                    "sample_values": df[col].head(3).tolist(),
                })
            schema[sheet_name] = columns

        return schema

    async def get_tables(self) -> list[str]:
        """Get list of sheet names."""
        return list(self._dataframes.keys())
