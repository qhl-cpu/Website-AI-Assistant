"""
Upload existing embedded JSONL chunks into Qdrant Cloud.

Input:
- vl-rag-assistant/data/processed/wp_chunks_embedded.jsonl

Each JSONL record must contain:
- chunk_id
- embedding
- embedding_dimension
- text

The script:
1. Connects to Qdrant Cloud.
2. Inspects and validates the JSONL data.
3. Creates the collection if it does not exist.
4. Converts each embedded chunk into a Qdrant point.
5. Uploads points in batches.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models


# Load environment variables from the backend .env file.
load_dotenv()

# Run this script in backend folder
INPUT_PATH = Path("../data/processed/wp_chunks_embedded.jsonl")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION_NAME",
    "vancouver_laser_content",
)

EXPECTED_VECTOR_SIZE = 1536
BATCH_SIZE = 64

# Recommended for the public website chatbot.
UPLOAD_PUBLISHED_ONLY = True


def validate_settings() -> None:
    """
    Validate required environment variables and input files.
    """
    if not QDRANT_URL:
        raise ValueError("Missing QDRANT_URL in .env")

    if not QDRANT_API_KEY:
        raise ValueError("Missing QDRANT_API_KEY in .env")

    if not QDRANT_COLLECTION_NAME:
        raise ValueError("Missing QDRANT_COLLECTION_NAME in .env")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Embedded chunks file not found: {INPUT_PATH}"
        )


def create_point_id(chunk_id: str) -> str:
    """
    Convert the string chunk ID into a stable UUID.

    Qdrant point IDs must be either:
    - unsigned integers, or
    - UUID strings

    The same chunk_id always produces the same UUID. This means rerunning
    the upload updates the existing point instead of creating duplicates.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def build_payload(item: dict) -> dict:
    """
    Build searchable metadata stored alongside the vector.

    The embedding itself is intentionally excluded from the payload because
    it is stored separately as the Qdrant point vector.
    """
    return {
        "chunk_id": item.get("chunk_id"),
        "doc_id": item.get("doc_id"),
        "wp_id": item.get("wp_id"),
        "url": item.get("url"),
        "title": item.get("title"),
        "status": item.get("status"),
        "post_type": item.get("post_type"),
        "page_type": item.get("page_type"),
        "source": item.get("source"),
        "cleaning_version": item.get("cleaning_version"),
        "section_type": item.get("section_type"),
        "chunk_index": item.get("chunk_index"),
        "text": item.get("text"),
        "token_count": item.get("token_count"),
        "word_count": item.get("word_count"),
        "char_count": item.get("char_count"),
        "embedding_model": item.get("embedding_model"),
        "embedding_dimension": item.get("embedding_dimension"),
    }


def iter_points() -> Iterator[models.PointStruct]:
    """
    Read the JSONL file lazily and yield valid Qdrant points.

    Reading lazily avoids loading the entire JSONL file and all embeddings
    into memory at once.
    """
    uploaded_count = 0
    skipped_private_count = 0
    skipped_invalid_count = 0

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                skipped_invalid_count += 1
                print(
                    f"Skipping line {line_number}: invalid JSON: {error}"
                )
                continue

            chunk_id = item.get("chunk_id")
            embedding = item.get("embedding")
            text = item.get("text")
            status = item.get("status")

            if UPLOAD_PUBLISHED_ONLY and status not in {"publish", "manual"}:
                skipped_private_count += 1
                continue

            if not chunk_id:
                skipped_invalid_count += 1
                print(
                    f"Skipping line {line_number}: missing chunk_id"
                )
                continue

            if not text:
                skipped_invalid_count += 1
                print(
                    f"Skipping line {line_number}: missing text"
                )
                continue

            if not isinstance(embedding, list):
                skipped_invalid_count += 1
                print(
                    f"Skipping line {line_number}: embedding is not a list"
                )
                continue

            if len(embedding) != EXPECTED_VECTOR_SIZE:
                skipped_invalid_count += 1
                print(
                    f"Skipping line {line_number}: "
                    f"expected vector size {EXPECTED_VECTOR_SIZE}, "
                    f"received {len(embedding)}"
                )
                continue

            uploaded_count += 1

            yield models.PointStruct(
                id=create_point_id(chunk_id),
                vector=embedding,
                payload=build_payload(item),
            )

    print()
    print("Finished reading JSONL file.")
    print(f"Valid points prepared: {uploaded_count}")
    print(f"Non-published or non-manual points skipped: {skipped_private_count}")
    print(f"Invalid points skipped: {skipped_invalid_count}")


def create_collection_if_needed(client: QdrantClient) -> None:
    """
    Create the Qdrant collection if it does not already exist.
    """
    if client.collection_exists(QDRANT_COLLECTION_NAME):
        collection_info = client.get_collection(
            collection_name=QDRANT_COLLECTION_NAME
        )

        print(
            f"Collection already exists: {QDRANT_COLLECTION_NAME}"
        )
        print(f"Current point count: {collection_info.points_count}")
        return

    client.create_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=EXPECTED_VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )

    print(f"Created collection: {QDRANT_COLLECTION_NAME}")
    print(f"Vector size: {EXPECTED_VECTOR_SIZE}")
    print("Distance: COSINE")


def main() -> None:
    validate_settings()

    print(f"Input file: {INPUT_PATH}")
    print(f"Collection: {QDRANT_COLLECTION_NAME}")
    print(
        f"Published only: {'yes' if UPLOAD_PUBLISHED_ONLY else 'no'}"
    )
    print()

    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=60,
    )

    # Confirm the database connection works.
    client.get_collections()
    print("Connected to Qdrant Cloud.")

    create_collection_if_needed(client)

    print("Uploading points...")

    client.upload_points(
        collection_name=QDRANT_COLLECTION_NAME,
        points=iter_points(),
        batch_size=BATCH_SIZE,
        parallel=1,
        max_retries=3,
        wait=True,
    )

    collection_info = client.get_collection(
        collection_name=QDRANT_COLLECTION_NAME
    )

    print()
    print("Upload completed successfully.")
    print(f"Collection: {QDRANT_COLLECTION_NAME}")
    print(f"Points in collection: {collection_info.points_count}")


if __name__ == "__main__":
    main()