"""
Datasource Service for managing data source connections.

Handles CRUD operations for datasources, connection validation,
and adapter factory pattern.
"""

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

import structlog

from src.domain.entities.datasource import (
    Datasource,
    DatasourceType,
    DatasourceCategory,
    ConnectionConfig,
    FileConfig,
)
from src.domain.entities.query import QueryMode
from src.domain.ports.datasource_port import DatasourcePort

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from src.infrastructure.adapters.factory import AdapterFactory

logger = structlog.get_logger(__name__)


class DatasourceService:
    """
    Service for managing datasources.

    Provides CRUD operations, connection validation, and adapter creation.
    """

    def __init__(
        self,
        config_path: str | None = None,
        adapter_factory: "AdapterFactory | None" = None,
    ) -> None:
        """Initialize service with optional config path and adapter factory.
        
        Args:
            config_path: Path to JSON config file for persistence
            adapter_factory: Factory for creating adapters (injected for DIP)
        """
        self._datasources: dict[str, Datasource] = {}
        self._adapters: dict[str, DatasourcePort] = {}
        self._current_mode: QueryMode = QueryMode.MIXED
        self._config_path = Path(config_path) if config_path else None
        
        # Lazy load factory if not provided (for backward compatibility)
        self._adapter_factory = adapter_factory

        # Load from config file if provided
        if self._config_path and self._config_path.exists():
            self._load_from_config()

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def add_datasource(
        self,
        id: str,
        name: str,
        ds_type: DatasourceType | str,
        connection_string: str | None = None,
        file_path: str | None = None,
        enabled: bool = True,
        description: str = "",
        **kwargs: Any,
    ) -> Datasource:
        """Add a new datasource configuration."""
        if isinstance(ds_type, str):
            ds_type = DatasourceType(ds_type.lower())

        logger.info(
            "adding_datasource",
            id=id,
            name=name,
            type=ds_type.value,
        )

        # Build configuration based on type
        connection_config = None
        file_config = None

        if ds_type.category == DatasourceCategory.FILE:
            if not file_path:
                raise ValueError(f"File path is required for {ds_type.value} datasource")
            file_config = FileConfig(
                path=file_path,
                encoding=kwargs.get("encoding", "utf-8"),
                delimiter=kwargs.get("delimiter", ","),
                sheet_name=kwargs.get("sheet_name"),
                has_header=kwargs.get("has_header", True),
            )
        else:
            if not connection_string:
                raise ValueError(f"Connection string is required for {ds_type.value} datasource")
            connection_config = ConnectionConfig(
                connection_string=connection_string,
                database=kwargs.get("database"),
                schema=kwargs.get("schema"),
                pool_size=kwargs.get("pool_size", 5),
                timeout_seconds=kwargs.get("timeout_seconds", 30),
            )

        datasource = Datasource(
            id=id,
            name=name,
            type=ds_type,
            enabled=enabled,
            description=description,
            connection_config=connection_config,
            file_config=file_config,
        )

        self._datasources[id] = datasource
        self._save_config()

        logger.info("datasource_added", id=id, type=ds_type.value)
        return datasource

    def remove_datasource(self, id: str) -> bool:
        """Remove a datasource by ID."""
        if id not in self._datasources:
            logger.warning("datasource_not_found", id=id)
            return False

        # Disconnect if connected
        if id in self._adapters:
            adapter = self._adapters.pop(id)
            # Note: Should call disconnect asynchronously
            logger.info("adapter_removed", id=id)

        del self._datasources[id]
        self._save_config()

        logger.info("datasource_removed", id=id)
        return True

    def get_datasource(self, id: str) -> Datasource | None:
        """Get a datasource by ID."""
        return self._datasources.get(id)

    def list_datasources(
        self,
        enabled_only: bool = False,
        category: DatasourceCategory | None = None,
    ) -> list[Datasource]:
        """List all datasources with optional filtering."""
        result = list(self._datasources.values())

        if enabled_only:
            result = [ds for ds in result if ds.enabled]

        if category:
            result = [ds for ds in result if ds.category == category]

        return result

    def toggle_datasource(self, id: str, enabled: bool | None = None) -> Datasource | None:
        """Enable or disable a datasource."""
        datasource = self._datasources.get(id)
        if not datasource:
            logger.warning("datasource_not_found", id=id)
            return None

        # Toggle if enabled is None, else set to provided value
        datasource.enabled = not datasource.enabled if enabled is None else enabled
        self._save_config()

        logger.info(
            "datasource_toggled",
            id=id,
            enabled=datasource.enabled,
        )
        return datasource

    # -------------------------------------------------------------------------
    # Mode Management
    # -------------------------------------------------------------------------

    def set_query_mode(self, mode: QueryMode | str) -> QueryMode:
        """Set the current query mode."""
        if isinstance(mode, str):
            mode = QueryMode(mode.lower())

        self._current_mode = mode
        logger.info("query_mode_set", mode=mode.value)
        return mode

    def get_query_mode(self) -> QueryMode:
        """Get the current query mode."""
        return self._current_mode

    def get_datasources_for_mode(self, mode: QueryMode | None = None) -> list[Datasource]:
        """Get datasources available for the current or specified mode."""
        mode = mode or self._current_mode

        if mode == QueryMode.MIXED:
            return [ds for ds in self._datasources.values() if ds.enabled]

        category_map = {
            QueryMode.SQL: DatasourceCategory.SQL,
            QueryMode.NOSQL: DatasourceCategory.NOSQL,
            QueryMode.FILES: DatasourceCategory.FILE,
        }

        target_category = category_map.get(mode)
        return [
            ds for ds in self._datasources.values()
            if ds.enabled and ds.category == target_category
        ]

    # -------------------------------------------------------------------------
    # Adapter Management
    # -------------------------------------------------------------------------

    def get_adapter(self, datasource_id: str) -> DatasourcePort | None:
        """Get or create an adapter for a datasource."""
        if datasource_id in self._adapters:
            return self._adapters[datasource_id]

        datasource = self._datasources.get(datasource_id)
        if not datasource:
            return None

        # Lazy init factory if not provided (Composition Root fallback)
        if not self._adapter_factory:
            from src.infrastructure.adapters.factory import create_default_factory
            self._adapter_factory = create_default_factory()

        # Use factory to create adapter (DIP compliant)
        adapter = self._adapter_factory.create(datasource)
        self._adapters[datasource_id] = adapter
        return adapter

    # _create_adapter removed - logic moved to AdapterFactory

    async def validate_connection(self, datasource_id: str) -> bool:
        """Validate connection to a datasource."""
        adapter = self.get_adapter(datasource_id)
        if not adapter:
            return False

        try:
            await adapter.connect()
            result = await adapter.validate_connection()
            await adapter.disconnect()
            return result
        except Exception as e:
            logger.error(
                "connection_validation_failed",
                datasource_id=datasource_id,
                error=str(e),
            )
            return False

    # -------------------------------------------------------------------------
    # Config Persistence
    # -------------------------------------------------------------------------

    def _load_from_config(self) -> None:
        """Load datasources from config file."""
        if not self._config_path or not self._config_path.exists():
            return

        try:
            with open(self._config_path) as f:
                config = json.load(f)

            for ds_id, ds_config in config.get("datasources", {}).items():
                self.add_datasource(
                    id=ds_id,
                    name=ds_config.get("name", ds_id),
                    ds_type=ds_config["type"],
                    connection_string=ds_config.get("connection_string"),
                    file_path=ds_config.get("path"),
                    enabled=ds_config.get("enabled", True),
                    description=ds_config.get("description", ""),
                    **ds_config.get("options", {}),
                )

            if "query_mode" in config:
                self.set_query_mode(config["query_mode"])

            logger.info(
                "config_loaded",
                path=str(self._config_path),
                datasource_count=len(self._datasources),
            )

        except Exception as e:
            logger.error("config_load_failed", error=str(e))

    def _save_config(self) -> None:
        """Save datasources to config file."""
        if not self._config_path:
            return

        try:
            config: dict[str, Any] = {
                "datasources": {},
                "query_mode": self._current_mode.value,
            }

            for ds_id, ds in self._datasources.items():
                ds_config: dict[str, Any] = {
                    "name": ds.name,
                    "type": ds.type.value,
                    "enabled": ds.enabled,
                    "description": ds.description,
                }

                if ds.connection_config:
                    # Do NOT save connection string to file for security
                    ds_config["connection_string_env"] = f"{ds_id.upper()}_CONNECTION_STRING"

                if ds.file_config:
                    ds_config["path"] = ds.file_config.path

                config["datasources"][ds_id] = ds_config

            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w") as f:
                json.dump(config, f, indent=2)

            logger.debug("config_saved", path=str(self._config_path))

        except Exception as e:
            logger.error("config_save_failed", error=str(e))

    def to_dict(self) -> dict[str, Any]:
        """Export service state as dictionary."""
        return {
            "mode": self._current_mode.value,
            "datasources": [ds.to_dict() for ds in self._datasources.values()],
            "active_adapters": list(self._adapters.keys()),
        }
