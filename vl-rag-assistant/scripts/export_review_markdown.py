import json
from pathlib import Path

INPUT_PATH = Path("data/raw/wp_pages.jsonl")
OUTPUT_PATH = Path("data/debug/wp_pages_review.md")


def export_review_markdown():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    documents = []

    with INPUT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            documents.append(json.loads(line))

    with OUTPUT_PATH.open("w", encoding="utf-8") as out:
        out.write("# WordPress Content Review\n\n")
        out.write(f"Total documents: {len(documents)}\n\n")

        for index, document in enumerate(documents, start=1):
            out.write("---\n\n")
            out.write(f"## {index}. {document.get('title')}\n\n")
            out.write(f"- **URL:** {document.get('url')}\n")
            out.write(f"- **Status:** {document.get('status')}\n")
            out.write(f"- **Post Type:** {document.get('post_type')}\n")
            out.write(f"- **Page Type:** {document.get('page_type')}\n")
            out.write(f"- **WP ID:** {document.get('wp_id')}\n\n")

            out.write("### Content\n\n")
            out.write(document.get("content", ""))
            out.write("\n\n")

    print(f"Exported readable review file to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_review_markdown()