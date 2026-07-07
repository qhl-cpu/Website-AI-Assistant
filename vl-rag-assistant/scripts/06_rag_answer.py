"""
06_rag_answer.py

Generate grounded answers from embedded WordPress/manual chunks.

Input:
- data/processed/wp_chunks_embedded.jsonl

This script:
1. Loads embedded chunks.
2. Embeds the user's question.
3. Retrieves relevant chunks.
4. Sends the question + retrieved chunks to OpenAI.
5. Prints a human-readable answer with sources.
"""

import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


INPUT_PATH = Path("data/processed/wp_chunks_embedded.jsonl")

EMBEDDING_MODEL = "text-embedding-3-small"

CHAT_MODEL = "gpt-4o-mini"

TOP_K = 8
MAX_CONTEXT_CHARS_PER_CHUNK = 1200


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
    Create an embedding vector for the user's question.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )

    return response.data[0].embedding


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
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


def build_context(results: list[dict]) -> tuple[str, list[dict]]:
    """
    Build the context string that will be sent to the chat model.

    Each retrieved chunk gets a source label like [S1], [S2], etc.
    """
    context_parts = []
    sources = []

    seen_urls = set()

    for index, result in enumerate(results, start=1):
        chunk = result["chunk"]
        score = result["score"]

        source_id = f"S{index}"

        title = chunk.get("title") or ""
        url = chunk.get("url") or ""
        post_type = chunk.get("post_type") or ""
        page_type = chunk.get("page_type") or ""
        section_type = chunk.get("section_type") or ""
        text = (chunk.get("text") or "").strip()

        if len(text) > MAX_CONTEXT_CHARS_PER_CHUNK:
            text = text[:MAX_CONTEXT_CHARS_PER_CHUNK] + "..."

        context_part = (
            f"[{source_id}]\n"
            f"Title: {title}\n"
            f"URL: {url}\n"
            f"Post Type: {post_type}\n"
            f"Page Type: {page_type}\n"
            f"Section Type: {section_type}\n"
            f"Similarity Score: {score:.4f}\n"
            f"Content:\n{text}"
        )

        context_parts.append(context_part)

        if url not in seen_urls:
            sources.append(
                {
                    "source_id": source_id,
                    "title": title,
                    "url": url,
                    "section_type": section_type,
                    "score": score,
                }
            )
            seen_urls.add(url)

    context = "\n\n---\n\n".join(context_parts)

    return context, sources


def generate_answer(question: str, context: str) -> str:
    """
    Generate a grounded answer using only retrieved website context.
    """
    system_prompt = """
You are a helpful website assistant for Vancouver Laser & Skin Care Centre.

Rules:
- Answer using only the provided website context.
- Do not invent details that are not in the context.
- If the answer is not in the context, say you do not have enough information from the website content.
- Do not diagnose medical conditions.
- Do not guarantee treatment results.
- Do not say a treatment is definitely suitable for the user.
- Recommend booking a free consultation with our professional consultants when suitability depends on skin type, health history, pregnancy, medication, recent sun exposure, or other personal factors.
- Keep answers clear, friendly, and concise.
- Include source labels like [S1] or [S2] when using information from a source.
""".strip()

    user_prompt = f"""
User question:
{question}

Website context:
{context}

Answer the user's question using only the website context above.
""".strip()

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content.strip()


def print_sources(sources: list[dict]) -> None:
    """
    Print source URLs used for the answer.
    """
    if not sources:
        return

    print("\nSources:")
    print("-" * 80)

    for source in sources:
        source_id = source.get("source_id")
        title = source.get("title")
        url = source.get("url")
        section_type = source.get("section_type")
        score = source.get("score")

        print(f"[{source_id}] {title}")
        print(f"Section Type: {section_type}")
        print(f"Score: {score:.4f}")
        print(f"URL: {url}")
        print()


def main():
    """
    Run the RAG assistant from the terminal.
    """
    chunks = read_jsonl(INPUT_PATH)

    print(f"Loaded {len(chunks)} embedded chunks.")
    print("Ask a question. Type 'exit' to stop.\n")

    while True:
        question = input("Question: ").strip()

        if question.lower() in {"exit", "quit"}:
            break

        if not question:
            continue

        results = search_chunks(question, chunks)
        context, sources = build_context(results)
        answer = generate_answer(question, context)

        print("\n" + "=" * 80)
        print("Answer")
        print("=" * 80)
        print(answer)

        print_sources(sources)


if __name__ == "__main__":
    main()