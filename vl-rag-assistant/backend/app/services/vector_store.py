from functools import lru_cache

from qdrant_client import QdrantClient

from app.core.config import (
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    QDRANT_URL,
)


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """
    Create one reusable Qdrant client for the application process.
    """
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=30,
    )


def search_qdrant(
    query_embedding: list[float],
    top_k: int,
) -> list[dict]:
    """
    Retrieve the closest published content chunks from Qdrant Cloud.

    The returned shape matches the format expected by the RAG context
    builder: each item contains a similarity score and its chunk payload.
    """
    response = get_qdrant_client().query_points(
        collection_name=QDRANT_COLLECTION_NAME,
        query=query_embedding,
        limit=top_k * 3,
        with_payload=True,
        with_vectors=False,
    )

    results = []

    for point in response.points:
        payload = dict(point.payload or {})

        if payload.get("status") not in {"publish", "manual"}:
            continue

        results.append(
            {
                "score": point.score,
                "chunk": payload,
            }
        )

        if len(results) == top_k:
            break

    return results


def get_collection_point_count() -> int:
    """
    Return the number of points currently stored in the Qdrant collection.
    """
    collection = get_qdrant_client().get_collection(
        collection_name=QDRANT_COLLECTION_NAME
    )

    return int(collection.points_count or 0)
