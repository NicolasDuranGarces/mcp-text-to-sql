"""
Application settings using Pydantic Settings.

Loads configuration from environment variables with validation and defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.domain.entities.query import QueryMode


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All sensitive values use SecretStr to prevent accidental exposure in logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Server Configuration
    # -------------------------------------------------------------------------
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # -------------------------------------------------------------------------
    # LLM Provider Selection
    # -------------------------------------------------------------------------
    llm_provider: Literal["openai", "anthropic", "gemini", "auto"] = Field(
        default="auto",
        description="LLM provider to use (openai, anthropic, gemini, auto). Auto will use the first available.",
    )

    # -------------------------------------------------------------------------
    # OpenAI Configuration
    # -------------------------------------------------------------------------
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key for query translation",
    )
    openai_model: str = Field(
        default="o1",
        description="OpenAI model to use (o1, o1-mini, gpt-4o, etc.)",
    )

    # -------------------------------------------------------------------------
    # Anthropic Configuration
    # -------------------------------------------------------------------------
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key for query translation",
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Anthropic model to use (claude-sonnet-4-20250514, claude-opus-4-20250514)",
    )

    # -------------------------------------------------------------------------
    # Google Gemini Configuration
    # -------------------------------------------------------------------------
    gemini_api_key: SecretStr | None = Field(
        default=None,
        description="Google Gemini API key for query translation",
    )
    gemini_model: str = Field(
        default="gemini-2.0-flash",
        description="Gemini model to use",
    )

    # -------------------------------------------------------------------------
    # Common LLM Settings
    # -------------------------------------------------------------------------
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM responses (0 = deterministic)",
    )
    llm_max_tokens: int = Field(
        default=2000,
        ge=100,
        le=8000,
        description="Maximum tokens for LLM response",
    )

    # -------------------------------------------------------------------------
    # Query Settings
    # -------------------------------------------------------------------------
    default_query_mode: QueryMode = Field(
        default=QueryMode.MIXED,
        description="Default query mode (sql, nosql, files, mixed)",
    )
    max_results: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Maximum rows to return from queries",
    )
    query_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Query execution timeout in seconds",
    )
    read_only_mode: bool = Field(
        default=True,
        description="Only allow SELECT/read operations",
    )

    # -------------------------------------------------------------------------
    # Logging Configuration
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "console"] = Field(
        default="json",
        description="Log output format",
    )

    # -------------------------------------------------------------------------
    # Cache Configuration
    # -------------------------------------------------------------------------
    schema_cache_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="TTL for cached schema information",
    )
    redis_url: str | None = Field(
        default=None,
        description="Redis URL for caching (optional)",
    )

    # -------------------------------------------------------------------------
    # File Paths
    # -------------------------------------------------------------------------
    config_file_path: str = Field(
        default="/app/config/datasources.json",
        description="Path to datasources configuration file",
    )
    data_directory: str = Field(
        default="/app/data",
        description="Base directory for file datasources",
    )

    @model_validator(mode="after")
    def validate_and_resolve_provider(self) -> "Settings":
        """
        Validate that at least one API key is configured.
        If provider is 'auto', select the first available provider.
        """
        available_providers: list[str] = []
        
        if self.openai_api_key:
            available_providers.append("openai")
        if self.anthropic_api_key:
            available_providers.append("anthropic")
        if self.gemini_api_key:
            available_providers.append("gemini")
        
        if not available_providers:
            raise ValueError(
                "At least one LLM API key is required. "
                "Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY."
            )
        
        # Auto-select provider if set to 'auto'
        if self.llm_provider == "auto":
            # Priority: openai > anthropic > gemini
            object.__setattr__(self, "llm_provider", available_providers[0])
        
        # Validate selected provider has API key
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER is 'anthropic'")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER is 'gemini'")
        
        return self
    
    def get_active_model(self) -> str:
        """Get the model name for the active provider."""
        if self.llm_provider == "openai":
            return self.openai_model
        elif self.llm_provider == "anthropic":
            return self.anthropic_model
        elif self.llm_provider == "gemini":
            return self.gemini_model
        return "unknown"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
