"""
MCP Tools Router.

Defines all MCP tools as FastAPI endpoints.
"""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.main import get_datasource_service, get_query_service
from src.infrastructure.config.settings import get_settings
from src.domain.entities.datasource import DatasourceType
from src.domain.entities.query import QueryMode

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class ConfigureDatasourceRequest(BaseModel):
    """Request model for configure_datasource tool."""

    id: str = Field(..., description="Unique identifier for the datasource")
    name: str = Field(..., description="Human-readable name")
    type: str = Field(..., description="Datasource type (postgresql, mysql, mongodb, csv, etc.)")
    # Security: prefer connection_string_env over connection_string
    connection_string_env: str | None = Field(
        None, 
        description="Name of environment variable containing connection string (RECOMMENDED for security)"
    )
    connection_string: str | None = Field(
        None, 
        description="Direct connection string (NOT recommended - use connection_string_env instead)"
    )
    file_path: str | None = Field(None, description="File path for CSV/Excel sources")
    enabled: bool = Field(True, description="Whether the datasource is enabled")
    description: str = Field("", description="Optional description")


class ToggleDatasourceRequest(BaseModel):
    """Request model for toggle_datasource tool."""

    id: str = Field(..., description="Datasource ID to toggle")
    enabled: bool | None = Field(None, description="Set enabled state (None to toggle)")


class SetQueryModeRequest(BaseModel):
    """Request model for set_query_mode tool."""

    mode: str = Field(..., description="Query mode: sql, nosql, files, or mixed")


class QueryRequest(BaseModel):
    """Request model for query tool."""

    query: str = Field(..., description="Natural language query")
    mode: str | None = Field(None, description="Optional mode override")
    max_results: int | None = Field(None, description="Maximum results to return")


class PreviewQueryRequest(BaseModel):
    """Request model for preview_query tool."""

    query: str = Field(..., description="Natural language query to preview")
    mode: str | None = Field(None, description="Optional mode override")


class ExportResultsRequest(BaseModel):
    """Request model for export_results tool."""

    format: str = Field("csv", description="Export format: csv or json")


class ToolResponse(BaseModel):
    """Standard tool response model."""

    success: bool
    message: str
    data: dict[str, Any] | None = None


# =============================================================================
# MCP Tools
# =============================================================================


