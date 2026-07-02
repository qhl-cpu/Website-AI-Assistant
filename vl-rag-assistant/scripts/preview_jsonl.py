import json
from pathlib import Path

INPUT_PATH = Path("data/raw/wp_pages.jsonl")


def preview_documents(limit: int = 10, content_chars: int = 1500):
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"File not found: {INPUT_PATH}")

    with INPUT_PATH.open("r", encoding="utf-8") as f:
        for index, line in zip(range(limit), f):
            document = json.loads(line)

            print("=" * 100)
            print(f"DOCUMENT {index + 1}")
            print("=" * 100)

            print("Title:     ", document.get("title"))
            print("URL:       ", document.get("url"))
            print("Status:    ", document.get("status"))
            print("Post Type: ", document.get("post_type"))
            print("Page Type: ", document.get("page_type"))
            print("WP ID:     ", document.get("wp_id"))
            print("-" * 100)

            content = document.get("content", "")
            print(content[:content_chars])

            if len(content) > content_chars:
                print("\n...CONTENT TRUNCATED...")

            print()


if __name__ == "__main__":
    preview_documents(limit=10, content_chars=1500)