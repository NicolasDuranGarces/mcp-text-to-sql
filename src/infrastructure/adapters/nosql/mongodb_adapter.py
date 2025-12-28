"""
MongoDB adapter using PyMongo.

Provides MongoDB-specific implementation of the DatasourcePort.
"""

import asyncio
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import structlog
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.domain.entities.datasource import Datasource
from src.domain.entities.result import (
    QueryResult,
    ResultFormat,
    ResultMetadata,
    ColumnInfo,
)
from src.domain.ports.datasource_port import DatasourcePort

logger = structlog.get_logger(__name__)


class MongoDBAdapter(DatasourcePort):
    """
    MongoDB adapter using PyMongo.

    Supports executing aggregation pipelines and find queries.
    Connection string format: mongodb://user:password@host:port/database
    """

    def __init__(self, datasource: Datasource) -> None:
        super().__init__(datasource)
        self._client: MongoClient | None = None
        self._database_name: str = ""

    def _get_connection_url(self) -> str:
        """Get MongoDB connection URL."""
        if self._datasource.connection_config is None:
            raise ValueError("Connection config is required for MongoDB")
        return self._datasource.connection_config.connection_string

    def _parse_database_name(self, url: str) -> str:
        """Extract database name from connection URL."""
        parsed = urlparse(url)
        db_name = parsed.path.lstrip("/")
        if not db_name:
            if self._datasource.connection_config and self._datasource.connection_config.database:
                return self._datasource.connection_config.database
            raise ValueError("Database name must be specified in URL or connection config")
        return db_name

    async def connect(self) -> bool:
        """Connect to MongoDB."""
        try:
            url = self._get_connection_url()
            self._database_name = self._parse_database_name(url)

            safe_url = self._mask_credentials(url)
            logger.info(
                "connecting_to_mongodb",
                datasource_id=self._datasource.id,
                url=safe_url,
                database=self._database_name,
            )

            timeout = self._datasource.connection_config.timeout_seconds * 1000 if self._datasource.connection_config else 30000

            self._client = MongoClient(
                url,
                serverSelectionTimeoutMS=timeout,
                connectTimeoutMS=timeout,
            )

            # Test connection
            await self.validate_connection()

            self._connected = True
            logger.info("mongodb_connected", datasource_id=self._datasource.id)
            return True

        except Exception as e:
            logger.error(
                "mongodb_connection_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise ConnectionError(f"Failed to connect to MongoDB: {e}") from e

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False
        logger.info("mongodb_disconnected", datasource_id=self._datasource.id)

    async def validate_connection(self) -> bool:
        """Validate MongoDB connection."""
        if not self._client:
            return False

        try:
            # Ping the server
            self._client.admin.command("ping")
            return True
        except PyMongoError as e:
            logger.warning(
                "mongodb_validation_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            return False

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        max_results: int = 1000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """
        Execute a MongoDB query.

        The query should be a JSON string representing either:
        - An aggregation pipeline: {"collection": "name", "pipeline": [...]}
        - A find query: {"collection": "name", "filter": {...}, "projection": {...}}
        """
        import json

        if not self._client:
            raise ConnectionError("Not connected to MongoDB")

        start_time = datetime.utcnow()
        logger.info(
            "executing_mongodb_query",
            datasource_id=self._datasource.id,
            query_preview=query[:100] + "..." if len(query) > 100 else query,
        )

        try:
            # Parse query
            query_doc = json.loads(query)
            collection_name = query_doc.get("collection")

            if not collection_name:
                raise ValueError("Query must specify a 'collection' field")

            result = await asyncio.wait_for(
                self._execute_query(query_doc, max_results),
                timeout=timeout_seconds,
            )

            execution_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )

            logger.info(
                "mongodb_query_executed",
                datasource_id=self._datasource.id,
                row_count=len(result["data"]),
                execution_time_ms=execution_time_ms,
            )

            return QueryResult(
                query_id="",
                format=ResultFormat.DOCUMENTS,
                data=result["data"],
                metadata=ResultMetadata(
                    total_rows=result["total_rows"],
                    returned_rows=len(result["data"]),
                    was_truncated=result["was_truncated"],
                    columns=result["columns"],
                    execution_time_ms=execution_time_ms,
                    datasource_id=self._datasource.id,
                    datasource_name=self._datasource.name,
                ),
            )

        except asyncio.TimeoutError:
            logger.error(
                "mongodb_query_timeout",
                datasource_id=self._datasource.id,
                timeout_seconds=timeout_seconds,
            )
            raise TimeoutError(f"Query timed out after {timeout_seconds} seconds")

        except (json.JSONDecodeError, PyMongoError) as e:
            logger.error(
                "mongodb_query_failed",
                datasource_id=self._datasource.id,
                error=str(e),
            )
            raise ValueError(f"Query execution failed: {e}") from e

    async def _execute_query(
        self,
        query_doc: dict[str, Any],
        max_results: int,
    ) -> dict[str, Any]:
        """Execute MongoDB query in thread pool."""

        def _run_query() -> dict[str, Any]:
            if self._client is None:
                raise ConnectionError("Client not initialized")

            db = self._client[self._database_name]
            collection = db[query_doc["collection"]]

            # Determine query type and execute
            if "pipeline" in query_doc:
                # Aggregation pipeline
                cursor = collection.aggregate(query_doc["pipeline"])
            else:
                # Find query
                filter_doc = query_doc.get("filter", {})
                projection = query_doc.get("projection")
                sort = query_doc.get("sort")

                cursor = collection.find(filter_doc, projection)
                if sort:
                    cursor = cursor.sort(list(sort.items()))

            # Collect results
            rows = []
            total_rows = 0
            was_truncated = False

            for doc in cursor:
                total_rows += 1
                if len(rows) < max_results:
                    # Convert ObjectId to string
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                    rows.append(doc)
                else:
                    was_truncated = True

            # Infer columns from first document
            columns = []
            if rows:
                for key, value in rows[0].items():
                    columns.append(ColumnInfo(
                        name=key,
                        data_type=type(value).__name__,
                        nullable=True,
                    ))

            return {
                "data": rows,
                "total_rows": total_rows,
                "was_truncated": was_truncated,
                "columns": columns,
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_query)

    async def get_schema(self) -> dict[str, list[dict[str, Any]]]:
        """Get MongoDB schema by sampling documents."""
        if not self._client:
            raise ConnectionError("Not connected to MongoDB")

        def _get_schema() -> dict[str, list[dict[str, Any]]]:
            if self._client is None:
                return {}

            db = self._client[self._database_name]
            schema: dict[str, list[dict[str, Any]]] = {}

            for collection_name in db.list_collection_names():
                # Sample documents to infer schema
                sample = list(db[collection_name].find().limit(100))

                # Collect all unique fields and their types
                fields: dict[str, set[str]] = {}
                for doc in sample:
                    for key, value in doc.items():
                        if key not in fields:
                            fields[key] = set()
                        fields[key].add(type(value).__name__)

                # Build column info
                columns = []
                for field_name, types in fields.items():
                    columns.append({
                        "name": field_name,
                        "type": ", ".join(sorted(types)),
                        "nullable": True,
                    })

                schema[collection_name] = columns

            return schema

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_schema)

    async def get_tables(self) -> list[str]:
        """Get list of collection names."""
        if not self._client:
            raise ConnectionError("Not connected to MongoDB")

        def _get_collections() -> list[str]:
            if self._client is None:
                return []
            db = self._client[self._database_name]
            return db.list_collection_names()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_collections)

    @staticmethod
    def _mask_credentials(url: str) -> str:
        """Mask password in connection URL for logging."""
        import re
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)