@router.post("/configure_datasource", response_model=ToolResponse)
async def configure_datasource(request: ConfigureDatasourceRequest) -> ToolResponse:
    """
    Add or update a datasource configuration.

    This tool allows you to configure connections to databases or file sources.
    
    For security, use connection_string_env to reference an environment variable
    instead of passing the connection string directly.
    """
    try:
        service = get_datasource_service()

        # Resolve connection string from environment variable if provided
        connection_string = request.connection_string
        if request.connection_string_env:
            connection_string = os.environ.get(request.connection_string_env)
            if not connection_string:
                raise ValueError(
                    f"Environment variable '{request.connection_string_env}' not found. "
                    "Please set it in your .env file or environment."
                )

        # Check if updating existing
        existing = service.get_datasource(request.id)
        if existing:
            service.remove_datasource(request.id)

        datasource = service.add_datasource(
            id=request.id,
            name=request.name,
            ds_type=request.type,
            connection_string=connection_string,
            file_path=request.file_path,
            enabled=request.enabled,
            description=request.description,
        )

        # Don't expose connection string in response
        response_data = datasource.to_dict()
        if "connection_string" in response_data:
            response_data["connection_string"] = "***hidden***"

        return ToolResponse(
            success=True,
            message=f"Datasource '{request.name}' configured successfully",
            data=response_data,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/remove_datasource/{datasource_id}", response_model=ToolResponse)
async def remove_datasource(datasource_id: str) -> ToolResponse:
    """
    Remove a datasource configuration.
    """
    service = get_datasource_service()

    if service.remove_datasource(datasource_id):
        return ToolResponse(
            success=True,
            message=f"Datasource '{datasource_id}' removed successfully",
        )
    else:
        raise HTTPException(status_code=404, detail=f"Datasource '{datasource_id}' not found")


@router.get("/list_datasources", response_model=ToolResponse)
async def list_datasources(enabled_only: bool = False) -> ToolResponse:
    """
    List all configured datasources.
    """
    service = get_datasource_service()
    datasources = service.list_datasources(enabled_only=enabled_only)

    return ToolResponse(
        success=True,
        message=f"Found {len(datasources)} datasource(s)",
        data={
            "datasources": [ds.to_dict() for ds in datasources],
            "current_mode": service.get_query_mode().value,
        },
    )


@router.post("/toggle_datasource", response_model=ToolResponse)
async def toggle_datasource(request: ToggleDatasourceRequest) -> ToolResponse:
    """
    Enable or disable a datasource.
    """
    service = get_datasource_service()
    datasource = service.toggle_datasource(request.id, request.enabled)

    if datasource:
        return ToolResponse(
            success=True,
            message=f"Datasource '{request.id}' is now {'enabled' if datasource.enabled else 'disabled'}",
            data=datasource.to_dict(),
        )
    else:
        raise HTTPException(status_code=404, detail=f"Datasource '{request.id}' not found")


@router.post("/set_query_mode", response_model=ToolResponse)
async def set_query_mode(request: SetQueryModeRequest) -> ToolResponse:
    """
    Set the query mode (sql, nosql, files, or mixed).
    """
    try:
        service = get_datasource_service()
        mode = service.set_query_mode(request.mode)

        available = service.get_datasources_for_mode(mode)

        return ToolResponse(
            success=True,
            message=f"Query mode set to '{mode.value}'",
            data={
                "mode": mode.value,
                "available_datasources": len(available),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/get_schema/{datasource_id}", response_model=ToolResponse)
async def get_schema(datasource_id: str) -> ToolResponse:
    """
    Get the schema of a datasource.
    """
    service = get_datasource_service()
    adapter = service.get_adapter(datasource_id)

    if not adapter:
        raise HTTPException(status_code=404, detail=f"Datasource '{datasource_id}' not found")

    try:
        async with adapter:
            schema = await adapter.get_schema()

        datasource = service.get_datasource(datasource_id)
        if datasource:
            datasource.update_schema_cache(schema)

        return ToolResponse(
            success=True,
            message=f"Schema retrieved for '{datasource_id}'",
            data={
                "datasource_id": datasource_id,
                "schema": schema,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=ToolResponse)
async def query(request: QueryRequest) -> ToolResponse:
    """
    Execute a natural language query.

    This is the main tool for querying data using natural language.
    The query will be translated to the appropriate format and executed
    against the selected datasource.
    """
    try:
        query_service = get_query_service()
        settings = get_settings()

        mode = QueryMode(request.mode) if request.mode else None

        result = await query_service.execute_query(
            natural_language=request.query,
            mode=mode,
            max_results=request.max_results,
        )

        # Add result data with provider info
        result_data = result.to_dict()
        result_data["llm_provider"] = settings.llm_provider
        result_data["llm_model"] = settings.get_active_model()

        # Use natural response as the main message for non-technical users
        user_message = result.natural_response or f"Encontré {result.row_count} resultado(s)."

        return ToolResponse(
            success=True,
            message=user_message,
            data=result_data,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview_query", response_model=ToolResponse)
async def preview_query(request: PreviewQueryRequest) -> ToolResponse:
    """
    Preview the generated query without executing it.

    Use this to see what query would be generated before running it.
    """
    try:
        query_service = get_query_service()
        settings = get_settings()

        mode = QueryMode(request.mode) if request.mode else None

        result = await query_service.preview_query(
            natural_language=request.query,
            mode=mode,
        )

        # Add provider info to preview response
        preview_data = result.get_preview_response()
        preview_data["llm_provider"] = settings.llm_provider
        preview_data["llm_model"] = settings.get_active_model()

        return ToolResponse(
            success=True,
            message=f"Query preview generated with {settings.llm_provider.upper()} ({settings.get_active_model()})",
            data=preview_data,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/export_results", response_model=ToolResponse)
async def export_results(request: ExportResultsRequest) -> ToolResponse:
    """
    Export the last query results to a file format.
    """
    query_service = get_query_service()
    result = query_service.get_last_result()

    if not result:
        raise HTTPException(status_code=404, detail="No query results to export")

    if request.format.lower() == "csv":
        export_data = result.to_csv_string()
        content_type = "text/csv"
    elif request.format.lower() == "json":
        export_data = result.to_json_string()
        content_type = "application/json"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

    return ToolResponse(
        success=True,
        message=f"Results exported as {request.format.upper()}",
        data={
            "format": request.format,
            "content_type": content_type,
            "content": export_data,
            "row_count": result.row_count,
        },
    )


@router.get("/query_history", response_model=ToolResponse)
async def query_history(limit: int = 10) -> ToolResponse:
    """
    Get recent query history.
    """
    query_service = get_query_service()
    history = query_service.get_query_history(limit=limit)

    return ToolResponse(
        success=True,
        message=f"Retrieved {len(history)} query history entries",
        data={"history": history},
    )
