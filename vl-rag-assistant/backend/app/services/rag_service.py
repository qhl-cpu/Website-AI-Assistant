import json
import math
from functools import lru_cache

from openai import OpenAI

from app.core.config import (
    CHAT_MODEL,
    EMBEDDING_MODEL,
    EMBEDDED_CHUNKS_PATH,
    MAX_CONTEXT_CHARS_PER_CHUNK,
    TOP_K,
)


client = OpenAI()


def read_jsonl(path) -> list[dict]:
    """
    Read JSONL file into a list of dictionaries.
    """
    items = []

    if not path.exists():
        raise FileNotFoundError(
            f"Embedded chunks file not found: {path}. "
            "Run 01, 02, 03, and 04 first."
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


@lru_cache(maxsize=1)
def load_chunks() -> tuple[dict, ...]:
    """
    Load embedded chunks once and cache them.

    This avoids re-reading wp_chunks_embedded.jsonl on every user question.
    """
    chunks = read_jsonl(EMBEDDED_CHUNKS_PATH)
    return tuple(chunks)


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


def search_chunks(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Search embedded chunks using cosine similarity.
    """
    chunks = load_chunks()
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

        if url and url not in seen_urls:
            sources.append(
                {
                    "source_id": source_id,
                    "title": title,
                    "url": url,
                    "section_type": section_type,
                    "score": round(score, 4),
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


def answer_question(question: str) -> dict:
    """
    Main function used by the FastAPI /chat endpoint.
    """
    results = search_chunks(question, top_k=TOP_K)
    context, sources = build_context(results)
    answer = generate_answer(question, context)

    return {
        "answer": answer,
        "sources": sources,
    }


def debug_search(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Return retrieval results without calling the chat model.

    Useful for testing whether bad answers are caused by bad retrieval.
    """
    results = search_chunks(query, top_k=top_k)

    formatted_results = []

    for result in results:
        chunk = result["chunk"]
        text = chunk.get("text") or ""

        formatted_results.append(
            {
                "score": round(result["score"], 4),
                "chunk_id": chunk.get("chunk_id") or "",
                "title": chunk.get("title") or "",
                "url": chunk.get("url") or "",
                "section_type": chunk.get("section_type"),
                "text_preview": text[:300],
            }
        )

    return formatted_results