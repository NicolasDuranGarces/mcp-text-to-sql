"""
Abstract port for data source operations.

This module defines the interface that all datasource adapters must implement,
following the Hexagonal Architecture (Ports & Adapters) pattern.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities.datasource import Datasource
from src.domain.entities.result import QueryResult


class DatasourcePort(ABC):
    """
    Abstract port defining operations for data source interactions.

    All datasource adapters (SQL, NoSQL, File) must implement this interface
    to ensure consistent behavior across different data source types.
    """

    def __init__(self, datasource: Datasource) -> None:
        """Initialize the adapter with a datasource configuration."""
        self._datasource = datasource
        self._connected = False

    @property
    def datasource(self) -> Datasource:
        """Get the datasource configuration."""
        return self._datasource

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to the datasource."""
        return self._connected

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the data source.

        Returns:
            True if connection was successful, False otherwise.

        Raises:
            ConnectionError: If connection fails with details.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection to the data source.

        Should be safe to call multiple times.
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate that the current connection is healthy.

        Returns:
            True if connection is valid and responsive.
        """
        pass

    @abstractmethod
    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        max_results: int = 1000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """
        Execute a query against the data source.

        Args:
            query: The query string to execute (SQL, MongoDB query, etc.)
            params: Optional parameters for parameterized queries
            max_results: Maximum number of results to return
            timeout_seconds: Query timeout in seconds

        Returns:
            QueryResult containing the data and metadata.

        Raises:
            QueryExecutionError: If query execution fails.
            TimeoutError: If query exceeds timeout.
        """
        pass

    @abstractmethod
    async def get_schema(self) -> dict[str, list[dict[str, Any]]]:
        """
        Retrieve the schema/structure of the data source.

        For SQL databases: tables and their columns
        For NoSQL: collections and sample document structure
        For files: inferred column structure

        Returns:
            Dictionary mapping table/collection names to their structure.
        """
        pass

    @abstractmethod
    async def get_tables(self) -> list[str]:
        """
        Get list of available tables/collections.

        Returns:
            List of table or collection names.
        """
        pass

    async def __aenter__(self) -> "DatasourcePort":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
