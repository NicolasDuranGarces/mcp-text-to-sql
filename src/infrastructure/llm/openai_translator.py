"""
OpenAI-based natural language to query translator.

Uses GPT-4/o1 to translate natural language into executable database queries.
"""

import json
from typing import Any

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.domain.entities.datasource import Datasource
from src.infrastructure.llm.base_translator import BaseTranslator, TranslationError

logger = structlog.get_logger(__name__)


class OpenAITranslator(BaseTranslator):
    """
    OpenAI-based translator for natural language to query conversion.

    Uses GPT-4/o1 with structured prompts to generate accurate queries.
    Supports o1/o1-mini models with appropriate parameter handling.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> None:
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self._client = AsyncOpenAI(api_key=api_key)

    def _is_o1_model(self) -> bool:
        """Check if current model is an o1 series model."""
        return self._model.startswith("o1") or "o1" in self._model.lower()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Call OpenAI API and return the response text.

        Handles o1 models differently (no temperature, no response_format).
        """
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

        return response.choices[0].message.content or ""

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
                {"role": "system", "content": "Generate clarification questions for database queries."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
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
                {"role": "system", "content": "Explain database queries in simple terms."},
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

Return as a JSON object with a "suggestions" array of strings."""

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "Generate practical example questions for database queries."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content or '{"suggestions": []}')
        return result.get("suggestions", result.get("questions", []))[:count]
