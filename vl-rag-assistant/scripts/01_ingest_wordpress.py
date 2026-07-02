import json
import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


# Load WordPress credentials from .env.
# Required variables:
# - WP_BASE_URL
# - WP_USERNAME
# - WP_APP_PASSWORD
load_dotenv()

WP_BASE_URL = os.getenv("WP_BASE_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

if not WP_BASE_URL or not WP_USERNAME or not WP_APP_PASSWORD:
    raise ValueError("Missing WordPress environment variables. Check your .env file.")

OUTPUT_PATH = Path("data/raw/wp_documents_raw.jsonl")


def html_to_text(html: str) -> str:
    """
    Convert WordPress/Elementor/ACF HTML into readable text.

    This version is intentionally broad.
    It works well for ACF fields because ACF values may be plain text,
    simple HTML, or Elementor-rendered HTML.
    Heavier cleanup happens later in 02_clean_documents.py.
    """
    remove_selectors = [
        # Non-content elements
        "script",
        "style",
        "noscript",
        "svg",
        "form",

        # Structural layout elements
        "header",
        "footer",
        "nav",
        "aside",

        # Common WordPress / Elementor layout areas
        ".elementor-location-header",
        ".elementor-location-footer",
        ".elementor-nav-menu",
        ".elementor-menu-toggle",
        ".elementor-popup-modal",
    ]

    soup = BeautifulSoup(html or "", "html.parser")
    # Remove unneeded elements
    for selector in remove_selectors:
        for tag in soup.select(selector):
            tag.decompose()

    # Turn HTML/plain text into text
    text = soup.get_text("\n", strip=True)

    lines = []
    seen = set()

    for line in text.splitlines():
        # Cleans extra whitespace
        line = " ".join(line.split())

        if not line:
            continue

        if line in seen:
            continue

        seen.add(line)
        lines.append(line)

    return "\n".join(lines)


def clean_title(title_html: str) -> str:
    """
    WordPress REST API titles may contain rendered HTML.
    Strip HTML tags and return plain text.
    """
    return BeautifulSoup(title_html or "", "html.parser").get_text(" ", strip=True)


def clean_private_title(title: str) -> str:
    """
    WordPress prefixes private post titles with 'Private:'.
    Remove it so the document title is cleaner for RAG.
    """
    return title.replace("Private:", "").strip()


def detect_page_type(link: str, slug: str = "", post_type: str = "") -> str:
    """
    Add a simple semantic category for later filtering/retrieval.
    """
    value = f"{link} {slug} {post_type}".lower()

    if "treatment" in value or "treatments" in value:
        return "treatment"

    if "concern" in value or "concerns" in value:
        return "concern"

    if "blog" in value or post_type == "posts":
        return "blog"

    return "general"


def prettify_acf_key(key: str) -> str:
    """
    Convert ACF machine field names into readable labels.
    These labels make the final RAG text easier to understand.
    """
    custom_labels = {
        "treatment_title_treatment_name": "Treatment Or Concern Name",
        "treatment_title_machine_name": "Machine Name",
        "treatment_title_location": "Location",
        "opening_advertisement": "Overview",
        "hero_description": "Hero Description",
        "concern_section_title": "Concern Section Title",
        "concern_introduction": "Concern Introduction",
        "concern_name1": "Concern 1",
        "concern_name2": "Concern 2",
        "concern_name3": "Concern 3",
        "treatment_area_conclusion": "Treatment Areas",
        "benefit_title_1": "Benefit 1 Title",
        "benefit_text_1": "Benefit 1 Description",
        "benefit_title_2": "Benefit 2 Title",
        "benefit_text_2": "Benefit 2 Description",
        "benefit_title_3": "Benefit 3 Title",
        "benefit_text_3": "Benefit 3 Description",
        "benefit_title_4": "Benefit 4 Title",
        "benefit_text_4": "Benefit 4 Description",
        "benefit_conclusion": "Benefit Summary",
        "treatment_duration": "Treatment Duration",
        "treatment_sessions": "Recommended Sessions",
        "treatment_aftercare": "Aftercare",
        "procedure_title": "Procedure Step Title",
        "procedure_description": "Procedure Step Description",
        "what_is_about_the_machine_title": "Machine Section Title",
        "what_is_about_the_machine_description": "Machine Description",
        "how_does_the_treatment_work_text": "How The Treatment Works",
        "is_treatment_safe_description_1": "Safety Description",
        "is_treatment_safe_description_2": "Expected Side Effects",
        "is_treatment_safe_expand_title_1": "Safety Detail 1 Title",
        "is_treatment_safe_expand_content_1": "Safety Detail 1 Description",
        "is_treatment_safe_expand_title_2": "Safety Detail 2 Title",
        "is_treatment_safe_expand_content_2": "Safety Detail 2 Description",
        "is_treatment_safe_expand_title_3": "Safety Detail 3 Title",
        "is_treatment_safe_expand_content_3": "Safety Detail 3 Description",
        "comparison_section_title": "Comparison Section Title",
        "traditional_approach_text": "Traditional Approach",
        "our_new_approach_text": "Clinic Approach",
        "question": "FAQ Question",
        "answer": "FAQ Answer",
        "schema_service_description": "Service Description",
    }

    if key in custom_labels:
        return custom_labels[key]

    return key.replace("_", " ").strip().title()


def is_probably_asset_or_relation_key(key: str) -> bool:
    """
    Skip ACF fields that are likely media, files, IDs, or relationship fields.
    Those are not useful text for the current RAG knowledge base.
    """
    key_lower = key.lower()

    ignored_exact_keys = {
        "id",
        "ID",
        "url",
        "filename",
        "filesize",
        "mime_type",
        "sizes",
        "width",
        "height",
        "alt",
        "caption",
        "description",
    }

    ignored_contains = [
        "image",
        "photo",
        "video",
        "media",
        "icon",
        "file",
        "attachment",
        "gallery",
        "before_after",
        "related_products",
        "other_popular_treatments",
        "related_blog_link",
        "shopify_product_handle",
    ]

    if key in ignored_exact_keys:
        return True

    return any(word in key_lower for word in ignored_contains)


def flatten_acf_value(value, parent_key: str = "") -> list[str]:
    """
    Recursively extract readable text from ACF values.

    Handles:
    - strings
    - useful numbers
    - repeater fields
    - nested group fields
    """
    texts = []

    if value is None:
        return texts

    label = prettify_acf_key(parent_key) if parent_key else ""

    if isinstance(value, str):
        cleaned = html_to_text(value)

        if cleaned:
            if label:
                texts.append(f"{label}: {cleaned}")
            else:
                texts.append(cleaned)

        return texts

    if isinstance(value, (int, float, bool)):
        useful_number_keys = {
            "min_sessions",
            "max_sessions",
        }

        if parent_key in useful_number_keys:
            texts.append(f"{label}: {value}")

        return texts

    if isinstance(value, list):
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                texts.extend(flatten_acf_value(item, parent_key))
            else:
                texts.extend(flatten_acf_value(item, f"{parent_key} {index}"))

        return texts

    if isinstance(value, dict):
        for key, item in value.items():
            if is_probably_asset_or_relation_key(key):
                continue

            texts.extend(flatten_acf_value(item, key))

        return texts

    return texts


def extract_acf_text(item: dict) -> str:
    """
    Extract readable ACF text from one WordPress REST API item.
    """
    acf = item.get("acf")

    if not isinstance(acf, dict) or not acf:
        return ""

    texts = []

    for key, value in acf.items():
        if is_probably_asset_or_relation_key(key):
            continue

        texts.extend(flatten_acf_value(value, key))

    cleaned_texts = []
    seen = set()

    for text in texts:
        text = " ".join(text.split())

        if not text:
            continue

        if text in seen:
            continue

        seen.add(text)
        cleaned_texts.append(text)

    return "\n".join(cleaned_texts)


def fetch_wp_items(post_type: str, status: str) -> list[dict]:
    """
    Fetch all WordPress REST API items for one post type and status.
    Handles pagination and logs recoverable WordPress API errors.
    """
    all_items = []
    page_number = 1

    while True:
        url = f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}"

        response = requests.get(
            url,
            auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD),
            params={
                "status": status,
                "per_page": 20,
                "page": page_number,
            },
            timeout=30,
        )

        # WordPress returns 400 when page number is out of range.
        if response.status_code == 400:
            break

        # If the REST endpoint does not exist, skip this post type.
        if response.status_code == 404:
            print(f"Skipping post type '{post_type}' because REST endpoint was not found.")
            break

        # If WordPress crashes on one page of results, log it and continue with the next group.
        if response.status_code >= 500:
            print(
                f"WordPress server error {response.status_code} for "
                f"post_type={post_type}, status={status}, page={page_number}"
            )
            print(f"URL: {response.url}")
            break

        response.raise_for_status()

        items = response.json()

        if not items:
            break

        all_items.extend(items)
        page_number += 1

    return all_items


