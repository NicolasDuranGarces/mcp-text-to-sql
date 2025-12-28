"""
Result entity representing query execution results.

This module defines the QueryResult entity which holds the data returned
from executing a query, along with metadata and export capabilities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ResultFormat(str, Enum):
    """Format of result data."""

    TABULAR = "tabular"  # List of dictionaries (rows)
    DOCUMENT = "document"  # Single document (MongoDB style)
    DOCUMENTS = "documents"  # List of documents
    SCALAR = "scalar"  # Single value
    EMPTY = "empty"


class ExportFormat(str, Enum):
    """Supported export formats."""

    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"


@dataclass
class ColumnInfo:
    """Information about a result column."""

    name: str
    data_type: str
    nullable: bool = True


@dataclass
class ResultMetadata:
    """Metadata about query result."""

    total_rows: int = 0
    returned_rows: int = 0
    was_truncated: bool = False
    columns: list[ColumnInfo] = field(default_factory=list)
    execution_time_ms: int = 0
    datasource_id: str = ""
    datasource_name: str = ""


@dataclass
class QueryResult:
    """
    Entity representing the result of a query execution.

    Contains the data, metadata, and methods for formatting/exporting results.
    """

    query_id: str
    format: ResultFormat = ResultFormat.TABULAR
    data: list[dict[str, Any]] = field(default_factory=list)
    metadata: ResultMetadata = field(default_factory=ResultMetadata)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # For preview mode
    generated_query: str | None = None
    is_preview: bool = False

    # Natural language response for non-technical users
    natural_response_template: str = ""
    natural_response: str = ""

    @property
    def is_empty(self) -> bool:
        """Check if the result is empty."""
        return len(self.data) == 0

    @property
    def row_count(self) -> int:
        """Get the number of rows in the result."""
        return len(self.data)

    @property
    def column_names(self) -> list[str]:
        """Get column names from metadata or infer from data."""
        if self.metadata.columns:
            return [col.name for col in self.metadata.columns]
        elif self.data:
            return list(self.data[0].keys())
        return []

    def generate_natural_response(self, template: str = "") -> str:
        """Generate a human-readable response using the template and actual data."""
        template = template or self.natural_response_template
        if not template:
            template = "Se encontraron {count} resultado(s)."

        # Determine the count value
        # If result is a single row with a single numeric value (aggregation like COUNT), use that value
        count_value = len(self.data)
        if len(self.data) == 1 and len(self.data[0]) == 1:
            value = list(self.data[0].values())[0]
            if isinstance(value, (int, float)):
                count_value = value

        # Format sample data as readable text
        sample_text = ""
        if self.data:
            # If it's a scalar value, don't show it as a sample list
            if len(self.data) == 1 and len(self.data[0]) == 1:
               pass
            else:
                sample_rows = self.data[:5]  # First 5 rows
                formatted_rows = []
                for i, row in enumerate(sample_rows, 1):
                    row_str = ", ".join(f"{k}: {v}" for k, v in row.items())
                    formatted_rows.append(f"  {i}. {row_str}")
                sample_text = "\n".join(formatted_rows)
                if len(self.data) > 5:
                    sample_text += f"\n  ... y {len(self.data) - 5} más"

        # Replace placeholders
        response = template.replace("{count}", str(count_value))
        response = response.replace("{sample}", sample_text)

        self.natural_response = response
        return response

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for API response."""
        result: dict[str, Any] = {
            "query_id": self.query_id,
            "format": self.format.value,
            "is_preview": self.is_preview,
            "created_at": self.created_at.isoformat(),
            "natural_response": self.natural_response,
            "metadata": {
                "total_rows": self.metadata.total_rows,
                "returned_rows": self.metadata.returned_rows,
                "was_truncated": self.metadata.was_truncated,
                "execution_time_ms": self.metadata.execution_time_ms,
                "datasource_id": self.metadata.datasource_id,
                "datasource_name": self.metadata.datasource_name,
                "columns": [
                    {"name": col.name, "data_type": col.data_type, "nullable": col.nullable}
                    for col in self.metadata.columns
                ],
            },
        }

        if self.is_preview:
            result["generated_query"] = self.generated_query
        else:
            result["data"] = self.data

        return result

    def to_csv_string(self) -> str:
        """Convert result to CSV string."""
        if not self.data:
            return ""

        import csv
        import io

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.column_names)
        writer.writeheader()
        writer.writerows(self.data)
        return output.getvalue()

    def to_json_string(self, indent: int = 2) -> str:
        """Convert result to JSON string."""
        import json

        return json.dumps(self.data, indent=indent, default=str)

    def get_preview_response(self) -> dict[str, Any]:
        """Get response for preview mode (query without execution)."""
        return {
            "query_id": self.query_id,
            "is_preview": True,
            "generated_query": self.generated_query,
            "target_datasource": {
                "id": self.metadata.datasource_id,
                "name": self.metadata.datasource_name,
            },
            "message": "Query generated successfully. Use 'query' tool to execute.",
        }
