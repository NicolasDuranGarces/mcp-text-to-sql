"""
Query Service for executing natural language queries.

Orchestrates the translation and execution of queries across datasources.
"""

from datetime import datetime
from typing import Any

import structlog

from src.domain.entities.query import Query, QueryMode, QueryStatus
from src.domain.entities.result import QueryResult, ResultMetadata
from src.domain.ports.translator_port import TranslatorPort
from src.application.services.datasource_service import DatasourceService
from src.infrastructure.config.settings import Settings

logger = structlog.get_logger(__name__)


class QueryService:
    """
    Service for executing natural language queries.

    Orchestrates translation, datasource selection, and query execution.
    """

    def __init__(
        self,
        datasource_service: DatasourceService,
        translator: TranslatorPort,
        settings: Settings,
    ) -> None:
        self._datasource_service = datasource_service
        self._translator = translator
        self._settings = settings
        self._last_result: QueryResult | None = None
        self._query_history: list[Query] = []

    async def execute_query(
        self,
        natural_language: str,
        mode: QueryMode | None = None,
        max_results: int | None = None,
        timeout_seconds: int | None = None,
    ) -> QueryResult:
        """
        Execute a natural language query.

        Args:
            natural_language: User's query in natural language
            mode: Query mode (overrides service default)
            max_results: Maximum results (overrides settings)
            timeout_seconds: Query timeout (overrides settings)

        Returns:
            QueryResult with data and metadata
        """
        # Create query entity
        query = Query(
            natural_language_input=natural_language,
            mode=mode or self._datasource_service.get_query_mode(),
            max_results=max_results or self._settings.max_results,
            timeout_seconds=timeout_seconds or self._settings.query_timeout_seconds,
        )

        logger.info(
            "executing_natural_language_query",
            query_id=query.id,
            input=natural_language[:100],
            mode=query.mode.value,
        )

        try:
            # Get available datasources for mode
            available_datasources = self._datasource_service.get_datasources_for_mode(query.mode)

            if not available_datasources:
                raise ValueError(
                    f"No datasources available for mode '{query.mode.value}'. "
                    "Configure and enable datasources first."
                )

            # Translate natural language to query
            query.mark_translating()
            translation = await self._translator.translate(
                natural_language=natural_language,
                available_datasources=available_datasources,
                mode=query.mode,
                context=self._build_query_context(),
            )
            query.mark_translated(translation)

            logger.info(
                "query_translated",
                query_id=query.id,
                target_datasource=translation.target_datasource_id,
                query_type=translation.query_type.value,
                confidence=translation.confidence,
            )

            # Get adapter for target datasource
            adapter = self._datasource_service.get_adapter(translation.target_datasource_id)
            if not adapter:
                raise ValueError(f"Adapter not found for datasource: {translation.target_datasource_id}")

            # Execute query
            query.mark_executing()
            start_time = datetime.utcnow()

            async with adapter:
                result = await adapter.execute(
                    query=translation.query_string,
                    max_results=query.max_results,
                    timeout_seconds=query.timeout_seconds,
                )

            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            query.mark_completed(execution_time_ms)

            # Update result with query info
            result.query_id = query.id
            result.generated_query = translation.query_string

            # Generate natural language response for non-technical users
            result.natural_response_template = translation.natural_response_template
            result.generate_natural_response()

            # Store for export
            self._last_result = result
            self._query_history.append(query)

            logger.info(
                "query_executed_successfully",
                query_id=query.id,
                row_count=result.row_count,
                execution_time_ms=execution_time_ms,
                natural_response=result.natural_response[:100],
            )

            return result

        except Exception as e:
            query.mark_failed(str(e))
            logger.error(
                "query_execution_failed",
                query_id=query.id,
                error=str(e),
            )
            raise

    async def preview_query(
        self,
        natural_language: str,
        mode: QueryMode | None = None,
    ) -> QueryResult:
        """
        Generate a query preview without execution.

        Args:
            natural_language: User's query in natural language
            mode: Query mode (overrides service default)

        Returns:
            QueryResult with generated query (no data)
        """
        query = Query(
            natural_language_input=natural_language,
            mode=mode or self._datasource_service.get_query_mode(),
            preview_only=True,
        )

        logger.info(
            "generating_query_preview",
            query_id=query.id,
            input=natural_language[:100],
        )

        try:
            available_datasources = self._datasource_service.get_datasources_for_mode(query.mode)

            if not available_datasources:
                raise ValueError(
                    f"No datasources available for mode '{query.mode.value}'."
                )

            # Translate only
            query.mark_translating()
            translation = await self._translator.translate(
                natural_language=natural_language,
                available_datasources=available_datasources,
                mode=query.mode,
                context=self._build_query_context(),
            )
            query.mark_translated(translation)

            # Get datasource info
            datasource = self._datasource_service.get_datasource(translation.target_datasource_id)
            datasource_name = datasource.name if datasource else translation.target_datasource_id

            # Return preview result
            result = QueryResult(
                query_id=query.id,
                is_preview=True,
                generated_query=translation.query_string,
                metadata=ResultMetadata(
                    datasource_id=translation.target_datasource_id,
                    datasource_name=datasource_name,
                ),
            )

            logger.info(
                "query_preview_generated",
                query_id=query.id,
                target_datasource=translation.target_datasource_id,
            )

            return result

        except Exception as e:
            query.mark_failed(str(e))
            logger.error(
                "query_preview_failed",
                query_id=query.id,
                error=str(e),
            )
            raise

    async def explain_last_query(self) -> str:
        """Get explanation of the last executed query."""
        if not self._last_result or not self._last_result.generated_query:
            return "No previous query to explain."

        last_query = self._query_history[-1] if self._query_history else None
        query_type = (
            last_query.translation.query_type.value
            if last_query and last_query.translation
            else "sql"
        )

        return await self._translator.explain_query(
            query=self._last_result.generated_query,
            query_type=query_type,
        )

    def get_last_result(self) -> QueryResult | None:
        """Get the last query result for export."""
        return self._last_result

    def get_query_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent query history."""
        return [q.to_dict() for q in self._query_history[-limit:]]

    def clear_history(self) -> None:
        """Clear query history."""
        self._query_history.clear()
        self._last_result = None

    def _build_query_context(self) -> dict[str, Any]:
        """Build context from recent queries."""
        if not self._query_history:
            return {}

        recent = self._query_history[-3:]
        context = {
            "previous_queries": [
                {
                    "input": q.natural_language_input,
                    "translated": q.translated_query,
                    "datasource": q.target_datasource_id,
                }
                for q in recent
                if q.is_translated
            ]
        }
        return context
