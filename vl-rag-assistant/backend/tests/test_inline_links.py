import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.site_links import find_inline_links, load_page_link_index


def page(title, path, **overrides):
    """Build a published website chunk fixture with optional field overrides.

    Args:
        title: Page name used by the matching code.
        path: Website path without leading or trailing slashes.
        **overrides: Fields to add or replace, including title, status, or URL.

    Returns:
        A fresh chunk dictionary for a test. No external services are called.
    """
    return {
        "title": title,
        "url": f"https://www.vancouverlaser.com/{path}/",
        "status": "publish",
        **overrides,
    }


class InlineLinkTests(unittest.TestCase):
    def setUp(self):
        """Clear the page lookup cache before and after each test.

        Notes:
            Runs under unittest and registers cleanup even when a test fails,
            preventing mocked catalogs from leaking into subsequent tests.
        """
        load_page_link_index.cache_clear()
        self.addCleanup(load_page_link_index.cache_clear)

    def test_chat_links_published_mentions_even_when_their_pages_are_not_sources(self):
        """Verify inline link selection through the chat endpoint.

        Notes:
            Mocks retrieval, model output, and a paginated page catalog. Checks
            Unicode offsets, overlapping names, aliases, domain restrictions,
            published status, and preservation of the answer and its sources.
            Assertion failures report regressions without external API calls.
        """
        campaign = page("Spring Event", "spring-event")
        acne = page("Acne", "conditions/acne")
        scars = page("Acne Scars", "conditions/acne-scars")
        sofwave = page("Sofwave™", "treatments/sofwave")
        membership = page("Membership", "membership")
        ultherapy = page(
            "Ultherapy® /Prime",
            "treatments/ultherapy-prime",
            section_type="overview",
            text="Treatment Or Concern Name: Ultherapy® Prime",
        )
        onda_pro = page(
            "Onda Pro",
            "treatments/onda-pro",
            section_type="overview",
            text="Treatment Or Concern Name: Onda Pro Face & Body Contouring",
        )
        answer = (
            "💡 Sofwave™, Ultherapy, and Onda Pro Face & Body Contouring.\n"
            "Read about Acne Scars and acne. "
            "See Membership or https://example.com/acne. Ignore xAcne, Draft Page, and External Page."
        )
        remaining_pages = [
            ultherapy,
            onda_pro,
            membership,
            page("Draft Page", "draft", status="draft"),
            page("External Page", "external", url="https://vancouverlaser.com.example.org/"),
        ]

        with (
            patch("app.services.vector_store.get_qdrant_client") as get_client,
            patch("app.services.rag_service.search_chunks", return_value=[{"chunk": campaign, "score": 0.8}]),
            patch("app.services.rag_service.generate_answer", return_value=answer),
        ):
            client = get_client.return_value
            client.scroll.side_effect = [
                ([], None),  # No managed revisions.
                ([SimpleNamespace(payload=item) for item in [acne, scars, sofwave]], "next"),
                ([SimpleNamespace(payload=item) for item in remaining_pages], None),
            ]
            response = TestClient(app).post("/chat", json={"message": "What else is on the site?"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], answer)
        self.assertEqual([source["url"] for source in data["sources"]], [campaign["url"]])
        self.assertEqual(
            [(answer[link["start"]:link["end"]], link["url"]) for link in data["inline_links"]],
            [
                ("Sofwave™", sofwave["url"]),
                ("Ultherapy", ultherapy["url"]),
                ("Onda Pro Face & Body Contouring", onda_pro["url"]),
                ("Acne Scars", scars["url"]),
                ("acne", acne["url"]),
                ("Membership", membership["url"]),
            ],
        )
        self.assertEqual(client.scroll.call_args.kwargs["offset"], "next")

    def test_catalog_failure_still_links_published_retrieved_pages(self):
        """Verify retrieved published pages supply links after a catalog timeout.

        Notes:
            Requires a clean lookup cache supplied by setUp(). Forces a mocked
            timeout and checks both error logging and the fallback link range.
        """
        treatment = page("Botox®", "treatments/botox")
        with (
            patch("app.services.site_links.iter_published_page_chunks", side_effect=TimeoutError),
            self.assertLogs("app.services.site_links", level="ERROR"),
        ):
            self.assertEqual(
                find_inline_links("Botox", [treatment]),
                [{"start": 0, "end": 5, "url": treatment["url"]}],
            )
