"""
04_embed_chunks.py

Create embeddings for retrieval-friendly chunks produced by 03_chunk_documents.py.

Input:
- data/processed/wp_chunks.jsonl

Output:
- data/processed/wp_chunks_embedded.jsonl

This script:
1. Reads chunks.
2. Sends chunk text to the OpenAI embeddings API.
3. Adds an embedding vector to each chunk.
4. Saves embedded chunks as JSONL.
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


INPUT_PATH = Path("data/processed/wp_chunks.jsonl")
OUTPUT_PATH = Path("data/processed/wp_chunks_embedded.jsonl")

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100


load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("Missing OPENAI_API_KEY. Add it to your .env file.")

client = OpenAI()


def read_jsonl(path: Path) -> list[dict]:
    """
    Read a JSONL file into a list of dictionaries.
    """
    items = []

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}. "
            "Run 03_chunk_documents.py first."
        )

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as error:
                print(f"Skipping invalid JSON on line {line_number}: {error}")

    return items


def write_jsonl(path: Path, items: list[dict]) -> None:
    """
    Write dictionaries to a JSONL file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def batch_items(items: list[dict], batch_size: int) -> list[list[dict]]:
    """
    Split items into smaller batches.
    """
    batches = []

    for start in range(0, len(items), batch_size):
        end = start + batch_size
        batches.append(items[start:end])

    return batches


def create_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Send a batch of texts to the embeddings API and return vectors.

    The response order matches the input order.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )

    return [item.embedding for item in response.data]


def build_embedding_input(chunk: dict) -> str:
    """
    Build the text sent to the embedding model.

    Metadata is included here because embeddings only understand
    the input string, not the surrounding JSON fields.
    """
    title = chunk.get("title") or ""
    page_type = chunk.get("page_type") or ""
    post_type = chunk.get("post_type") or ""
    section_type = chunk.get("section_type") or ""
    text = chunk.get("text") or ""

    return (
        f"Title: {title}\n"
        f"Post Type: {post_type}\n"
        f"Page Type: {page_type}\n"
        f"Section Type: {section_type}\n\n"
        f"{text}"
    ).strip()


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Add embeddings to chunks.
    """
    embedded_chunks = []
    batches = batch_items(chunks, BATCH_SIZE)

    for batch_index, batch in enumerate(batches, start=1):
        texts = []

        for chunk in batch:
            text = build_embedding_input(chunk)

            if not text:
                text = ""

            texts.append(text)

        try:
            embeddings = create_embeddings(texts)
        except Exception as error:
            print(f"Embedding batch {batch_index} failed: {error}")
            raise

        for chunk, embedding in zip(batch, embeddings):
            embedded_chunk = dict(chunk)
            embedded_chunk["embedding_model"] = EMBEDDING_MODEL
            embedded_chunk["embedding"] = embedding
            embedded_chunk["embedding_dimension"] = len(embedding)

            embedded_chunks.append(embedded_chunk)

        print(f"Embedded batch {batch_index}/{len(batches)}")

        # Small pause to be gentle with API rate limits.
        time.sleep(0.2)

    return embedded_chunks


def main():
    """
    Read chunks, create embeddings, and save embedded chunks.
    """
    chunks = read_jsonl(INPUT_PATH)

    if not chunks:
        print(f"No chunks found in {INPUT_PATH}")
        return

    embedded_chunks = embed_chunks(chunks)

    write_jsonl(OUTPUT_PATH, embedded_chunks)

    print(f"\nRead {len(chunks)} chunks from {INPUT_PATH}")
    print(f"Saved {len(embedded_chunks)} embedded chunks to {OUTPUT_PATH}")

    if embedded_chunks:
        dimensions = {
            chunk["embedding_dimension"]
            for chunk in embedded_chunks
        }

        print("\nEmbedding summary:")
        print(f"- Embedding model: {EMBEDDING_MODEL}")
        print(f"- Embedding dimensions found: {sorted(dimensions)}")


if __name__ == "__main__":
    main()