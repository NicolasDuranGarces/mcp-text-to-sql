"""
Datasource entity representing a data source connection configuration.

This module defines the core entity for managing different types of data sources
including SQL databases, NoSQL databases, and flat files.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DatasourceCategory(str, Enum):
    """Category of data source for filtering and mode selection."""

    SQL = "sql"
    NOSQL = "nosql"
    FILE = "file"


class DatasourceType(str, Enum):
    """Supported data source types."""

    # SQL Databases
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    SQLSERVER = "sqlserver"
    MARIADB = "mariadb"

    # NoSQL Databases
    MONGODB = "mongodb"
    DYNAMODB = "dynamodb"

    # File Types
    CSV = "csv"
    EXCEL = "excel"

    @property
    def category(self) -> DatasourceCategory:
        """Get the category for this datasource type."""
        sql_types = {
            DatasourceType.POSTGRESQL,
            DatasourceType.MYSQL,
            DatasourceType.SQLITE,
            DatasourceType.SQLSERVER,
            DatasourceType.MARIADB,
        }
        nosql_types = {DatasourceType.MONGODB, DatasourceType.DYNAMODB}

        if self in sql_types:
            return DatasourceCategory.SQL
        elif self in nosql_types:
            return DatasourceCategory.NOSQL
        else:
            return DatasourceCategory.FILE


@dataclass
class ConnectionConfig:
    """Configuration for database connections."""

    connection_string: str
    database: str | None = None
    schema: str | None = None
    pool_size: int = 5
    timeout_seconds: int = 30


@dataclass
class FileConfig:
    """Configuration for file-based data sources."""

    path: str
    encoding: str = "utf-8"
    delimiter: str = ","  # For CSV
    sheet_name: str | None = None  # For Excel
    has_header: bool = True


@dataclass
class SchemaCache:
    """Cached schema information for a datasource."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    cached_at: datetime | None = None
    ttl_seconds: int = 3600  # 1 hour default

    @property
    def is_valid(self) -> bool:
        """Check if the cached schema is still valid."""
        if self.cached_at is None:
            return False
        elapsed = (datetime.utcnow() - self.cached_at).total_seconds()
        return elapsed < self.ttl_seconds


@dataclass
class Datasource:
    """
    Entity representing a data source.

    A datasource can be a SQL database, NoSQL database, or a flat file.
    It contains all configuration needed to connect and query the source.
    """

    id: str
    name: str
    type: DatasourceType
    enabled: bool = True
    description: str = ""

    # Configuration - exactly one should be set based on type
    connection_config: ConnectionConfig | None = None
    file_config: FileConfig | None = None

    # Metadata and caching
    schema_cache: SchemaCache = field(default_factory=SchemaCache)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate that the configuration matches the datasource type."""
        if self.category == DatasourceCategory.FILE:
            if self.file_config is None:
                raise ValueError(f"File datasource {self.name} requires file_config")
        else:
            if self.connection_config is None:
                raise ValueError(f"Database datasource {self.name} requires connection_config")

    @property
    def category(self) -> DatasourceCategory:
        """Get the category of this datasource."""
        return self.type.category

    @property
    def is_sql(self) -> bool:
        """Check if this is a SQL datasource."""
        return self.category == DatasourceCategory.SQL

    @property
    def is_nosql(self) -> bool:
        """Check if this is a NoSQL datasource."""
        return self.category == DatasourceCategory.NOSQL

    @property
    def is_file(self) -> bool:
        """Check if this is a file datasource."""
        return self.category == DatasourceCategory.FILE

    def update_schema_cache(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        """Update the cached schema information."""
        self.schema_cache.tables = tables
        self.schema_cache.cached_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def invalidate_schema_cache(self) -> None:
        """Invalidate the cached schema."""
        self.schema_cache.cached_at = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation (safe for logging/API)."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "category": self.category.value,
            "enabled": self.enabled,
            "description": self.description,
            "has_cached_schema": self.schema_cache.is_valid,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
