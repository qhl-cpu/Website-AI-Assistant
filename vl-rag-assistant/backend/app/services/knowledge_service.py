"""Replace or remove individual sources in the shared Qdrant collection."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from uuid import NAMESPACE_URL, uuid4, uuid5

from qdrant_client import models

from app.core.config import EMBEDDING_MODEL, QDRANT_COLLECTION_NAME
from app.knowledge.index import RECORD, REVISION, SOURCE, scroll_points
from app.knowledge.managed_content import (
    ContentError,
    page_key,
    page_url,
    prepare_chunks,
    read_file,
    read_page,
)
from app.services.rag_service import client as openai_client
from app.services.site_links import load_page_link_index


logger = logging.getLogger(__name__)
mutation_lock = Lock()
DIMENSIONS = 1536
PAGE_FIELDS = ["wp_id", "post_type", "doc_id", "url", "title", "status"]
RECORD_FIELDS = [RECORD, SOURCE, REVISION, "kind", "legacy_doc_id", "updated_at", "chunk_count"]


def source_id(payload: dict) -> str:
    if payload.get(SOURCE):
        return payload[SOURCE]
    identity = f"wp/{payload['wp_id']}" if payload.get("wp_id") else f"legacy/{payload['doc_id']}"
    return str(uuid5(NAMESPACE_URL, f"vl-rag/{identity}"))


def catalog(client) -> tuple[dict, dict]:
    records = {}
    point_ids = defaultdict(list)
    legacy = {}
    # The admin list already reads the full catalog. Keep this read available
    # on strict collections before their search indexes have been initialized.
    for point in scroll_points(client, None, PAGE_FIELDS + RECORD_FIELDS):
        payload = point.payload or {}
        if payload.get(RECORD):
            records[point.id] = payload
            continue
        if payload.get("status") not in {"publish", "manual"}:
            continue
        if not (payload.get(SOURCE) or payload.get("wp_id") or payload.get("doc_id")):
            continue
        key = source_id(payload)
        point_ids[key].append(point.id)
        if not payload.get(SOURCE):
            legacy[key] = {
                **payload,
                "kind": "page" if payload.get("status") == "publish" else "file",
                "legacy_doc_id": payload.get("doc_id"),
            }

    for key, entry in legacy.items():
        if key not in records:
            records[key] = {**entry, "chunk_count": len(point_ids[key])}
    return records, point_ids


def list_sources(client) -> list[dict]:
    records, point_ids = catalog(client)
    rows = []
    for key, record in records.items():
        removed = record.get(RECORD) and not record.get(REVISION)
        if removed and not point_ids[key]:
            continue
        rows.append({
            "id": key,
            "kind": record["kind"],
            "title": record.get("title") or "Untitled",
            "url": record.get("url") if record["kind"] == "page" else "",
            "updated_at": record.get("updated_at"),
            "chunk_count": record.get("chunk_count"),
            "cleanup_pending": bool(removed),
        })
    return sorted(rows, key=lambda row: (row["kind"], row["title"].casefold()))


def embed(chunks: list[dict]) -> list[list[float]]:
    inputs = [
        f"Title: {chunk['title']}\nPost Type: {chunk['post_type']}\n"
        f"Page Type: {chunk['page_type']}\nSection Type: {chunk['section_type']}\n\n{chunk['text']}"
        for chunk in chunks
    ]
    vectors = []
    for start in range(0, len(inputs), 64):
        batch = inputs[start:start + 64]
        response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        items = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(batch))) or any(
            len(item.embedding) != DIMENSIONS for item in items
        ):
            raise RuntimeError("The embeddings service returned an incomplete or incompatible result.")
        vectors.extend(item.embedding for item in items)
    return vectors


def write_record(client, key: str, record: dict) -> None:
    # A single record switches which complete revision chat can retrieve.
    client.upsert(
        collection_name=QDRANT_COLLECTION_NAME,
        points=[models.PointStruct(
            id=key,
            vector=[0.0] * DIMENSIONS,
            payload={**record, RECORD: True},
        )],
        wait=True,
        ordering=models.WriteOrdering.STRONG,
    )
    load_page_link_index.cache_clear()


def cleanup(client, ids: list, key: str) -> str | None:
    if not ids:
        return None
    try:
        for start in range(0, len(ids), 256):
            client.delete(
                collection_name=QDRANT_COLLECTION_NAME,
                points_selector=models.PointIdsList(points=ids[start:start + 256]),
                wait=True,
                ordering=models.WriteOrdering.STRONG,
            )
    except Exception:
        logger.exception("Could not clean obsolete knowledge points for %s", key)
        return "The change is live. Some old chunks could not be deleted and are hidden from chat."
    return None


def replace_source(client, key: str, previous: dict, old_ids: list, document: dict) -> str | None:
    document["doc_id"] = document.get("doc_id") or previous.get("doc_id") or key
    chunks = prepare_chunks(document)
    vectors = embed(chunks)
    revision = str(uuid4())
    points = [
        models.PointStruct(
            id=str(uuid5(NAMESPACE_URL, f"{revision}/{index}")),
            vector=vector,
            payload={**chunk, SOURCE: key, REVISION: revision, "embedding_model": EMBEDDING_MODEL},
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    try:
        for start in range(0, len(points), 64):
            client.upsert(
                collection_name=QDRANT_COLLECTION_NAME,
                points=points[start:start + 64],
                wait=True,
                ordering=models.WriteOrdering.STRONG,
            )
    except Exception:
        # No attempt to activate this revision has been made.
        cleanup(client, [point.id for point in points], key)
        raise
    record = {
        **{field: document.get(field) for field in PAGE_FIELDS if field != "status"},
        "kind": "page" if document["status"] == "publish" else "file",
        "legacy_doc_id": previous.get("legacy_doc_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(points),
        REVISION: revision,
    }
    # On an ambiguous write timeout, keep both revisions. The record decides which is live.
    write_record(client, key, record)
    return cleanup(client, old_ids, key)


def add_page(client, url: str) -> str | None:
    url = page_url(url)
    document = read_page(url)
    records, point_ids = catalog(client)
    path = page_key(document["url"])
    url_id = str(uuid5(NAMESPACE_URL, f"vl-rag/page/{path}"))
    wp_id = document.get("wp_id")
    key = source_id(document) if wp_id else url_id
    if key not in records and url_id in records:
        # Keep the ID of a source previously indexed from rendered HTML.
        key = url_id
    if not wp_id and key not in records:
        for record in records.values():
            if record["kind"] != "page" or not is_live(record) or not record.get("url"):
                continue
            try:
                same_page = page_key(record["url"]) == path
            except ContentError:
                continue
            if same_page:
                raise ContentError("This URL is already indexed. Select its webpage in the list to update it.")
    return replace_source(client, key, records.get(key, {}), point_ids[key], document)


def is_live(record: dict) -> bool:
    return bool(record and (not record.get(RECORD) or record.get(REVISION)))


def update_page(client, key: str, records: dict, point_ids: dict) -> str | None:
    previous = records.get(key, {})
    if not is_live(previous) or previous["kind"] != "page":
        raise ContentError("This webpage is no longer in the knowledge base.")
    document = read_page(previous.get("url") or "", wp_id=previous.get("wp_id"), post_type=previous.get("post_type"))
    # A previously indexed HTML page can later expose its WordPress ID. Keep the
    # existing source identity unless the WordPress record is already indexed.
    if document.get("wp_id") and source_id(document) != key and source_id(document) in records:
        raise ContentError("This URL now points to another indexed page. Select that page to update it.")
    return replace_source(client, key, previous, point_ids[key], document)


def upload_file(client, filename: str, data: bytes, key: str | None) -> str | None:
    document = read_file(filename, data)
    if key is None:
        return replace_source(client, str(uuid4()), {}, [], document)
    records, point_ids = catalog(client)
    previous = records.get(key, {})
    if not is_live(previous) or previous["kind"] != "file":
        raise ContentError("This file is no longer in the knowledge base.")
    return replace_source(client, key, previous, point_ids[key], document)


def remove_source(client, key: str, records: dict, point_ids: dict) -> str | None:
    previous = records.get(key)
    if not previous:
        raise ContentError("This source is no longer in the knowledge base.")
    write_record(client, key, {**previous, REVISION: None, "chunk_count": 0})
    return cleanup(client, point_ids[key], key)
