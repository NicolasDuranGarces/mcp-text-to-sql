"""
Adapter Factory for creating database adapters.

Follows Dependency Inversion Principle - high-level modules don't depend on low-level modules.
Both depend on abstractions.
"""

from typing import Protocol

from src.domain.entities.datasource import Datasource, DatasourceType
from src.domain.ports.datasource_port import DatasourcePort


class AdapterFactoryProtocol(Protocol):
    """Protocol for adapter factories - allows dependency injection."""

    def create(self, datasource: Datasource) -> DatasourcePort:
        """Create an adapter for the given datasource."""
        ...

    def supports(self, ds_type: DatasourceType) -> bool:
        """Check if this factory supports the given datasource type."""
        ...


class AdapterFactory:
    """
    Factory for creating database adapters.

    Centralizes adapter creation logic and makes it easily testable.
    Supports registration of new adapters at runtime.
    """

    def __init__(self) -> None:
        self._adapters: dict[DatasourceType, type[DatasourcePort]] = {}

    def register(self, ds_type: DatasourceType, adapter_class: type[DatasourcePort]) -> None:
        """Register an adapter class for a datasource type."""
        self._adapters[ds_type] = adapter_class

    def create(self, datasource: Datasource) -> DatasourcePort:
        """Create an adapter for the given datasource."""
        adapter_class = self._adapters.get(datasource.type)
        if not adapter_class:
            raise ValueError(f"No adapter registered for type: {datasource.type.value}")

        return adapter_class(datasource)

    def supports(self, ds_type: DatasourceType) -> bool:
        """Check if this factory supports the given datasource type."""
        return ds_type in self._adapters

    @property
    def supported_types(self) -> list[DatasourceType]:
        """Get list of supported datasource types."""
        return list(self._adapters.keys())


def create_default_factory() -> AdapterFactory:
    """
    Create a factory with all default adapters registered.

    This is a convenience function that creates a pre-configured factory.
    For testing, you can create an empty factory and register mock adapters.
    """
    # Import here to avoid circular imports and allow lazy loading
    from src.infrastructure.adapters.sql import (
        PostgreSQLAdapter,
        MySQLAdapter,
        SQLiteAdapter,
    )
    from src.infrastructure.adapters.nosql import MongoDBAdapter
    from src.infrastructure.adapters.files import CSVAdapter, ExcelAdapter

    factory = AdapterFactory()

    # Register SQL adapters
    factory.register(DatasourceType.POSTGRESQL, PostgreSQLAdapter)
    factory.register(DatasourceType.MYSQL, MySQLAdapter)
    factory.register(DatasourceType.SQLITE, SQLiteAdapter)

    # Register NoSQL adapters
    factory.register(DatasourceType.MONGODB, MongoDBAdapter)

    # Register file adapters
    factory.register(DatasourceType.CSV, CSVAdapter)
    factory.register(DatasourceType.EXCEL, ExcelAdapter)

    return factory
