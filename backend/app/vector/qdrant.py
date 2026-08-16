from __future__ import annotations

import asyncio
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.vector.base import VectorHit, VectorPoint, VectorStore, VectorStoreError


class QdrantVectorStore(VectorStore):
    """Qdrant transport adapter; it contains no tenant authorization decisions."""

    def __init__(
        self,
        url: str | None,
        api_key: str | None,
        collection_name: str,
        timeout_seconds: int,
        upsert_batch_size: int,
        *,
        client: QdrantClient | None = None,
    ) -> None:
        self._client = client or QdrantClient(
            url=url,
            api_key=api_key or None,
            timeout=timeout_seconds,
            check_compatibility=False,
        )
        self._collection_name = collection_name
        self._upsert_batch_size = upsert_batch_size

    @property
    def collection_name(self) -> str:
        return self._collection_name

    async def ensure_collection(self, dimension: int) -> None:
        try:
            await asyncio.to_thread(self._ensure_collection_sync, dimension)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(
                "QDRANT_UNAVAILABLE", "The vector index is unavailable"
            ) from exc

    def _ensure_collection_sync(self, dimension: int) -> None:
        if not self._client.collection_exists(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )
        info = self._client.get_collection(self._collection_name)
        vectors = info.config.params.vectors
        if not isinstance(vectors, models.VectorParams):
            raise VectorStoreError(
                "QDRANT_COLLECTION_INCOMPATIBLE",
                "The vector collection configuration is incompatible",
            )
        if vectors.size != dimension:
            raise VectorStoreError(
                "QDRANT_DIMENSION_MISMATCH",
                "The vector collection dimension does not match the embedding model",
            )
        if vectors.distance != models.Distance.COSINE:
            raise VectorStoreError(
                "QDRANT_DISTANCE_MISMATCH",
                "The vector collection distance must be cosine",
            )
        for field in ("workspace_id", "case_id", "document_id"):
            if field not in info.payload_schema:
                self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.UUID,
                    wait=True,
                )

    async def replace_document_points(
        self, document_id: UUID, points: list[VectorPoint]
    ) -> None:
        try:
            await asyncio.to_thread(self._replace_document_points_sync, document_id, points)
        except Exception as exc:
            raise VectorStoreError(
                "QDRANT_INDEXING_FAILED", "The document vector index could not be updated"
            ) from exc

    def _replace_document_points_sync(
        self, document_id: UUID, points: list[VectorPoint]
    ) -> None:
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=self._document_filter(document_id)
            ),
            wait=True,
        )
        for offset in range(0, len(points), self._upsert_batch_size):
            batch = points[offset : offset + self._upsert_batch_size]
            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    models.PointStruct(
                        id=str(point.id), vector=point.vector, payload=point.payload
                    )
                    for point in batch
                ],
                wait=True,
            )

    async def count_document_points(self, document_id: UUID) -> int:
        try:
            result = await asyncio.to_thread(
                self._client.count,
                collection_name=self._collection_name,
                count_filter=self._document_filter(document_id),
                exact=True,
            )
            return result.count
        except Exception as exc:
            raise VectorStoreError(
                "QDRANT_INDEXING_FAILED", "The document vector index could not be verified"
            ) from exc

    async def search(
        self,
        query_vector: list[float],
        workspace_id: UUID,
        case_id: UUID | None,
        limit: int,
    ) -> list[VectorHit]:
        conditions = [self._match_uuid("workspace_id", workspace_id)]
        if case_id is not None:
            conditions.append(self._match_uuid("case_id", case_id))
        try:
            response = await asyncio.to_thread(
                self._client.query_points,
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=models.Filter(must=conditions),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            hits: list[VectorHit] = []
            for point in response.points:
                try:
                    point_id = UUID(str(point.id))
                except (TypeError, ValueError):
                    continue
                hits.append(
                    VectorHit(
                        id=point_id,
                        score=float(point.score),
                        payload=dict(point.payload or {}),
                    )
                )
            return hits
        except Exception as exc:
            raise VectorStoreError(
                "QDRANT_SEARCH_FAILED", "Semantic search is temporarily unavailable"
            ) from exc

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)

    @classmethod
    def _document_filter(cls, document_id: UUID) -> models.Filter:
        return models.Filter(must=[cls._match_uuid("document_id", document_id)])

    @staticmethod
    def _match_uuid(field: str, value: UUID) -> models.FieldCondition:
        return models.FieldCondition(
            key=field,
            match=models.MatchValue(value=str(value)),
        )
