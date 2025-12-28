"""
MCP Text-to-SQL Server - FastAPI Application.

Main entry point for the MCP server providing natural language
to query translation capabilities.
"""

import sys
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.infrastructure.config.settings import get_settings, Settings
from src.infrastructure.llm.openai_translator import OpenAITranslator
from src.infrastructure.llm.anthropic_translator import AnthropicTranslator
from src.infrastructure.llm.gemini_translator import GeminiTranslator
from src.domain.ports.translator_port import TranslatorPort
from src.application.services.datasource_service import DatasourceService
from src.application.services.query_service import QueryService

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
        if get_settings().log_format == "json"
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Global service instances
_datasource_service: DatasourceService | None = None
_query_service: QueryService | None = None
_settings: Settings | None = None


def get_datasource_service() -> DatasourceService:
    """Get datasource service instance."""
    if _datasource_service is None:
        raise RuntimeError("Services not initialized")
    return _datasource_service


def get_query_service() -> QueryService:
    """Get query service instance."""
    if _query_service is None:
        raise RuntimeError("Services not initialized")
    return _query_service


def create_translator(settings: Settings) -> TranslatorPort:
    """
    Factory function to create the appropriate translator based on settings.
    
    Supports: openai, anthropic, gemini
    """
    provider = settings.llm_provider
    
    logger.info("creating_translator", provider=provider)
    
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        return OpenAITranslator(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")
        return AnthropicTranslator(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.anthropic_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    
    elif provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for Gemini provider")
        return GeminiTranslator(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use: openai, anthropic, gemini")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global _datasource_service, _query_service, _settings

    logger.info("starting_mcp_server")

    # Load settings
    _settings = get_settings()

    # Initialize services
    _datasource_service = DatasourceService(
        config_path=_settings.config_file_path,
    )

    # Create translator based on provider
    translator = create_translator(_settings)

    _query_service = QueryService(
        datasource_service=_datasource_service,
        translator=translator,
        settings=_settings,
    )

    logger.info(
        "mcp_server_started",
        host=_settings.host,
        port=_settings.port,
        mode=_settings.default_query_mode.value,
        llm_provider=_settings.llm_provider,
    )

    yield

    # Cleanup on shutdown
    logger.info("stopping_mcp_server")


# Create FastAPI application
app = FastAPI(
    title="MCP Text-to-SQL Server",
    description="Translate natural language queries to executable database queries",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled errors."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if get_settings().debug else "An error occurred",
        },
    )


# Health check endpoints
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready_check() -> dict[str, Any]:
    """Readiness check with service status."""
    service = get_datasource_service()
    return {
        "status": "ready",
        "datasources": len(service.list_datasources()),
        "mode": service.get_query_mode().value,
    }


# Import and include MCP tools router
from src.api.tools import router as tools_router
app.include_router(tools_router, prefix="/mcp", tags=["MCP Tools"])


def main() -> None:
    """Main entry point for running the server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
