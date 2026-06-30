import os
import json
import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

WP_BASE_URL = os.getenv("WP_BASE_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

if not WP_BASE_URL or not WP_USERNAME or not WP_APP_PASSWORD:
    raise ValueError("Missing WordPress environment variables. Check your .env file.")

OUTPUT_PATH = "data/raw/wp_pages.jsonl"


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")

    # Remove whole layout sections: header, footer, nav, menus, popups, etc.
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

        # Common menu/search/footer classes
        ".menu",
        ".sub-menu",
        ".mobile-menu",
        ".site-header",
        ".site-footer",
        ".main-header",
        ".main-footer",
        ".footer",
        ".header",
        ".navbar",
        ".nav",
        ".breadcrumb",
        ".breadcrumbs",

        # Common CTA/repeated global sections
        ".cookie",
        ".cookie-banner",
        ".newsletter",
        ".subscribe",
        ".social",
        ".social-links",
    ]

    for selector in remove_selectors:
        for tag in soup.select(selector):
            tag.decompose()
    
    text = soup.get_text("\n", strip=True)

    blocked_exact_lines = {
        # "Shop",
        # "About",
        # "Treatments",
        # "Concerns",
        # "Contact",
        # "Booking",
        # "about",
        # "treatments",
        # "concerns",
        # "shop",
        # "blog",
        # "privacy policy",
        # "terms and conditions",
        # "terms of service",
        # "follow us",
        # "facebook",
        # "instagram",
        # "youtube",
        # "linkedin",
        # "skip to content",
        # "back to top",
    }

    blocked_contains = [
        "copyright",
        "all rights reserved",
        "powered by",
        "elementor",
        "wp-content",
        "wp-json",
    ]

    lines = []
    seen = set()

    for line in text.splitlines():
        line = " ".join(line.split())

        if not line:
            continue

        line_lower = line.lower()

        # Remove exact repeated UI/navigation lines.
        if line_lower in blocked_exact_lines:
            continue

        # Remove lines that contain known non-content phrases.
        if any(blocked in line_lower for blocked in blocked_contains):
            continue

        # Remove very short navigation-like fragments.
        if len(line) <= 2:
            continue

        # Remove duplicate lines inside the same page.
        if line in seen:
            continue

        seen.add(line)
        lines.append(line)

    return "\n".join(lines)


def clean_title(title_html: str) -> str:
    return BeautifulSoup(title_html or "", "html.parser").get_text(" ", strip=True)


def detect_page_type(link: str, slug: str = "", post_type: str = "") -> str:
    value = f"{link} {slug} {post_type}".lower()

    if "treatment" in value or "treatments" in value:
        return "treatment"

    if "concern" in value or "concerns" in value:
        return "concern"

    if "pricing" in value or "price" in value:
        return "pricing"

    if "faq" in value:
        return "faq"

    if "contact" in value or "book" in value:
        return "booking"

    if "blog" in value or post_type == "posts":
        return "blog"

    return "general"


def looks_like_placeholder(title: str, content: str) -> bool:
    value = f"{title}\n{content}".lower()

    placeholder_phrases = [
        "lorem ipsum",
        "coming soon",
        "placeholder",
        "test page",
        "sample page",
        "add your heading text here",
        "add your text here",
    ]

    return any(phrase in value for phrase in placeholder_phrases)


def fetch_wp_items(post_type: str, status: str) -> list[dict]:
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

        # If the endpoint does not exist, skip this post type.
        if response.status_code == 404:
            print(f"Skipping post type '{post_type}' because REST endpoint was not found.")
            break

        # If WordPress crashes on one page of results, log it and stop this post_type/status combo.
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

from collections import Counter

# Remove duplicated content across all pages
def remove_global_repeated_lines(documents: list[dict], max_page_ratio: float = 0.4) -> list[dict]:
    line_counts = Counter()

    for document in documents:
        unique_lines = set(document["content"].splitlines())

        for line in unique_lines:
            line_counts[line] += 1

    total_docs = len(documents)

    if total_docs == 0:
        return documents

    repeated_lines = {
        line
        for line, count in line_counts.items()
        if count / total_docs >= max_page_ratio
    }

    cleaned_documents = []

    for document in documents:
        cleaned_lines = []

        for line in document["content"].splitlines():
            if line in repeated_lines:
                continue

            cleaned_lines.append(line)

        document["content"] = "\n".join(cleaned_lines)
        cleaned_documents.append(document)

    print(f"Removed {len(repeated_lines)} globally repeated lines.")

    return cleaned_documents

def main():
    os.makedirs("data/raw", exist_ok=True)

    # Add your likely WordPress REST API endpoints here.
    # "pages" = normal WordPress pages
    # "posts" = normal blog posts
    # "treatment" and "concern" depend on your CPT REST settings
    post_types = [
        "pages",
        "posts",
        "treatment",
        "concern",
    ]

    statuses = [
        "private",
        "publish",
    ]

    total_saved = 0
    total_skipped_short = 0
    total_skipped_placeholder = 0
    seen_doc_keys = set()

    documents = []

    # fetch and clean documents first
    for post_type in post_types:
        for status in statuses:
            print(f"Fetching post_type={post_type}, status={status}")

            items = fetch_wp_items(post_type=post_type, status=status)

            print(f"Found {len(items)} items for post_type={post_type}, status={status}")

            for item in items:
                wp_id = item.get("id")
                slug = item.get("slug") or ""
                link = item.get("link") or ""

                doc_key = f"{post_type}:{wp_id}"

                if doc_key in seen_doc_keys:
                    continue

                seen_doc_keys.add(doc_key)

                title = clean_title(item.get("title", {}).get("rendered", ""))
                html = item.get("content", {}).get("rendered", "")
                content = html_to_text(html)

                document = {
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

                if len(document["content"]) < 100:
                    total_skipped_short += 1
                    continue

                if looks_like_placeholder(document["title"], document["content"]):
                    total_skipped_placeholder += 1
                    continue

                documents.append(document)

    # remove lines repeated across many documents
    documents = remove_global_repeated_lines(documents, max_page_ratio=0.3)

    # save final documents
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for document in documents:
            if len(document["content"]) < 100:
                total_skipped_short += 1
                continue

            f.write(json.dumps(document, ensure_ascii=False) + "\n")
            total_saved += 1
              
    print(f"Saved {total_saved} WordPress documents to {OUTPUT_PATH}")
    print(f"Skipped {total_skipped_short} short documents.")
    print(f"Skipped {total_skipped_placeholder} placeholder documents.")


if __name__ == "__main__":
    main()