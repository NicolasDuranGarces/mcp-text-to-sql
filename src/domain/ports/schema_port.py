"""
Abstract port for schema operations.

This module defines the interface for schema discovery and caching operations
across different datasource types.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities.datasource import Datasource


class SchemaPort(ABC):
    """
    Abstract port for schema management operations.

    Handles schema discovery, caching, and introspection for datasources.
    """

    @abstractmethod
    async def discover_schema(self, datasource: Datasource) -> dict[str, list[dict[str, Any]]]:
        """
        Discover and return the schema of a datasource.

        Args:
            datasource: The datasource to discover schema for

        Returns:
            Dictionary mapping table/collection names to column/field info.
            Each field info contains: name, type, nullable, constraints, etc.
        """
        pass

    @abstractmethod
    async def cache_schema(
        self,
        datasource_id: str,
        schema: dict[str, list[dict[str, Any]]],
        ttl_seconds: int = 3600,
    ) -> None:
        """
        Cache schema information for faster access.

        Args:
            datasource_id: ID of the datasource
            schema: Schema information to cache
            ttl_seconds: Time-to-live for cache entry
        """
        pass

    @abstractmethod
    async def get_cached_schema(
        self, datasource_id: str
    ) -> dict[str, list[dict[str, Any]]] | None:
        """
        Retrieve cached schema if available and valid.

        Args:
            datasource_id: ID of the datasource

        Returns:
            Cached schema if valid, None otherwise.
        """
        pass

    @abstractmethod
    async def invalidate_cache(self, datasource_id: str) -> None:
        """
        Invalidate cached schema for a datasource.

        Args:
            datasource_id: ID of the datasource
        """
        pass

    @abstractmethod
    async def describe_table(
        self,
        datasource: Datasource,
        table_name: str,
    ) -> dict[str, Any]:
        """
        Get detailed description of a specific table/collection.

        Args:
            datasource: The datasource
            table_name: Name of the table or collection

        Returns:
            Detailed information including columns, types, constraints,
            sample data, and statistics.
        """
        pass

    @abstractmethod
    async def infer_types_from_file(
        self,
        file_path: str,
        sample_rows: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Infer data types from a file (CSV, Excel).

        Args:
            file_path: Path to the file
            sample_rows: Number of rows to sample for type inference

        Returns:
            List of column information with inferred types.
        """
        pass
