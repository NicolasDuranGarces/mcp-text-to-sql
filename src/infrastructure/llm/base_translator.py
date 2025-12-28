"""
Base Translator for natural language to query conversion.

Provides common functionality shared by all LLM translators (OpenAI, Anthropic, Gemini).
Follows DRY principle - all shared logic is here, providers only implement their specifics.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import structlog

from src.domain.entities.datasource import Datasource, DatasourceCategory
from src.domain.entities.query import QueryMode, QueryType, TranslationResult
from src.domain.ports.translator_port import TranslatorPort

logger = structlog.get_logger(__name__)


class TranslationError(Exception):
    """Raised when translation fails."""

    pass


class BaseTranslator(TranslatorPort, ABC):
    """
    Abstract base class for LLM translators.

    Implements shared logic for:
    - Datasource filtering by mode
    - Schema context building
    - Prompt construction
    - Response parsing

    Subclasses only need to implement:
    - _call_llm(): The actual API call to the LLM provider
    - clarify(), explain_query(), suggest_queries(): Provider-specific convenience methods
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        """Get the current model name."""
        return self._model

    # =========================================================================
    # Abstract Methods - Must be implemented by providers
    # =========================================================================

    @abstractmethod
    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Call the LLM provider and return the response text.

        Args:
            system_prompt: System-level instructions
            user_prompt: User query with context

        Returns:
            Raw response text from the LLM
        """
        pass

    @abstractmethod
    async def clarify(
        self,
        natural_language: str,
        available_datasources: list[Datasource],
        ambiguity_reason: str,
    ) -> str:
        """Generate a clarification question for ambiguous queries."""
        pass

    @abstractmethod
    async def explain_query(self, query: str, query_type: str) -> str:
        """Generate a human-readable explanation of a query."""
        pass

    @abstractmethod
    async def suggest_queries(
        self,
        datasource: Datasource,
        schema: dict[str, Any],
        count: int = 5,
    ) -> list[str]:
        """Generate example natural language queries for a datasource."""
        pass

    # =========================================================================
    # Template Method - Main translation flow
    # =========================================================================

    async def translate(
        self,
        natural_language: str,
        available_datasources: list[Datasource],
        mode: QueryMode,
        context: dict[str, Any] | None = None,
    ) -> TranslationResult:
        """
        Translate natural language to an executable query.

        Template Method pattern: defines the algorithm skeleton,
        subclasses provide the _call_llm() implementation.
        """
        logger.info(
            "translating_query",
            input=natural_language[:100],
            mode=mode.value,
            datasource_count=len(available_datasources),
            model=self._model,
            provider=self.__class__.__name__,
        )

        # Step 1: Filter datasources by mode
        filtered_sources = self._filter_by_mode(available_datasources, mode)

        if not filtered_sources:
            raise TranslationError(
                f"No datasources available for mode '{mode.value}'. "
                "Configure and enable appropriate datasources first."
            )

        # Step 2: Build prompts
        schema_context = self._build_schema_context(filtered_sources)
        system_prompt = self._build_system_prompt(mode)
        user_prompt = self._build_user_prompt(natural_language, schema_context, context)

        try:
            # Step 3: Call LLM (provider-specific)
            result_text = await self._call_llm(system_prompt, user_prompt)

            if not result_text:
                raise TranslationError("Empty response from LLM")

            # Step 4: Parse response
            result = self._extract_json(result_text)
            return self._parse_translation_result(result, filtered_sources)

        except json.JSONDecodeError as e:
            logger.error("translation_json_error", error=str(e))
            raise TranslationError(f"Failed to parse LLM response: {e}") from e

        except TranslationError:
            raise

        except Exception as e:
            logger.error("translation_failed", error=str(e))
            raise TranslationError(f"Translation failed: {e}") from e

    # =========================================================================
    # Shared Helper Methods (DRY - no duplication)
    # =========================================================================

    def _filter_by_mode(
        self,
        datasources: list[Datasource],
        mode: QueryMode,
    ) -> list[Datasource]:
        """Filter datasources based on query mode. O(n) complexity."""
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
        """Build schema context string for the prompt. O(n*m) where m is avg tables."""
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
        base_prompt = """You are an expert database query translator and professional assistant. Your task is to:
1. Understand the user's natural language query
2. Select the most appropriate datasource
3. Generate the correct query for that datasource type
4. Provide a professional, helpful natural language response template

IMPORTANT RULES:
- Generate ONLY SELECT/read queries (no INSERT, UPDATE, DELETE, DROP, etc.)
- For SQL databases, use standard SQL syntax appropriate for the dialect
- For MongoDB, generate a JSON query document with "collection", "filter", and optional "projection"
- For file-based sources (CSV/Excel), generate SQL that can be run with pandasql
- The natural_response_template should be professional, concise, and helpful. 
- Avoid overly casual language like "¡Amigo!"
- Use {count} placeholder for the number of results (or the value of the result if it's a count)
- Use {sample} placeholder for showing first few records in a readable format
- Always offer to show more details or list the items if appropriate in the template (e.g., "Would you like to see the list?")

Always respond with a JSON object containing:
{
    "datasource_id": "id of the selected datasource",
    "query_type": "sql" | "mongodb" | "dynamodb" | "pandas",
    "query": "the generated query string",
    "confidence": 0.0 to 1.0,
    "explanation": "brief technical explanation",
    "warnings": ["any warnings or assumptions made"],
    "natural_response_template": "Professional response like: 'Found {count} products. I can list them if you'd like.'"
}"""

        mode_suffix = {
            QueryMode.SQL: "\n\nFocus on SQL databases only.",
            QueryMode.NOSQL: "\n\nFocus on NoSQL databases (MongoDB, DynamoDB) only.",
            QueryMode.FILES: "\n\nFocus on file-based sources (CSV, Excel) only. Use SQL syntax compatible with pandasql.",
        }

        return base_prompt + mode_suffix.get(mode, "")

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

        if context and "previous_queries" in context:
            prompt += f"\n## Previous Queries (for context)\n{context['previous_queries']}"

        return prompt

    def _extract_json(self, text: str) -> dict[str, Any]:
        """
        Extract JSON from response text, handling markdown code blocks.

        O(n) where n is text length.
        """
        # Try direct parse first (O(n))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Look for JSON in code blocks or raw (O(n))
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())

        raise json.JSONDecodeError("No JSON found in response", text, 0)

    def _parse_translation_result(
        self,
        result: dict[str, Any],
        available_datasources: list[Datasource],
    ) -> TranslationResult:
        """
        Parse and validate LLM response into TranslationResult.

        O(n) where n is number of datasources (for verification).
        """
        datasource_id = result.get("datasource_id")
        if not datasource_id:
            raise TranslationError("LLM response missing 'datasource_id'")

        # O(n) search - could use dict for O(1) if needed
        matching_ds = next(
            (ds for ds in available_datasources if ds.id == datasource_id),
            None,
        )
        if not matching_ds:
            raise TranslationError(f"LLM selected unknown datasource: {datasource_id}")

        # Parse query type - O(1) dict lookup
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
        """Format datasource list for prompts. O(n)."""
        return "\n".join(
            f"- {ds.name} ({ds.type.value}): {ds.description or 'No description'}"
            for ds in datasources
        )
