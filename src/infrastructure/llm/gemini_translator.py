"""
Google Gemini-based natural language to query translator.

Uses Gemini to translate natural language into executable database queries.
"""

import json
from typing import Any

import structlog
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from src.domain.entities.datasource import Datasource, DatasourceCategory
from src.domain.entities.query import QueryMode, QueryType, TranslationResult
from src.domain.ports.translator_port import TranslatorPort

logger = structlog.get_logger(__name__)


class TranslationError(Exception):
    """Raised when translation fails."""

    pass


class GeminiTranslator(TranslatorPort):
    """
    Google Gemini-based translator for natural language to query conversion.

    Uses Gemini with structured prompts to generate accurate queries.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._temperature = temperature
        self._max_tokens = max_tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def translate(
        self,
        natural_language: str,
        available_datasources: list[Datasource],
        mode: QueryMode,
        context: dict[str, Any] | None = None,
    ) -> TranslationResult:
        """Translate natural language to an executable query."""
        logger.info(
            "translating_query_gemini",
            input=natural_language[:100],
            mode=mode.value,
            datasource_count=len(available_datasources),
        )

        # Filter datasources by mode
        filtered_sources = self._filter_by_mode(available_datasources, mode)

        if not filtered_sources:
            raise TranslationError(
                f"No datasources available for mode '{mode.value}'. "
                "Configure and enable appropriate datasources first."
            )

        # Build context about available schemas
        schema_context = self._build_schema_context(filtered_sources)

        # Build the full prompt
        full_prompt = self._build_full_prompt(
            natural_language,
            schema_context,
            mode,
            context,
        )

        try:
            response = await self._model.generate_content_async(
                full_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=self._temperature,
                    max_output_tokens=self._max_tokens,
                ),
            )

            result_text = response.text
            if not result_text:
                raise TranslationError("Empty response from Gemini")

            # Extract JSON from response
            result = self._extract_json(result_text)

            # Validate and parse response
            return self._parse_translation_result(result, filtered_sources)

        except json.JSONDecodeError as e:
            logger.error("translation_json_error", error=str(e))
            raise TranslationError(f"Failed to parse Gemini response: {e}") from e

        except Exception as e:
            logger.error("translation_failed", error=str(e))
            raise TranslationError(f"Translation failed: {e}") from e

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from Gemini's response text."""
        import re
        
        # Look for JSON block
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
        
        raise json.JSONDecodeError("No JSON found in response", text, 0)

    async def clarify(
        self,
        natural_language: str,
        available_datasources: list[Datasource],
        ambiguity_reason: str,
    ) -> str:
        """Generate a clarification question for ambiguous queries."""
        prompt = f"""The user asked: "{natural_language}"

This query is ambiguous because: {ambiguity_reason}

Available datasources:
{self._format_datasource_list(available_datasources)}

Generate a clear, helpful question to ask the user for clarification.
Be specific about what information you need."""

        response = await self._model.generate_content_async(prompt)
        return response.text or "Could you please clarify your query?"

    async def explain_query(self, query: str, query_type: str) -> str:
        """Generate a human-readable explanation of a query."""
        prompt = f"""Explain what this {query_type} query does in simple terms:

```{query_type}
{query}
```

Explain it in 2-3 sentences, focusing on what data it retrieves and any conditions."""

        response = await self._model.generate_content_async(prompt)
        return response.text or "Unable to explain query."

    async def suggest_queries(
        self,
        datasource: Datasource,
        schema: dict[str, Any],
        count: int = 5,
    ) -> list[str]:
        """Generate example natural language queries for a datasource."""
        prompt = f"""Given this database schema:

Datasource: {datasource.name} (Type: {datasource.type.value})

Tables/Collections:
{json.dumps(schema, indent=2)}

Generate {count} example natural language questions that a user might ask about this data.
Make the questions practical and diverse (aggregations, filters, joins, etc.).

Return as a JSON object with a "suggestions" array of strings."""

        response = await self._model.generate_content_async(prompt)
        result = self._extract_json(response.text or '{"suggestions": []}')
        return result.get("suggestions", result.get("questions", []))[:count]

    def _filter_by_mode(
        self,
        datasources: list[Datasource],
        mode: QueryMode,
    ) -> list[Datasource]:
        """Filter datasources based on query mode."""
        if mode == QueryMode.MIXED:
            return [ds for ds in datasources if ds.enabled]

        category_map = {
            QueryMode.SQL: DatasourceCategory.SQL,
            QueryMode.NOSQL: DatasourceCategory.NOSQL,
            QueryMode.FILES: DatasourceCategory.FILE,
        }

        target_category = category_map.get(mode)
        return [
            ds for ds in datasources
            if ds.enabled and ds.category == target_category
        ]

    def _build_schema_context(self, datasources: list[Datasource]) -> str:
        """Build schema context string for the prompt."""
        context_parts = []

        for ds in datasources:
            schema_info = ds.schema_cache.tables if ds.schema_cache.is_valid else {}

            ds_info = f"""
### {ds.name} ({ds.type.value})
ID: {ds.id}
Category: {ds.category.value}
"""
            if schema_info:
                ds_info += f"Schema:\n{json.dumps(schema_info, indent=2)}"
            else:
                ds_info += "Schema: Not cached (will be fetched if selected)"

            context_parts.append(ds_info)

        return "\n".join(context_parts)

    def _build_full_prompt(
        self,
        natural_language: str,
        schema_context: str,
        mode: QueryMode,
        context: dict[str, Any] | None,
    ) -> str:
        """Build the full prompt for Gemini."""
        system_part = """You are an expert database query translator. Your task is to:
1. Understand the user's natural language query
2. Select the most appropriate datasource
3. Generate the correct query for that datasource type

IMPORTANT RULES:
- Generate ONLY SELECT/read queries (no INSERT, UPDATE, DELETE, DROP, etc.)
- For SQL databases, use standard SQL syntax appropriate for the dialect
- For MongoDB, generate a JSON query document with "collection", "filter", and optional "projection"
- For file-based sources (CSV/Excel), generate SQL that can be run with pandasql

Always respond with a JSON object containing:
{
    "datasource_id": "id of the selected datasource",
    "query_type": "sql" | "mongodb" | "dynamodb" | "pandas",
    "query": "the generated query string",
    "confidence": 0.0 to 1.0,
    "explanation": "brief explanation of what the query does",
    "warnings": ["any warnings or assumptions made"]
}

Respond ONLY with the JSON object, no additional text."""

        if mode == QueryMode.SQL:
            system_part += "\n\nFocus on SQL databases only."
        elif mode == QueryMode.NOSQL:
            system_part += "\n\nFocus on NoSQL databases (MongoDB, DynamoDB) only."
        elif mode == QueryMode.FILES:
            system_part += "\n\nFocus on file-based sources (CSV, Excel) only."

        user_part = f"""## User Query
{natural_language}

## Available Datasources
{schema_context}
"""

        if context and "previous_queries" in context:
            user_part += f"\n## Previous Queries (for context)\n{context['previous_queries']}"

        return f"{system_part}\n\n{user_part}"

    def _parse_translation_result(
        self,
        result: dict[str, Any],
        available_datasources: list[Datasource],
    ) -> TranslationResult:
        """Parse and validate response into TranslationResult."""
        datasource_id = result.get("datasource_id")
        if not datasource_id:
            raise TranslationError("Response missing 'datasource_id'")

        # Verify datasource exists
        matching_ds = next(
            (ds for ds in available_datasources if ds.id == datasource_id),
            None,
        )
        if not matching_ds:
            raise TranslationError(f"Selected unknown datasource: {datasource_id}")

        # Parse query type
        query_type_str = result.get("query_type", "sql").lower()
        query_type_map = {
            "sql": QueryType.SQL,
            "mongodb": QueryType.MONGODB,
            "dynamodb": QueryType.DYNAMODB,
            "pandas": QueryType.PANDAS,
        }
        query_type = query_type_map.get(query_type_str, QueryType.SQL)

        return TranslationResult(
            query_string=result.get("query", ""),
            query_type=query_type,
            target_datasource_id=datasource_id,
            confidence=float(result.get("confidence", 0.8)),
            explanation=result.get("explanation", ""),
            warnings=result.get("warnings", []),
        )

    def _format_datasource_list(self, datasources: list[Datasource]) -> str:
        """Format datasource list for prompts."""
        return "\n".join(
            f"- {ds.name} ({ds.type.value}): {ds.description or 'No description'}"
            for ds in datasources
        )
