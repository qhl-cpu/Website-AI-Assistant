"""
03_chunk_documents.py

Create retrieval-friendly chunks from cleaned WordPress documents.

Input:
- data/processed/wp_documents_clean.jsonl

Output:
- data/processed/wp_chunks.jsonl

Chunking strategy:
1. Group ACF-style fields into meaningful sections.
2. Create draft chunks from those sections.
3. Count tokens for each draft chunk.
4. If chunk <= 500 tokens, keep it.
5. If chunk > 500 tokens, split it with overlap.
"""

import json
from pathlib import Path

import tiktoken


INPUT_PATH = Path("data/processed/wp_documents_clean.jsonl")
OUTPUT_PATH = Path("data/processed/wp_chunks.jsonl")

ENCODING_NAME = "cl100k_base"

MAX_TOKENS = 500
OVERLAP_TOKENS = 80
MIN_CHUNK_WORDS = 8
IMPORTANT_SHORT_SECTION_TYPES = {
    "duration",
    "sessions",
    "aftercare",
    "operator",
}


def read_jsonl(path: Path) -> list[dict]:
    """
    Read a JSONL file into a list of dictionaries.
    """
    documents = []

    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found: {path}. "
            "Run 02_clean_documents.py first."
        )

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                documents.append(json.loads(line))
            except json.JSONDecodeError as error:
                print(f"Skipping invalid JSON on line {line_number}: {error}")

    return documents


def write_jsonl(path: Path, items: list[dict]) -> None:
    """
    Write a list of dictionaries to a JSONL file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def get_encoding():
    """
    Load the tokenizer used for counting and splitting text by tokens.
    """
    return tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str, encoding) -> int:
    """
    Count how many tokens a text string uses.
    """
    if not text:
        return 0

    return len(encoding.encode(text))


def split_long_text_by_tokens(
    text: str,
    encoding,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """
    Split a long text section into overlapping token chunks.

    This is only used when a meaningful section is too large.
    """
    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return [text]

    chunks = []
    start = 0

    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens).strip()

        if chunk_text:
            chunks.append(chunk_text)

        if end >= len(tokens):
            break

        start = end - overlap_tokens

    return chunks


def is_labeled_line(line: str) -> bool:
    """
    Detect whether a line looks like an ACF label/value pair.

    Example:
    - Overview: text...
    - Benefit 1 Description: text...
    - FAQ Question: text...
    """
    if ":" not in line:
        return False

    label, value = line.split(":", 1)

    label = label.strip()
    value = value.strip()

    if not label or not value:
        return False

    # Avoid treating normal long sentences with colons as labels.
    if len(label.split()) > 7:
        return False

    return True


def get_label(line: str) -> str:
    """
    Return the label before the first colon.
    """
    if ":" not in line:
        return ""

    return line.split(":", 1)[0].strip()


def get_section_group(label: str) -> str:
    """
    Convert an ACF label into a broader section type.

    These section types become metadata on each chunk.
    """
    label_lower = label.lower()

    overview_labels = {
        "treatment or concern name",
        "location",
        "overview",
        "hero description",
        "hero bullet text",
    }

    duration_labels = {
        "treatment duration",
        "duration",
    }

    session_labels = {
        "min sessions",
        "max sessions",
        "recommended sessions",
    }

    aftercare_labels = {
        "aftercare",
    }

    treatment_area_labels = {
        "treatment areas",
    }

    how_it_works_labels = {
        "how the treatment works",
        "how it works",
    }

    operator_labels = {
        "operator type",
    }

    technology_labels = {
        "machine name",
        "machine section title",
        "machine description",
    }

    comparison_labels = {
        "comparison section title",
        "traditional approach",
        "clinic approach",
    }

    if label_lower in overview_labels:
        return "overview"

    if label_lower in duration_labels:
        return "duration"

    if label_lower in session_labels:
        return "sessions"

    if label_lower in aftercare_labels:
        return "aftercare"

    if label_lower in treatment_area_labels:
        return "treatment_areas"

    if label_lower in how_it_works_labels:
        return "how_it_works"

    if label_lower in operator_labels:
        return "operator"

    if label_lower.startswith("concern "):
        return "concerns"

    if label_lower.startswith("benefit"):
        return "benefits"

    if label_lower.startswith("procedure step"):
        return "procedure"

    if label_lower in technology_labels:
        return "technology"

    if label_lower.startswith("safety") or label_lower == "expected side effects":
        return "safety"

    if label_lower in comparison_labels:
        return "comparison"

    if label_lower.startswith("faq"):
        return "faq"

    return "general"


def split_content_into_sections(content: str) -> list[dict]:
    """
    Group cleaned document content into meaningful sections.

    This function uses ACF-style labels to avoid random word-based chunking.
    It tries to keep related fields together:
    - FAQ Question + FAQ Answer
    - Benefit title + benefit description
    - Procedure step title + procedure step description
    - Overview/introduction fields
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    sections = []
    current_group = None
    current_lines = []

    def flush_current():
        nonlocal current_group, current_lines

        if current_lines:
            sections.append(
                {
                    "section_type": current_group or "general",
                    "text": "\n".join(current_lines).strip(),
                }
            )

        current_group = None
        current_lines = []

    for line in lines:
        if not is_labeled_line(line):
            if current_group is None:
                current_group = "general"

            current_lines.append(line)
            continue

        label = get_label(line)
        group = get_section_group(label)
        label_lower = label.lower()

        # Keep each FAQ Question + FAQ Answer together.
        if group == "faq":
            if label_lower.startswith("faq") and label_lower.endswith("question"):
                flush_current()
                current_group = "faq"
                current_lines = [line]
                continue

            if label_lower.startswith("faq") and label_lower.endswith("answer"):
                if current_group == "faq":
                    current_lines.append(line)
                    flush_current()
                else:
                    current_group = "faq"
                    current_lines = [line]
                    flush_current()
                continue

        # Keep each Procedure Step Title + Procedure Step Description together.
        if group == "procedure":
            if label_lower.startswith("procedure step") and label_lower.endswith("title"):
                flush_current()
                current_group = "procedure"
                current_lines = [line]
                continue

            if label_lower.startswith("procedure step") and label_lower.endswith("description"):
                if current_group == "procedure":
                    current_lines.append(line)
                    flush_current()
                else:
                    current_group = "procedure"
                    current_lines = [line]
                    flush_current()
                continue

        # For normal sections, group consecutive lines with the same section type.
        if current_group is None:
            current_group = group
            current_lines = [line]
        elif current_group == group:
            current_lines.append(line)
        else:
            flush_current()
            current_group = group
            current_lines = [line]

    flush_current()

    return sections


