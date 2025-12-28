"""
Unit tests for DatasourceService.
"""

import pytest
from unittest.mock import patch

from src.application.services.datasource_service import DatasourceService
from src.domain.entities.datasource import DatasourceType, DatasourceCategory
from src.domain.entities.query import QueryMode


class TestDatasourceService:
    """Tests for DatasourceService."""

    def test_add_sql_datasource(self):
        """Test adding a SQL datasource."""
        service = DatasourceService()

        datasource = service.add_datasource(
            id="test_pg",
            name="Test PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/db",
        )

        assert datasource.id == "test_pg"
        assert datasource.name == "Test PostgreSQL"
        assert datasource.type == DatasourceType.POSTGRESQL
        assert datasource.enabled is True
        assert datasource.is_sql is True

    def test_add_file_datasource(self):
        """Test adding a file datasource."""
        service = DatasourceService()

        datasource = service.add_datasource(
            id="test_csv",
            name="Test CSV",
            ds_type="csv",
            file_path="/data/test.csv",
        )

        assert datasource.id == "test_csv"
        assert datasource.type == DatasourceType.CSV
        assert datasource.is_file is True
        assert datasource.file_config is not None
        assert datasource.file_config.path == "/data/test.csv"

    def test_add_datasource_missing_connection_string(self):
        """Test that adding SQL datasource without connection_string raises error."""
        service = DatasourceService()

        with pytest.raises(ValueError, match="Connection string is required"):
            service.add_datasource(
                id="test_pg",
                name="Test PostgreSQL",
                ds_type="postgresql",
            )

    def test_add_datasource_missing_file_path(self):
        """Test that adding file datasource without file_path raises error."""
        service = DatasourceService()

        with pytest.raises(ValueError, match="File path is required"):
            service.add_datasource(
                id="test_csv",
                name="Test CSV",
                ds_type="csv",
            )

    def test_remove_datasource(self):
        """Test removing a datasource."""
        service = DatasourceService()

        service.add_datasource(
            id="test_pg",
            name="Test PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/db",
        )

        assert service.get_datasource("test_pg") is not None
        assert service.remove_datasource("test_pg") is True
        assert service.get_datasource("test_pg") is None

    def test_remove_nonexistent_datasource(self):
        """Test removing a datasource that doesn't exist."""
        service = DatasourceService()
        assert service.remove_datasource("nonexistent") is False

    def test_list_datasources(self):
        """Test listing all datasources."""
        service = DatasourceService()

        service.add_datasource(
            id="pg1",
            name="PostgreSQL 1",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db1",
            enabled=True,
        )

        service.add_datasource(
            id="pg2",
            name="PostgreSQL 2",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db2",
            enabled=False,
        )

        all_ds = service.list_datasources()
        assert len(all_ds) == 2

        enabled_ds = service.list_datasources(enabled_only=True)
        assert len(enabled_ds) == 1
        assert enabled_ds[0].id == "pg1"

    def test_toggle_datasource(self):
        """Test toggling datasource enabled status."""
        service = DatasourceService()

        service.add_datasource(
            id="test_pg",
            name="Test PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
            enabled=True,
        )

        # Toggle off
        ds = service.toggle_datasource("test_pg")
        assert ds is not None
        assert ds.enabled is False

        # Toggle on
        ds = service.toggle_datasource("test_pg")
        assert ds is not None
        assert ds.enabled is True

        # Set explicitly
        ds = service.toggle_datasource("test_pg", enabled=False)
        assert ds is not None
        assert ds.enabled is False

    def test_set_query_mode(self):
        """Test setting query mode."""
        service = DatasourceService()

        mode = service.set_query_mode("sql")
        assert mode == QueryMode.SQL

        mode = service.set_query_mode(QueryMode.NOSQL)
        assert mode == QueryMode.NOSQL

    def test_get_datasources_for_mode(self):
        """Test filtering datasources by mode."""
        service = DatasourceService()

        service.add_datasource(
            id="pg1",
            name="PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
        )

        service.add_datasource(
            id="mongo1",
            name="MongoDB",
            ds_type="mongodb",
            connection_string="mongodb://localhost/db",
        )

        service.add_datasource(
            id="csv1",
            name="CSV",
            ds_type="csv",
            file_path="/data/test.csv",
        )

        # SQL mode
        sql_ds = service.get_datasources_for_mode(QueryMode.SQL)
        assert len(sql_ds) == 1
        assert sql_ds[0].id == "pg1"

        # NoSQL mode
        nosql_ds = service.get_datasources_for_mode(QueryMode.NOSQL)
        assert len(nosql_ds) == 1
        assert nosql_ds[0].id == "mongo1"

        # Files mode
        file_ds = service.get_datasources_for_mode(QueryMode.FILES)
        assert len(file_ds) == 1
        assert file_ds[0].id == "csv1"

        # Mixed mode
        all_ds = service.get_datasources_for_mode(QueryMode.MIXED)
        assert len(all_ds) == 3

    def test_create_adapter(self):
        """Test adapter creation for different datasource types."""
        from src.infrastructure.adapters.sql import PostgreSQLAdapter

        service = DatasourceService()

        service.add_datasource(
            id="test_pg",
            name="Test PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
        )

        adapter = service.get_adapter("test_pg")
        assert adapter is not None
        assert isinstance(adapter, PostgreSQLAdapter)

    def test_get_adapter_caching(self):
        """Test that adapters are cached."""
        service = DatasourceService()

        service.add_datasource(
            id="test_pg",
            name="Test PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
        )

        adapter1 = service.get_adapter("test_pg")
        adapter2 = service.get_adapter("test_pg")

        assert adapter1 is adapter2
