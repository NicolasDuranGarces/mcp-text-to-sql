"""
Abstract port for natural language to query translation.

This module defines the interface for LLM-based translators that convert
natural language queries into executable database queries.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities.datasource import Datasource
from src.domain.entities.query import TranslationResult, QueryMode


class TranslatorPort(ABC):
    """
    Abstract port for natural language to query translation.

    Implementations should use an LLM to translate user queries
    into appropriate database queries based on available datasources.
    """

    @abstractmethod
    async def translate(
        self,
        natural_language: str,
        available_datasources: list[Datasource],
        mode: QueryMode,
        context: dict[str, Any] | None = None,
    ) -> TranslationResult:
        """
        Translate natural language to an executable query.

        Args:
            natural_language: User's query in natural language
            available_datasources: List of datasources available for querying
            mode: Current query mode (sql, nosql, files, mixed)
            context: Optional additional context (previous queries, user preferences)

        Returns:
            TranslationResult with the generated query and metadata.

        Raises:
            TranslationError: If translation fails or is ambiguous.
        """
        pass

    @abstractmethod
    async def clarify(
        self,
        natural_language: str,
        available_datasources: list[Datasource],
        ambiguity_reason: str,
    ) -> str:
        """
        Generate a clarification question when the query is ambiguous.

        Args:
            natural_language: The ambiguous user query
            available_datasources: Available datasources
            ambiguity_reason: Why the query is considered ambiguous

        Returns:
            A clarification question to ask the user.
        """
        pass

    @abstractmethod
    async def explain_query(
        self,
        query: str,
        query_type: str,
    ) -> str:
        """
        Generate a human-readable explanation of a query.

        Args:
            query: The generated query
            query_type: Type of query (sql, mongodb, etc.)

        Returns:
            Human-readable explanation of what the query does.
        """
        pass

    @abstractmethod
    async def suggest_queries(
        self,
        datasource: Datasource,
        schema: dict[str, Any],
        count: int = 5,
    ) -> list[str]:
        """
        Suggest example natural language queries for a datasource.

        Args:
            datasource: The target datasource
            schema: Schema information for the datasource
            count: Number of suggestions to generate

        Returns:
            List of suggested natural language queries.
        """
        pass