def build_chunk(
    document: dict,
    chunk_text: str,
    chunk_index: int,
    section_type: str,
    token_count: int,
) -> dict:
    """
    Build one final chunk object with metadata needed for retrieval.
    """
    doc_id = document.get("doc_id")

    return {
        "chunk_id": f"{doc_id}-chunk-{chunk_index:03d}",
        "doc_id": doc_id,
        "wp_id": document.get("wp_id"),
        "url": document.get("url"),
        "title": document.get("title"),
        "status": document.get("status"),
        "post_type": document.get("post_type"),
        "page_type": document.get("page_type", "general"),
        "source": document.get("source", "wordpress_rest_api"),
        "cleaning_version": document.get("cleaning_version"),
        "section_type": section_type,
        "chunk_index": chunk_index,
        "text": chunk_text,
        "token_count": token_count,
        "word_count": len(chunk_text.split()),
        "char_count": len(chunk_text),
    }


def should_keep_section(section_type: str, text: str) -> bool:
    """
    Decide whether a section is worth saving as a chunk.

    Most sections should have at least MIN_CHUNK_WORDS.
    But factual sections like duration can be short and still important.
    """
    word_count = len(text.split())

    if word_count >= MIN_CHUNK_WORDS:
        return True

    if section_type in IMPORTANT_SHORT_SECTION_TYPES and word_count >= 3:
        return True

    return False


def chunk_document(document: dict, encoding) -> list[dict]:
    """
    Chunk one cleaned document.

    Process:
    1. Group ACF fields into meaningful sections.
    2. Create draft chunks from each section.
    3. Count tokens.
    4. Keep chunks under MAX_TOKENS.
    5. Split oversized chunks with token overlap.
    """
    content = document.get("content", "")

    if not content.strip():
        return []

    sections = split_content_into_sections(content)

    chunks = []
    chunk_index = 0

    for section in sections:
        section_type = section["section_type"]
        section_text = section["text"].strip()

        if not should_keep_section(section_type, section_text):
            continue

        token_count = count_tokens(section_text, encoding)

        if token_count <= MAX_TOKENS:
            chunk = build_chunk(
                document=document,
                chunk_text=section_text,
                chunk_index=chunk_index,
                section_type=section_type,
                token_count=token_count,
            )

            chunks.append(chunk)
            chunk_index += 1
            continue

        split_texts = split_long_text_by_tokens(
            text=section_text,
            encoding=encoding,
            max_tokens=MAX_TOKENS,
            overlap_tokens=OVERLAP_TOKENS,
        )

        for split_text in split_texts:
            split_token_count = count_tokens(split_text, encoding)

            chunk = build_chunk(
                document=document,
                chunk_text=split_text,
                chunk_index=chunk_index,
                section_type=section_type,
                token_count=split_token_count,
            )

            chunks.append(chunk)
            chunk_index += 1

    return chunks


def main():
    """
    Read cleaned documents, create chunks, and save them for embeddings.
    """
    encoding = get_encoding()
    documents = read_jsonl(INPUT_PATH)

    all_chunks = []

    for document in documents:
        chunks = chunk_document(document, encoding)
        all_chunks.extend(chunks)

    write_jsonl(OUTPUT_PATH, all_chunks)

    print(f"Read {len(documents)} cleaned documents from {INPUT_PATH}")
    print(f"Saved {len(all_chunks)} chunks to {OUTPUT_PATH}")

    if all_chunks:
        token_counts = [chunk["token_count"] for chunk in all_chunks]
        word_counts = [chunk["word_count"] for chunk in all_chunks]

        print("\nChunking summary:")
        print(f"- Min tokens: {min(token_counts)}")
        print(f"- Max tokens: {max(token_counts)}")
        print(f"- Average tokens: {sum(token_counts) // len(token_counts)}")
        print(f"- Min words: {min(word_counts)}")
        print(f"- Max words: {max(word_counts)}")
        print(f"- Average words: {sum(word_counts) // len(word_counts)}")


if __name__ == "__main__":
    main()