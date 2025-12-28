"""
Pytest configuration and fixtures.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-for-testing"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["LOG_FORMAT"] = "console"


@pytest.fixture
def mock_datasource():
    """Create a mock datasource for testing."""
    from src.domain.entities.datasource import (
        Datasource,
        DatasourceType,
        ConnectionConfig,
    )

    return Datasource(
        id="test_postgres",
        name="Test PostgreSQL",
        type=DatasourceType.POSTGRESQL,
        enabled=True,
        description="Test database",
        connection_config=ConnectionConfig(
            connection_string="postgresql://user:pass@localhost:5432/testdb",
        ),
    )


@pytest.fixture
def mock_file_datasource():
    """Create a mock file datasource for testing."""
    from src.domain.entities.datasource import (
        Datasource,
        DatasourceType,
        FileConfig,
    )

    return Datasource(
        id="test_csv",
        name="Test CSV",
        type=DatasourceType.CSV,
        enabled=True,
        description="Test CSV file",
        file_config=FileConfig(
            path="/data/test.csv",
        ),
    )


@pytest.fixture
def mock_translator():
    """Create a mock translator for testing."""
    from src.domain.entities.query import TranslationResult, QueryType

    translator = AsyncMock()
    translator.translate.return_value = TranslationResult(
        query_string="SELECT * FROM users LIMIT 10",
        query_type=QueryType.SQL,
        target_datasource_id="test_postgres",
        confidence=0.95,
        explanation="Selecting all users with a limit of 10",
    )
    return translator


@pytest.fixture
def mock_adapter():
    """Create a mock datasource adapter for testing."""
    from src.domain.entities.result import QueryResult, ResultFormat, ResultMetadata

    adapter = AsyncMock()
    adapter.connect.return_value = True
    adapter.disconnect.return_value = None
    adapter.validate_connection.return_value = True

    adapter.execute.return_value = QueryResult(
        query_id="test-query-id",
        format=ResultFormat.TABULAR,
        data=[
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ],
        metadata=ResultMetadata(
            total_rows=2,
            returned_rows=2,
            execution_time_ms=50,
        ),
    )

    adapter.get_schema.return_value = {
        "users": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "name", "type": "varchar", "nullable": True},
        ]
    }

    adapter.get_tables.return_value = ["users", "orders"]

    # Make it work as async context manager
    adapter.__aenter__.return_value = adapter
    adapter.__aexit__.return_value = None

    return adapter


@pytest.fixture
def settings():
    """Create test settings."""
    from src.infrastructure.config.settings import Settings

    return Settings(
        openai_api_key="test-key",
        debug=True,
        log_level="DEBUG",
        log_format="console",
    )
