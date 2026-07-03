"""
02_clean_documents.py

Clean and normalize raw WordPress documents produced by 01_ingest_wordpress.py.

Input:
- data/raw/wp_documents_raw.jsonl

Output:
- data/processed/wp_documents_clean.jsonl

"""

import json
import re
from pathlib import Path


INPUT_PATH = Path("data/raw/wp_documents_raw.jsonl")
OUTPUT_PATH = Path("data/processed/wp_documents_clean.jsonl")


def normalize_whitespace(text: str) -> str:
    """
    Normalize messy whitespace while preserving paragraph breaks.

    Example:
    - removes extra spaces
    - converts multiple blank lines into one blank line
    - keeps content readable for later chunking
    """
    if not text:
        return ""

    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove extra spaces/tabs inside each line.
    lines = []
    for line in text.split("\n"):
        line = " ".join(line.split())
        lines.append(line)

    text = "\n".join(lines)

    # Collapse 3+ newlines into 2 newlines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def remove_repeated_lines(text: str) -> str:
    """
    Remove repeated lines while keeping the original order.

    This helps with Elementor/ACF content where the same heading,
    CTA text, or label may appear multiple times.
    """
    if not text:
        return ""

    cleaned_lines = []
    seen = set()

    for line in text.split("\n"):
        normalized_line = line.strip()

        if not normalized_line:
            cleaned_lines.append("")
            continue

        # Use lowercase version only for duplicate detection.
        duplicate_key = normalized_line.lower()

        if duplicate_key in seen:
            continue

        seen.add(duplicate_key)
        cleaned_lines.append(normalized_line)

    return normalize_whitespace("\n".join(cleaned_lines))


def remove_common_noise(text: str) -> str:
    """
    Remove common website text that is not useful for RAG.

    Keep this conservative. Do not remove too aggressively because
    clinic content may include short but important phrases.
    """
    if not text:
        return ""

    noise_phrases = {
        "skip to content",
        "book now",
        "buy now",
        "shop now",
        "learn more",
        "read more",
        "contact us",
        "menu",
        "close",
        "next",
        "previous",
        "submit",

        # Generic repeated ACF headings
        "concern section title do you have these concerns",
    }

    cleaned_lines = []

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        # Normalize weird spaces like non-breaking spaces.
        normalized_line = stripped.replace("\xa0", " ")

        # Remove punctuation, symbols, and emoji.
        # Keep only letters, numbers, and spaces.
        normalized_line = re.sub(r"[^a-zA-Z0-9\s]", "", normalized_line)

        # Normalize repeated spaces and lowercase.
        normalized_line = " ".join(normalized_line.split()).lower()

        if normalized_line in noise_phrases:
            continue

        cleaned_lines.append(stripped)

    return normalize_whitespace("\n".join(cleaned_lines))


def normalize_title(title: str) -> str:
    """
    Clean document titles.

    01_ingest_wordpress.py already removes 'Private:',
    but this function gives us an extra safety layer.
    """
    if not title:
        return ""

    title = title.replace("Private:", "")
    title = title.replace("Protected:", "")
    title = normalize_whitespace(title)

    return title


def normalize_url(url: str) -> str:
    """
    Normalize URLs.

    For now, keep this simple:
    - strip whitespace
    - remove trailing slash unless it is the domain root
    """
    if not url:
        return ""

    return url.strip()


def clean_content(content: str) -> str:
    """
    Main content cleaning pipeline.

    The order matters:
    1. normalize whitespace
    2. remove common website noise
    3. remove duplicate lines
    4. normalize whitespace again
    """
    content = normalize_whitespace(content)
    content = remove_common_noise(content)
    content = remove_repeated_lines(content)
    content = normalize_whitespace(content)

    return content


def is_document_usable(document: dict) -> bool:
    """
    Decide whether a cleaned document should be kept.

    A document should have:
    - a title or URL
    - meaningful cleaned content
    """
    title = document.get("title") or ""
    url = document.get("url") or ""
    content = document.get("content") or ""

    if not title and not url:
        return False

    # Avoid saving almost-empty pages.
    if len(content.split()) < 20:
        return False

    return True


def clean_document(raw_document: dict) -> dict:
    """
    Clean one raw WordPress document and preserve important metadata.
    """
    title = normalize_title(raw_document.get("title", ""))
    url = normalize_url(raw_document.get("url", ""))
    content = clean_content(raw_document.get("content", ""))

    cleaned_document = {
        "wp_id": raw_document.get("wp_id"),
        "doc_id": raw_document.get("doc_id"),
        "url": url,
        "title": title,
        "status": raw_document.get("status"),
        "post_type": raw_document.get("post_type"),
        "page_type": raw_document.get("page_type", "general"),
        "content": content,
        "source": raw_document.get("source", "wordpress_rest_api"),
        "cleaning_version": "v1",
        "word_count": len(content.split()),
        "char_count": len(content),
    }

    return cleaned_document


def read_jsonl(path: Path) -> list[dict]:
    """
    Read a JSONL file into a list of dictionaries.
    """
    documents = []

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


def write_jsonl(path: Path, documents: list[dict]) -> None:
    """
    Write dictionaries to a JSONL file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for document in documents:
            f.write(json.dumps(document, ensure_ascii=False) + "\n")


def main():
    """
    Clean raw WordPress documents and save processed documents.
    """
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}. "
            "Run 01_ingest_wordpress.py first."
        )

    raw_documents = read_jsonl(INPUT_PATH)

    cleaned_documents = []
    skipped_count = 0

    for raw_document in raw_documents:
        cleaned_document = clean_document(raw_document)

        if not is_document_usable(cleaned_document):
            skipped_count += 1
            continue

        cleaned_documents.append(cleaned_document)

    write_jsonl(OUTPUT_PATH, cleaned_documents)

    print(f"Read {len(raw_documents)} raw documents from {INPUT_PATH}")
    print(f"Saved {len(cleaned_documents)} cleaned documents to {OUTPUT_PATH}")
    print(f"Skipped {skipped_count} documents because they were too short or unusable")

    if cleaned_documents:
        word_counts = [doc["word_count"] for doc in cleaned_documents]

        print("\nCleaning summary:")
        print(f"- Min words: {min(word_counts)}")
        print(f"- Max words: {max(word_counts)}")
        print(f"- Average words: {sum(word_counts) // len(word_counts)}")


if __name__ == "__main__":
    main()