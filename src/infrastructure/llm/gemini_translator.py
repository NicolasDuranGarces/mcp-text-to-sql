"""
Google Gemini-based natural language to query translator.

Uses Gemini to translate natural language into executable database queries.
"""

import json
from typing import Any

import structlog
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from src.domain.entities.datasource import Datasource
from src.infrastructure.llm.base_translator import BaseTranslator

logger = structlog.get_logger(__name__)


class GeminiTranslator(BaseTranslator):
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
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Call Gemini API and return the response text."""
        # Gemini combines system and user prompts
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        response = await self._client.generate_content_async(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
            ),
        )

        return response.text or ""

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

        response = await self._client.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=200,
            ),
        )

        return response.text or "Could you please clarify your query?"

    async def explain_query(self, query: str, query_type: str) -> str:
        """Generate a human-readable explanation of a query."""
        prompt = f"""Explain what this {query_type} query does in simple terms:

```{query_type}
{query}
```

Explain it in 2-3 sentences, focusing on what data it retrieves and any conditions."""

        response = await self._client.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=300,
            ),
        )

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

        response = await self._client.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=500,
            ),
        )

        result = self._extract_json(response.text or '{"suggestions": []}')
        return result.get("suggestions", result.get("questions", []))[:count]
