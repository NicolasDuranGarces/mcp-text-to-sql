"""Domain ports package - Abstract interfaces for infrastructure adapters."""

from src.domain.ports.datasource_port import DatasourcePort
from src.domain.ports.translator_port import TranslatorPort
from src.domain.ports.schema_port import SchemaPort

__all__ = ["DatasourcePort", "TranslatorPort", "SchemaPort"]
