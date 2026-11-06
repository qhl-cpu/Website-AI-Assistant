import logging
import re
from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.core.config import (
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    QDRANT_URL,
)


logger = logging.getLogger(__name__)
ELEVEN_ELEVEN_TITLE_PATTERN = re.compile(r"\b11\s*[-/]\s*11\b")
MAX_CAMPAIGN_PAGES = 2
MAX_CAMPAIGN_CHUNKS = 16


def is_eleven_eleven_campaign(chunk: dict) -> bool:
    """Identify 11/11 content without treating the mutable homepage URL as an ID."""
    return chunk.get("doc_id") == "pages-11-11-event" or bool(
        ELEVEN_ELEVEN_TITLE_PATTERN.search(chunk.get("title") or "")
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

    return expand_campaign_results(results)


def expand_campaign_results(results: list[dict]) -> list[dict]:
    """Include sibling 11/11 chunks so ranked hits cannot hide offers or terms.

    Keep other results in relevance order, expand at most two 11/11 documents,
    and cap each expansion. Other campaigns keep their original search behavior.
    This reads the existing index without changing it.
    """
    expanded = list(results)
    seen_chunks = {
        result["chunk"].get("chunk_id")
        for result in results
        if result["chunk"].get("chunk_id")
    }
    seen_pages = set()

    for result in results:
        chunk = result["chunk"]
        if not is_eleven_eleven_campaign(chunk):
            continue

        # A document ID avoids mixing unrelated documents sharing a URL.
        field = "doc_id" if chunk.get("doc_id") else "url"
        value = chunk.get(field)
        page_key = (field, value)
        if not value or page_key in seen_pages:
            continue
        if len(seen_pages) >= MAX_CAMPAIGN_PAGES:
            break
        seen_pages.add(page_key)

        siblings = []
        offset = None
        try:
            while len(siblings) < MAX_CAMPAIGN_CHUNKS:
                points, offset = get_qdrant_client().scroll(
                    collection_name=QDRANT_COLLECTION_NAME,
                    scroll_filter=models.Filter(must=[
                        models.FieldCondition(
                            key=field, match=models.MatchValue(value=value)
                        ),
                        models.FieldCondition(
                            key="status",
                            match=models.MatchAny(any=["publish", "manual"]),
                        ),
                    ]),
                    limit=MAX_CAMPAIGN_CHUNKS - len(siblings),
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                siblings.extend(dict(point.payload or {}) for point in points)
                if offset is None:
                    break
        except Exception:
            # Extra context is optional; retain the original search on failure.
            logger.exception("Could not expand campaign context")
            continue

        for sibling in sorted(siblings, key=lambda item: item.get("chunk_index") or 0):
            chunk_id = sibling.get("chunk_id")
            if (
                not chunk_id
                or chunk_id in seen_chunks
                or sibling.get("status") not in {"publish", "manual"}
                or sibling.get(field) != value
            ):
                continue
            seen_chunks.add(chunk_id)
            # Siblings inherit the parent hit's relevance; they were not ranked
            # independently by vector search.
            expanded.append({"score": result["score"], "chunk": sibling})

    return expanded


def get_collection_point_count() -> int:
    """
    Return the number of points currently stored in the Qdrant collection.
    """
    collection = get_qdrant_client().get_collection(
        collection_name=QDRANT_COLLECTION_NAME
    )

    return int(collection.points_count or 0)
