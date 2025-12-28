"""
PostgreSQL adapter using SQLAlchemy with psycopg2.

Extends BaseSQLAdapter with PostgreSQL-specific functionality.
"""

from src.domain.entities.datasource import Datasource
from src.infrastructure.adapters.sql.base_sql_adapter import BaseSQLAdapter


class PostgreSQLAdapter(BaseSQLAdapter):
    """
    PostgreSQL-specific adapter.

    Uses psycopg2-binary driver via SQLAlchemy.
    Connection string format: postgresql://user:password@host:port/database
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)

    @property
    def dialect(self) -> str:
        return "postgresql"

    def _get_connection_url(self) -> str:
        """Ensure PostgreSQL dialect prefix."""
        url = super()._get_connection_url()

        # Normalize connection string prefix
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        if not url.startswith("postgresql://"):
            raise ValueError(
                f"Invalid PostgreSQL connection string. "
                f"Expected format: postgresql://user:password@host:port/database"
            )

        return url