def build_document(item: dict, post_type: str) -> dict:
    """
    Convert a WordPress REST API item into the raw document format.
    """
    wp_id = item.get("id")
    slug = item.get("slug") or ""
    link = item.get("link") or ""

    title = clean_private_title(clean_title(item.get("title", {}).get("rendered", "")))

    html = item.get("content", {}).get("rendered", "")

    main_content = html_to_text(html)
    acf_content = extract_acf_text(item)

    content_parts = []

    if main_content:
        content_parts.append(main_content)

    if acf_content:
        content_parts.append(acf_content)

    content = "\n".join(content_parts)

    return {
        "wp_id": wp_id,
        "doc_id": f"{post_type}-{slug or wp_id}",
        "url": link,
        "title": title,
        "status": item.get("status"),
        "post_type": post_type,
        "page_type": detect_page_type(link, slug, post_type),
        "content": content,
        "source": "wordpress_rest_api",
    }


def main():
    """
    Ingest private WordPress pages and CPTs into a raw JSONL file.

    This script intentionally does not do final cleaning/chunking/embedding.
    Those steps are handled by later pipeline scripts.
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # REST API bases from /wp-json/wp/v2/types.
    post_types = [
        "pages",
        "treatment",
        "concern",
    ]

    # Current project state: private pages/CPTs are the main source.
    statuses = [
        "private",
    ]

    total_saved = 0
    seen_doc_keys = set()

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for post_type in post_types:
            for status in statuses:
                print(f"Fetching post_type={post_type}, status={status}")

                items = fetch_wp_items(post_type=post_type, status=status)

                print(f"Found {len(items)} items for post_type={post_type}, status={status}")

                for item in items:
                    wp_id = item.get("id")
                    doc_key = f"{post_type}:{wp_id}"

                    if doc_key in seen_doc_keys:
                        continue

                    seen_doc_keys.add(doc_key)

                    document = build_document(item, post_type)

                    f.write(json.dumps(document, ensure_ascii=False) + "\n")
                    total_saved += 1

    print(f"Saved {total_saved} raw WordPress documents to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()