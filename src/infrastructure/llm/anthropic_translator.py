"""
Anthropic Claude-based natural language to query translator.

Uses Claude to translate natural language into executable database queries.
"""

import json
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.domain.entities.datasource import Datasource, DatasourceCategory
from src.domain.entities.query import QueryMode, QueryType, TranslationResult
from src.domain.ports.translator_port import TranslatorPort

logger = structlog.get_logger(__name__)


class TranslationError(Exception):
    """Raised when translation fails."""

    pass


class AnthropicTranslator(TranslatorPort):
    """
    Anthropic Claude-based translator for natural language to query conversion.

    Uses Claude with structured prompts to generate accurate queries.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
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
            "translating_query_anthropic",
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

        # Build the system prompt
        system_prompt = self._build_system_prompt(mode)

        # Build the user prompt
        user_prompt = self._build_user_prompt(
            natural_language,
            schema_context,
            context,
        )

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )

            result_text = response.content[0].text
            if not result_text:
                raise TranslationError("Empty response from Claude")

            # Extract JSON from response
            result = self._extract_json(result_text)

            # Validate and parse response
            return self._parse_translation_result(result, filtered_sources)

        except json.JSONDecodeError as e:
            logger.error("translation_json_error", error=str(e))
            raise TranslationError(f"Failed to parse Claude response: {e}") from e

        except Exception as e:
            logger.error("translation_failed", error=str(e))
            raise TranslationError(f"Translation failed: {e}") from e

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from Claude's response text."""
        # Try to find JSON in the response
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

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=200,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        return response.content[0].text or "Could you please clarify your query?"

    async def explain_query(self, query: str, query_type: str) -> str:
        """Generate a human-readable explanation of a query."""
        prompt = f"""Explain what this {query_type} query does in simple terms:

```{query_type}
{query}
```

Explain it in 2-3 sentences, focusing on what data it retrieves and any conditions."""

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        return response.content[0].text or "Unable to explain query."

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

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        result = self._extract_json(response.content[0].text or '{"suggestions": []}')
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

    def _build_system_prompt(self, mode: QueryMode) -> str:
        """Build the system prompt based on query mode."""
        base_prompt = """You are an expert database query translator. Your task is to:
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
            base_prompt += "\n\nFocus on SQL databases only."
        elif mode == QueryMode.NOSQL:
            base_prompt += "\n\nFocus on NoSQL databases (MongoDB, DynamoDB) only."
        elif mode == QueryMode.FILES:
            base_prompt += "\n\nFocus on file-based sources (CSV, Excel) only. Use SQL syntax compatible with pandasql."

        return base_prompt

    def _build_user_prompt(
        self,
        natural_language: str,
        schema_context: str,
        context: dict[str, Any] | None,
    ) -> str:
        """Build the user prompt with query and context."""
        prompt = f"""## User Query
{natural_language}

## Available Datasources
{schema_context}
"""

        if context:
            if "previous_queries" in context:
                prompt += f"\n## Previous Queries (for context)\n{context['previous_queries']}"

        return prompt

    def _parse_translation_result(
        self,
        result: dict[str, Any],
        available_datasources: list[Datasource],
    ) -> TranslationResult:
        """Parse and validate Claude response into TranslationResult."""
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
