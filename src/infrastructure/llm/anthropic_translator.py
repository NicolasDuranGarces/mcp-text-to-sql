"""
Anthropic Claude-based natural language to query translator.

Uses Claude to translate natural language into executable database queries.
"""

import json
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.domain.entities.datasource import Datasource
from src.infrastructure.llm.base_translator import BaseTranslator

logger = structlog.get_logger(__name__)


class AnthropicTranslator(BaseTranslator):
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
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self._client = AsyncAnthropic(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Call Anthropic Claude API and return the response text."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )

        return response.content[0].text or ""

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
