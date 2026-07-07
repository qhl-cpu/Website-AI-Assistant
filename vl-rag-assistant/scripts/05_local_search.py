"""
05_local_search.py

Test local semantic search over embedded WordPress chunks.

Input:
- data/processed/wp_chunks_embedded.jsonl

This script:
1. Loads embedded chunks.
2. Embeds a user query.
3. Compares the query embedding against chunk embeddings.
4. Returns the most relevant chunks.
"""

import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


INPUT_PATH = Path("data/processed/wp_chunks_embedded.jsonl")

EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K = 5


load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("Missing OPENAI_API_KEY. Add it to your .env file.")

client = OpenAI()


def read_jsonl(path: Path) -> list[dict]:
    """
    Read JSONL file into a list of dictionaries.
    """
    items = []

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}. "
            "Run 04_embed_chunks.py first."
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


def create_query_embedding(query: str) -> list[float]:
    """
    Create an embedding vector for the user's search query.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )

    return response.data[0].embedding


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Higher score means more semantically similar.
    """
    dot_product = 0
    norm_a = 0
    norm_b = 0

    for a, b in zip(vector_a, vector_b):
        dot_product += a * b
        norm_a += a * a
        norm_b += b * b

    if norm_a == 0 or norm_b == 0:
        return 0

    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))


def search_chunks(query: str, chunks: list[dict], top_k: int = TOP_K) -> list[dict]:
    """
    Search embedded chunks using cosine similarity.
    """
    query_embedding = create_query_embedding(query)

    scored_chunks = []

    for chunk in chunks:
        chunk_embedding = chunk.get("embedding")

        if not chunk_embedding:
            continue

        score = cosine_similarity(query_embedding, chunk_embedding)

        scored_chunks.append(
            {
                "score": score,
                "chunk": chunk,
            }
        )

    scored_chunks.sort(key=lambda item: item["score"], reverse=True)

    return scored_chunks[:top_k]


def print_results(query: str, results: list[dict]) -> None:
    """
    Print search results in a readable format.
    """
    print("\n" + "=" * 80)
    print(f"Query: {query}")
    print("=" * 80)

    for index, result in enumerate(results, start=1):
        score = result["score"]
        chunk = result["chunk"]

        title = chunk.get("title", "")
        url = chunk.get("url", "")
        page_type = chunk.get("page_type", "")
        section_type = chunk.get("section_type", "")
        text = chunk.get("text", "")

        preview = text[:700].replace("\n", " ")

        print(f"\nResult {index}")
        print("-" * 80)
        print(f"Score: {score:.4f}")
        print(f"Title: {title}")
        print(f"Page Type: {page_type}")
        print(f"Section Type: {section_type}")
        print(f"URL: {url}")
        print(f"Text Preview: {preview}")


def main():
    """
    Run local semantic search from the terminal.
    """
    chunks = read_jsonl(INPUT_PATH)

    print(f"Loaded {len(chunks)} embedded chunks.")
    print("Type a question to search your website content.")
    print("Type 'exit' to stop.\n")

    while True:
        query = input("Search query: ").strip()

        if query.lower() in {"exit", "quit"}:
            break

        if not query:
            continue

        results = search_chunks(query, chunks)
        print_results(query, results)


if __name__ == "__main__":
    main()