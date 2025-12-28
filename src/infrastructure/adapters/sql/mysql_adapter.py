"""
MySQL adapter using SQLAlchemy with PyMySQL.

Extends BaseSQLAdapter with MySQL-specific functionality.
"""

from src.domain.entities.datasource import Datasource
from src.infrastructure.adapters.sql.base_sql_adapter import BaseSQLAdapter


class MySQLAdapter(BaseSQLAdapter):
    """
    MySQL-specific adapter.

    Uses PyMySQL driver via SQLAlchemy.
    Connection string format: mysql+pymysql://user:password@host:port/database
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)

    @property
    def dialect(self) -> str:
        return "mysql"

    def _get_connection_url(self) -> str:
        """Ensure MySQL dialect prefix with PyMySQL driver."""
        url = super()._get_connection_url()

        # Normalize connection string prefix
        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+pymysql://", 1)

        if not url.startswith("mysql+pymysql://"):
            raise ValueError(
                f"Invalid MySQL connection string. "
                f"Expected format: mysql+pymysql://user:password@host:port/database"
            )

        return url
