"""
Query entity representing a natural language query and its translation.

This module defines the Query entity which tracks the lifecycle of a query
from natural language input through translation and execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class QueryType(str, Enum):
    """Type of generated query based on target datasource."""

    SQL = "sql"
    MONGODB = "mongodb"
    DYNAMODB = "dynamodb"
    PANDAS = "pandas"  # For file-based queries


class QueryStatus(str, Enum):
    """Status of query execution lifecycle."""

    PENDING = "pending"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueryMode(str, Enum):
    """Query mode determining which datasources are available."""

    SQL = "sql"
    NOSQL = "nosql"
    FILES = "files"
    MIXED = "mixed"


@dataclass
class TranslationResult:
    """Result of translating natural language to a query."""

    query_string: str
    query_type: QueryType
    target_datasource_id: str
    confidence: float = 1.0
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    # Natural language response template for non-technical users
    # Uses {count} and {data} placeholders that will be replaced with actual results
    natural_response_template: str = ""


@dataclass
class Query:
    """
    Entity representing a query from natural language input.

    Tracks the full lifecycle from input through translation and execution.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    natural_language_input: str = ""
    status: QueryStatus = QueryStatus.PENDING
    mode: QueryMode = QueryMode.MIXED

    # Translation
    translation: TranslationResult | None = None

    # Execution context
    preview_only: bool = False
    max_results: int = 1000
    timeout_seconds: int = 30

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    executed_at: datetime | None = None
    execution_time_ms: int | None = None

    # Error tracking
    error_message: str | None = None
    error_details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_translated(self) -> bool:
        """Check if the query has been translated."""
        return self.translation is not None

    @property
    def translated_query(self) -> str | None:
        """Get the translated query string if available."""
        return self.translation.query_string if self.translation else None

    @property
    def target_datasource_id(self) -> str | None:
        """Get the target datasource ID if translation is complete."""
        return self.translation.target_datasource_id if self.translation else None

    def mark_translating(self) -> None:
        """Mark query as being translated."""
        self.status = QueryStatus.TRANSLATING

    def mark_translated(self, translation: TranslationResult) -> None:
        """Mark query as translated with result."""
        self.translation = translation
        self.status = QueryStatus.TRANSLATED

    def mark_executing(self) -> None:
        """Mark query as being executed."""
        self.status = QueryStatus.EXECUTING
        self.executed_at = datetime.utcnow()

    def mark_completed(self, execution_time_ms: int) -> None:
        """Mark query as successfully completed."""
        self.status = QueryStatus.COMPLETED
        self.execution_time_ms = execution_time_ms

    def mark_failed(self, error_message: str, error_details: dict[str, Any] | None = None) -> None:
        """Mark query as failed with error information."""
        self.status = QueryStatus.FAILED
        self.error_message = error_message
        self.error_details = error_details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "natural_language_input": self.natural_language_input,
            "status": self.status.value,
            "mode": self.mode.value,
            "preview_only": self.preview_only,
            "max_results": self.max_results,
            "created_at": self.created_at.isoformat(),
        }

        if self.translation:
            result["translation"] = {
                "query_string": self.translation.query_string,
                "query_type": self.translation.query_type.value,
                "target_datasource_id": self.translation.target_datasource_id,
                "confidence": self.translation.confidence,
                "explanation": self.translation.explanation,
                "warnings": self.translation.warnings,
            }

        if self.executed_at:
            result["executed_at"] = self.executed_at.isoformat()

        if self.execution_time_ms is not None:
            result["execution_time_ms"] = self.execution_time_ms

        if self.error_message:
            result["error"] = {
                "message": self.error_message,
                "details": self.error_details,
            }

        return result
