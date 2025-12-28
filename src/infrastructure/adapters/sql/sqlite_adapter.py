"""
SQLite adapter using SQLAlchemy.

Extends BaseSQLAdapter with SQLite-specific functionality.
"""

from src.domain.entities.datasource import Datasource
from src.infrastructure.adapters.sql.base_sql_adapter import BaseSQLAdapter


class SQLiteAdapter(BaseSQLAdapter):
    """
    SQLite-specific adapter.

    Uses SQLite driver via SQLAlchemy.
    Connection string format: sqlite:///path/to/database.db
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)

    @property
    def dialect(self) -> str:
        return "sqlite"

    def _get_connection_url(self) -> str:
        """Ensure SQLite dialect prefix."""
        url = super()._get_connection_url()

        if not url.startswith("sqlite:"):
            raise ValueError(
                f"Invalid SQLite connection string. "
                f"Expected format: sqlite:///path/to/database.db"
            )

        return url
