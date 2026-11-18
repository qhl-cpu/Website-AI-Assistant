import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache
from time import monotonic
from urllib.parse import urlsplit

from app.services.vector_store import iter_published_page_chunks


logger = logging.getLogger(__name__)
PAGE_INDEX_CACHE_SECONDS = 300
SITE_HOSTS = {"vancouverlaser.com", "www.vancouverlaser.com", "shop.vancouverlaser.com"}
PAGE_NAME = re.compile(r"^Treatment Or Concern Name:[ \t]*(.+)$", re.IGNORECASE | re.MULTILINE)
BRAND_VARIANT_SEPARATOR = re.compile(r"(?<=[®™])\s*/")
NAME_WORD = re.compile(r"[^\W_]+")
NAME_SEPARATOR = r"[ \t®™&+/’'\-‐‑–—]+"
URL_PATTERN = r"(?:https?://|www\.)[^\s<>()]+"


def is_site_url(url: str) -> bool:
    """Check whether a URL is eligible for an inline website link.

    Args:
        url: URL string to parse. Callers must supply a string.

    Returns:
        True for HTTPS URLs whose exact host is in SITE_HOSTS. Returns False
        for other hosts, schemes, or URLs that raise a parsing ValueError.

    Notes:
        Checks the URL locally. Page availability comes from the published
        index and is not verified with an HTTP request.
    """
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and parsed.netloc.lower() in SITE_HOSTS
    except ValueError:
        return False


def name_key(name: str) -> str:
    """Normalize a page name for case-insensitive lookup.

    Args:
        name: Page title or alias supplied as a string.

    Returns:
        Lowercase Unicode letters and numbers joined by single spaces.
        Punctuation and trademark symbols act as separators. An input with
        no letters or numbers produces an empty string.
    """
    return " ".join(NAME_WORD.findall(name.lower()))


def build_page_link_index(chunks: Iterable[dict]) -> dict[str, str]:
    """Build an unambiguous lookup from published page names to their URLs.

    Args:
        chunks: Iterable of indexed chunk dictionaries. Expected fields are
            status, url, title, section_type, and text. Present textual fields
            must contain strings. Missing fields are treated as empty values.

    Returns:
        Normalized titles and aliases mapped to allowed HTTPS URLs. Official
        titles take precedence over aliases. Names with multiple remaining
        destinations are excluded. About and Home require explicit page names.

    Notes:
        Consumes the iterable, including generators. Overview labels and
        trademarked slash variants provide aliases. Errors from the iterable
        propagate to the caller, allowing the loader to discard partial reads.
    """
    titles = defaultdict(set)
    aliases = defaultdict(set)

    for chunk in chunks:
        url = chunk.get("url") or ""
        if chunk.get("status") != "publish" or not is_site_url(url):
            continue

        raw_title = chunk.get("title") or ""
        title = name_key(raw_title)
        if not title:
            continue
        # These titles are also ordinary words. Require an explicit page reference.
        if title in {"about", "home"}:
            titles[f"{title} page"].add(url)
            if title == "about":
                titles["about us"].add(url)
        else:
            titles[title].add(url)

        # A title like Ultherapy® /Prime also names the base treatment.
        brand = name_key(BRAND_VARIANT_SEPARATOR.split(raw_title, maxsplit=1)[0])
        if brand != title:
            aliases[brand].add(url)

        if chunk.get("section_type") == "overview":
            for name in PAGE_NAME.findall(chunk.get("text") or ""):
                alias = name_key(name)
                if alias:
                    aliases[alias].add(url)

    # A page title takes precedence over an alias. For example, Excessive
    # Sweating is a concern page and also an alias for its treatment page.
    aliases.update(titles)
    return {name: next(iter(urls)) for name, urls in aliases.items() if len(urls) == 1}


@lru_cache(maxsize=1)
def load_page_link_index(_refresh_window: int) -> dict[str, str]:
    """Load and cache the published page lookup for a caller-selected window.

    Args:
        _refresh_window: Integer cache key, normally monotonic time divided
            by PAGE_INDEX_CACHE_SECONDS. Its value controls cache refreshes.

    Returns:
        The cached name-to-URL dictionary, or an empty dictionary after a
        loading failure. Callers must treat the cached dictionary as read-only.

    Notes:
        Requires configured Qdrant access on a cache miss. Reads the collection
        synchronously and retains one window per process. Loading failures are
        logged and their empty result is cached for the current window too.
    """
    try:
        return build_page_link_index(iter_published_page_chunks())
    except Exception:
        logger.exception("Could not load the published page index for inline links")
        return {}


def find_inline_links(answer: str, retrieved_chunks: Iterable[dict]) -> list[dict]:
    """Locate recognized page names in a finished assistant answer.

    Args:
        answer: Original answer string whose positions the frontend will use.
        retrieved_chunks: Indexed chunks for the current question, used as a
            fallback when the full published lookup is empty. Chunks must meet
            build_page_link_index's field requirements.

    Returns:
        Non-overlapping link dictionaries in answer order. Each contains a
        start-inclusive and end-exclusive Unicode code point range plus its
        URL. Longer names win at the same position. Matching ignores case,
        tolerates supported separators, and skips names inside raw URLs.
        Returns an empty list when no eligible names match.

    Notes:
        May trigger a cached Qdrant catalog read. The answer is kept intact so
        the frontend must use the same text and Unicode code point offsets.
    """
    urls = load_page_link_index(int(monotonic() // PAGE_INDEX_CACHE_SECONDS))
    if not urls:
        urls = build_page_link_index(retrieved_chunks)
    if not urls:
        return []

    # Longer names win over shorter names at the same position (Acne Scars vs. Acne).
    names = "|".join(
        NAME_SEPARATOR.join(re.escape(word) for word in name.split())
        for name in sorted(urls, key=len, reverse=True)
    )
    matches = re.finditer(
        rf"(?P<url>{URL_PATTERN})|(?<!\w)(?:{names})[®™]*(?!\w)",
        answer,
        re.IGNORECASE,
    )
    links = []
    for match in matches:
        if match.group("url"):
            continue
        url = urls.get(name_key(match.group()))
        if url:
            links.append({"start": match.start(), "end": match.end(), "url": url})
    return links
