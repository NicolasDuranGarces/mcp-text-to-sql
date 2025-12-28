"""
OpenAI-based natural language to query translator.

Uses GPT-4 to translate natural language into executable database queries.
"""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.domain.entities.datasource import Datasource, DatasourceCategory
from src.domain.entities.query import QueryMode, QueryType, TranslationResult
from src.domain.ports.translator_port import TranslatorPort

logger = structlog.get_logger(__name__)


class TranslationError(Exception):
    """Raised when translation fails."""

    pass


class OpenAITranslator(TranslatorPort):
    """
    OpenAI-based translator for natural language to query conversion.

    Uses GPT-4 with structured prompts to generate accurate queries.
    Supports o1/o1-mini models with appropriate parameter handling.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _is_o1_model(self) -> bool:
        """Check if current model is an o1 series model."""
        return self._model.startswith("o1") or "o1" in self._model.lower()

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
            "translating_query",
            input=natural_language[:100],
            mode=mode.value,
            datasource_count=len(available_datasources),
            model=self._model,
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
            # Build request parameters based on model type
            if self._is_o1_model():
                # o1 models don't support temperature or response_format
                # and use max_completion_tokens instead of max_tokens
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}\n\nRespond ONLY with the JSON object."},
                    ],
                    max_completion_tokens=self._max_tokens,
                )
            else:
                # Standard GPT-4/GPT-3.5 models
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    response_format={"type": "json_object"},
                )

            result_text = response.choices[0].message.content
            if not result_text:
                raise TranslationError("Empty response from LLM")

            # Extract JSON from response (handles both raw JSON and markdown-wrapped JSON)
            result = self._extract_json(result_text)

            # Validate and parse response
            return self._parse_translation_result(result, filtered_sources)

        except json.JSONDecodeError as e:
            logger.error("translation_json_error", error=str(e))
            raise TranslationError(f"Failed to parse LLM response: {e}") from e

        except Exception as e:
            logger.error("translation_failed", error=str(e))
            raise TranslationError(f"Translation failed: {e}") from e

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from response text, handling markdown code blocks."""
        import re
        
        # Try to parse directly first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Look for JSON in code blocks or raw
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

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful database assistant. Generate clear clarification questions.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        return response.choices[0].message.content or "Could you please clarify your query?"

    async def explain_query(self, query: str, query_type: str) -> str:
        """Generate a human-readable explanation of a query."""
        prompt = f"""Explain what this {query_type} query does in simple terms:

```{query_type}
{query}
```

Explain it in 2-3 sentences, focusing on what data it retrieves and any conditions."""

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a database expert. Explain queries clearly and concisely.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        return response.choices[0].message.content or "Unable to explain query."

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

Return as a JSON array of strings."""

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": "Generate practical example questions for database queries.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content or '{"suggestions": []}')
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
        base_prompt = """You are an expert database query translator and friendly assistant. Your task is to:
1. Understand the user's natural language query
2. Select the most appropriate datasource
3. Generate the correct query for that datasource type
4. Provide a natural, friendly response template for non-technical users

IMPORTANT RULES:
- Generate ONLY SELECT/read queries (no INSERT, UPDATE, DELETE, DROP, etc.)
- For SQL databases, use standard SQL syntax appropriate for the dialect
- For MongoDB, generate a JSON query document with "collection", "filter", and optional "projection"
- For file-based sources (CSV/Excel), generate SQL that can be run with pandasql
- The natural_response_template should be friendly and conversational, like talking to a friend
- Use {count} placeholder for the number of results
- Use {sample} placeholder for showing first few records in a readable format

Always respond with a JSON object containing:
{
    "datasource_id": "id of the selected datasource",
    "query_type": "sql" | "mongodb" | "dynamodb" | "pandas",
    "query": "the generated query string",
    "confidence": 0.0 to 1.0,
    "explanation": "brief technical explanation",
    "warnings": ["any warnings or assumptions made"],
    "natural_response_template": "Friendly response like: 'Encontré {count} clientes en la base de datos. ¿Te gustaría ver la lista completa?' or 'Hay {count} registros. Aquí tienes algunos:\n{sample}'"
}"""

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
        """Parse and validate LLM response into TranslationResult."""
        datasource_id = result.get("datasource_id")
        if not datasource_id:
            raise TranslationError("LLM response missing 'datasource_id'")

        # Verify datasource exists
        matching_ds = next(
            (ds for ds in available_datasources if ds.id == datasource_id),
            None,
        )
        if not matching_ds:
            raise TranslationError(f"LLM selected unknown datasource: {datasource_id}")

        # Parse query type
        query_type_str = result.get("query_type", "sql").lower()
        query_type_map = {
            "sql": QueryType.SQL,
            "mongodb": QueryType.MONGODB,
            "dynamodb": QueryType.DYNAMODB,
            "pandas": QueryType.PANDAS,
        }
        query_type = query_type_map.get(query_type_str, QueryType.SQL)

        # Default natural response if LLM didn't provide one
        natural_template = result.get(
            "natural_response_template",
            "Encontré {count} registro(s). ¿Te gustaría ver los detalles?"
        )

        return TranslationResult(
            query_string=result.get("query", ""),
            query_type=query_type,
            target_datasource_id=datasource_id,
            confidence=float(result.get("confidence", 0.8)),
            explanation=result.get("explanation", ""),
            warnings=result.get("warnings", []),
            natural_response_template=natural_template,
        )

    def _format_datasource_list(self, datasources: list[Datasource]) -> str:
        """Format datasource list for prompts."""
        return "\n".join(
            f"- {ds.name} ({ds.type.value}): {ds.description or 'No description'}"
            for ds in datasources
        )
