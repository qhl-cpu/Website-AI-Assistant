import json
from pathlib import Path

INPUT_PATH = Path("data/raw/wp_pages.jsonl")


def search_documents(keyword: str, content_chars: int = 2000):
    keyword_lower = keyword.lower()
    matches = []

    with INPUT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            document = json.loads(line)

            searchable_text = (
                document.get("title", "")
                + "\n"
                + document.get("url", "")
                + "\n"
                + document.get("content", "")
            ).lower()

            if keyword_lower in searchable_text:
                matches.append(document)

    print(f"Found {len(matches)} matching documents for: {keyword}")
    print()

    for index, document in enumerate(matches[:10], start=1):
        print("=" * 100)
        print(f"MATCH {index}")
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
    keyword = input("Search keyword: ").strip()
    search_documents(keyword)