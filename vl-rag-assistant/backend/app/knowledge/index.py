"""Qdrant visibility rules shared by chat retrieval and knowledge management."""

from collections.abc import Iterator

from qdrant_client import models

from app.core.config import QDRANT_COLLECTION_NAME


RECORD = "knowledge_record"
REVISION = "knowledge_revision"
SOURCE = "knowledge_source"

PAYLOAD_INDEXES = {
    RECORD: models.PayloadSchemaType.BOOL,
    REVISION: models.PayloadSchemaType.KEYWORD,
    SOURCE: models.PayloadSchemaType.KEYWORD,
    "wp_id": models.PayloadSchemaType.INTEGER,
    "doc_id": models.PayloadSchemaType.KEYWORD,
    "url": models.PayloadSchemaType.KEYWORD,
    "status": models.PayloadSchemaType.KEYWORD,
    "chunk_index": models.PayloadSchemaType.INTEGER,
    "section_type": models.PayloadSchemaType.KEYWORD,
}


class KnowledgeIndexesRequired(RuntimeError):
    """The collection blocks filters that the application needs."""


def payload_index_gaps(info: models.CollectionInfo) -> tuple[dict, dict]:
    missing = {}
    mismatched = {}
    for name, expected in PAYLOAD_INDEXES.items():
        current = info.payload_schema.get(name)
        if current is None:
            missing[name] = expected
        elif current.data_type != expected:
            mismatched[name] = expected
    return missing, mismatched


def require_knowledge_indexes(client) -> None:
    info = client.get_collection(QDRANT_COLLECTION_NAME)
    strict = info.config.strict_mode_config
    if not (strict and strict.enabled and strict.unindexed_filtering_retrieve is False):
        return
    missing, mismatched = payload_index_gaps(info)
    if missing or mismatched:
        fields = ", ".join(sorted(missing.keys() | mismatched.keys()))
        raise KnowledgeIndexesRequired(f"Qdrant payload indexes are missing or incompatible: {fields}")


def matches(key, value) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def scroll_points(client, condition: models.Filter | None, fields: list[str]) -> Iterator:
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION_NAME,
            scroll_filter=condition,
            limit=256,
            offset=offset,
            with_payload=fields,
            with_vectors=False,
        )
        yield from points
        if offset is None:
            return


def visibility_filter(client) -> models.Filter:
    """Show committed revisions and legacy points that were never replaced."""
    records = scroll_points(
        client,
        models.Filter(must=[matches(RECORD, True)]),
        [REVISION, "wp_id", "legacy_doc_id"],
    )
    revisions = []
    wp_ids = set()
    doc_ids = set()
    for point in records:
        record = point.payload
        if record.get(REVISION):
            revisions.append(record[REVISION])
        if record.get("wp_id"):
            wp_ids.add(record["wp_id"])
        if record.get("legacy_doc_id"):
            doc_ids.add(record["legacy_doc_id"])

    legacy = models.Filter(
        must=[models.IsEmptyCondition(is_empty=models.PayloadField(key=SOURCE))]
    )
    overrides = []
    if wp_ids:
        overrides.append(models.FieldCondition(key="wp_id", match=models.MatchAny(any=sorted(wp_ids))))
    if doc_ids:
        overrides.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=sorted(doc_ids))))
    if overrides:
        legacy.must_not = overrides

    allowed = [legacy]
    if revisions:
        allowed.append(models.FieldCondition(key=REVISION, match=models.MatchAny(any=revisions)))
    return models.Filter(should=allowed)
