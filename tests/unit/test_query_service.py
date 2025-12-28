"""
Unit tests for QueryService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.services.query_service import QueryService
from src.application.services.datasource_service import DatasourceService
from src.domain.entities.query import QueryMode, QueryType, TranslationResult
from src.domain.entities.result import QueryResult, ResultFormat, ResultMetadata


class TestQueryService:
    """Tests for QueryService."""

    @pytest.fixture
    def query_service(self, mock_translator, mock_adapter, settings):
        """Create QueryService with mocked dependencies."""
        datasource_service = DatasourceService()

        # Add test datasource
        datasource_service.add_datasource(
            id="test_postgres",
            name="Test PostgreSQL",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
        )

        # Mock the adapter creation
        with patch.object(datasource_service, "get_adapter", return_value=mock_adapter):
            service = QueryService(
                datasource_service=datasource_service,
                translator=mock_translator,
                settings=settings,
            )

            # Patch again for the actual test
            service._datasource_service.get_adapter = MagicMock(return_value=mock_adapter)

            yield service

    @pytest.mark.asyncio
    async def test_execute_query_success(self, query_service, mock_translator, mock_adapter):
        """Test successful query execution."""
        result = await query_service.execute_query(
            natural_language="Show me all users",
        )

        assert result is not None
        assert result.row_count == 2
        assert result.data[0]["name"] == "Alice"

        mock_translator.translate.assert_called_once()
        mock_adapter.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_with_mode_override(self, query_service, mock_translator):
        """Test query execution with mode override."""
        await query_service.execute_query(
            natural_language="Show me all users",
            mode=QueryMode.SQL,
        )

        # Verify translator was called with correct mode
        call_args = mock_translator.translate.call_args
        assert call_args.kwargs["mode"] == QueryMode.SQL

    @pytest.mark.asyncio
    async def test_execute_query_with_max_results(self, query_service, mock_adapter):
        """Test query execution with max_results override."""
        await query_service.execute_query(
            natural_language="Show me all users",
            max_results=100,
        )

        # Verify adapter was called with correct max_results
        call_args = mock_adapter.execute.call_args
        assert call_args.kwargs["max_results"] == 100

    @pytest.mark.asyncio
    async def test_preview_query(self, query_service, mock_translator):
        """Test query preview without execution."""
        result = await query_service.preview_query(
            natural_language="Show me all users",
        )

        assert result is not None
        assert result.is_preview is True
        assert result.generated_query is not None

        mock_translator.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_query_no_datasources(self, query_service):
        """Test preview fails when no datasources available."""
        # Remove all datasources
        query_service._datasource_service._datasources.clear()

        with pytest.raises(ValueError, match="No datasources available"):
            await query_service.preview_query(
                natural_language="Show me all users",
            )

    def test_get_last_result(self, query_service):
        """Test getting last result."""
        assert query_service.get_last_result() is None

    def test_get_query_history(self, query_service):
        """Test getting query history."""
        history = query_service.get_query_history()
        assert history == []

    @pytest.mark.asyncio
    async def test_query_history_tracking(self, query_service):
        """Test that queries are tracked in history."""
        await query_service.execute_query(
            natural_language="Show me all users",
        )

        history = query_service.get_query_history()
        assert len(history) == 1
        assert history[0]["natural_language_input"] == "Show me all users"

    def test_clear_history(self, query_service):
        """Test clearing history."""
        query_service._query_history.append(MagicMock())
        query_service._last_result = MagicMock()

        query_service.clear_history()

        assert query_service.get_query_history() == []
        assert query_service.get_last_result() is None


class TestQueryServiceErrorHandling:
    """Tests for QueryService error handling."""

    @pytest.fixture
    def failing_translator(self):
        """Create a translator that raises errors."""
        translator = AsyncMock()
        translator.translate.side_effect = ValueError("Translation failed")
        return translator

    @pytest.fixture
    def failing_adapter(self):
        """Create an adapter that raises errors."""
        adapter = AsyncMock()
        adapter.execute.side_effect = TimeoutError("Query timed out")
        adapter.__aenter__.return_value = adapter
        adapter.__aexit__.return_value = None
        return adapter

    @pytest.mark.asyncio
    async def test_translation_error(self, failing_translator, settings):
        """Test handling of translation errors."""
        datasource_service = DatasourceService()
        datasource_service.add_datasource(
            id="test_pg",
            name="Test",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
        )

        service = QueryService(
            datasource_service=datasource_service,
            translator=failing_translator,
            settings=settings,
        )

        with pytest.raises(ValueError, match="Translation failed"):
            await service.execute_query("Show me users")

    @pytest.mark.asyncio
    async def test_execution_error(self, mock_translator, failing_adapter, settings):
        """Test handling of execution errors."""
        datasource_service = DatasourceService()
        datasource_service.add_datasource(
            id="test_postgres",
            name="Test",
            ds_type="postgresql",
            connection_string="postgresql://localhost/db",
        )

        with patch.object(datasource_service, "get_adapter", return_value=failing_adapter):
            service = QueryService(
                datasource_service=datasource_service,
                translator=mock_translator,
                settings=settings,
            )
            service._datasource_service.get_adapter = MagicMock(return_value=failing_adapter)

            with pytest.raises(TimeoutError, match="Query timed out"):
                await service.execute_query("Show me users")
