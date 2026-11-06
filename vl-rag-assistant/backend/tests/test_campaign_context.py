import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.rag_service import build_context
from app.services.vector_store import (
    MAX_CAMPAIGN_CHUNKS,
    MAX_CAMPAIGN_PAGES,
    expand_campaign_results,
    is_eleven_eleven_campaign,
    search_qdrant,
)


def campaign_chunk(index, **overrides):
    return {
        "chunk_id": f"event-chunk-{index}",
        "doc_id": "event",
        "url": "https://www.vancouverlaser.com/",
        "title": "11-11 Event",
        "status": "publish",
        "chunk_index": index,
        "text": "Event details",
        **overrides,
    }


def point(chunk):
    return SimpleNamespace(payload=chunk, score=0.9)


class CampaignContextTests(unittest.TestCase):
    @patch("app.services.rag_service.MAX_CONTEXT_CHARS_PER_CHUNK", 1200)
    @patch("app.services.vector_store.get_qdrant_client")
    def test_ranked_campaign_hit_supplies_missing_treatments_and_discount_tiers(
        self, get_client
    ):
        # The first chunk's treatment list begins beyond the old 1,200-char
        # cutoff; the second chunk alone does not mention BBL or public terms.
        first = campaign_chunk(
            0,
            text=(
                "Campaign introduction. " * 60
                + "Public: 25% off. Members/pass holders: 30% off. "
                "Daily Drops: 40% off for members/pass holders only. "
                "Featured treatments: BBL™ Broad Band Light, Microneedling."
            ),
        )
        second = campaign_chunk(1, text="Hair Boost, Ultherapy® Prime, Thermage® FLX")
        client = get_client.return_value
        client.query_points.return_value = SimpleNamespace(points=[point(second)])
        client.scroll.return_value = ([point(first), point(second)], None)

        results = search_qdrant([0.1], top_k=1)
        context, sources = build_context(results)

        for fact in ["BBL™ Broad Band Light", "Hair Boost", "25%", "30%", "40%"]:
            self.assertIn(fact, context)
        self.assertEqual(2, len(results))
        self.assertEqual(1, len(sources))
        self.assertEqual("S1", sources[0]["source_id"])

        filters = client.scroll.call_args.kwargs["scroll_filter"].must
        self.assertEqual("doc_id", filters[0].key)
        self.assertEqual("event", filters[0].match.value)
        self.assertEqual(["publish", "manual"], filters[1].match.any)

    @patch("app.services.vector_store.get_qdrant_client")
    def test_expansion_paginates_deduplicates_and_rejects_unpublished_content(
        self, get_client
    ):
        original = campaign_chunk(1)
        get_client.return_value.scroll.side_effect = [
            ([point(original), point(campaign_chunk(0))], "next-page"),
            ([
                point(campaign_chunk(0)),
                point(campaign_chunk(2, status="draft")),
                point(campaign_chunk(3, doc_id="unrelated")),
                point(campaign_chunk(4, status="manual")),
            ], None),
        ]

        results = expand_campaign_results([{"score": 0.9, "chunk": original}])

        self.assertEqual(
            ["event-chunk-1", "event-chunk-0", "event-chunk-4"],
            [result["chunk"]["chunk_id"] for result in results],
        )
        self.assertEqual(
            "next-page", get_client.return_value.scroll.call_args.kwargs["offset"]
        )

    @patch("app.services.vector_store.get_qdrant_client")
    def test_non_campaign_search_does_not_expand(self, get_client):
        for title in ["Membership", "Summer Savings Event", "Black Friday Offers"]:
            with self.subTest(title=title):
                results = [{"score": 0.9, "chunk": campaign_chunk(0, title=title)}]

                self.assertEqual(results, expand_campaign_results(results))
        get_client.assert_not_called()

    def test_only_eleven_eleven_content_gets_special_handling(self):
        for title in ["11-11 Event", "11/11 Savings Event"]:
            with self.subTest(title=title):
                self.assertTrue(is_eleven_eleven_campaign(campaign_chunk(0, title=title)))
        self.assertTrue(is_eleven_eleven_campaign(
            campaign_chunk(0, title="", doc_id="pages-11-11-event")
        ))
        # A new homepage campaign must not inherit this exception via its URL.
        self.assertFalse(is_eleven_eleven_campaign(
            campaign_chunk(0, title="Black Friday Offers", doc_id="black-friday")
        ))

    @patch("app.services.rag_service.MAX_CONTEXT_CHARS_PER_CHUNK", 1200)
    def test_other_pages_keep_original_context_allowance(self):
        for title in ["Membership", "Summer Savings Event", "Black Friday Offers"]:
            with self.subTest(title=title):
                chunk = campaign_chunk(0, title=title, text="a" * 1200 + "TRUNCATED")
                context, _ = build_context([{"score": 0.9, "chunk": chunk}])
                self.assertIn("a" * 1200 + "...", context)
                self.assertNotIn("TRUNCATED", context)

    @patch("app.services.vector_store.get_qdrant_client")
    def test_url_fallback_without_document_id(self, get_client):
        chunk = campaign_chunk(0, doc_id=None)
        get_client.return_value.scroll.return_value = ([], None)

        expand_campaign_results([{"score": 0.9, "chunk": chunk}])

        filters = get_client.return_value.scroll.call_args.kwargs["scroll_filter"].must
        self.assertEqual("url", filters[0].key)
        self.assertEqual(chunk["url"], filters[0].match.value)

    @patch("app.services.vector_store.get_qdrant_client")
    def test_failed_expansion_keeps_ranked_results(self, get_client):
        get_client.return_value.scroll.side_effect = RuntimeError("unavailable")
        results = [{"score": 0.9, "chunk": campaign_chunk(0)}]

        with self.assertLogs("app.services.vector_store", level="ERROR"):
            self.assertEqual(results, expand_campaign_results(results))

    @patch("app.services.vector_store.get_qdrant_client")
    def test_expansion_is_bounded_for_large_campaigns(self, get_client):
        get_client.return_value.scroll.return_value = (
            [point(campaign_chunk(index)) for index in range(MAX_CAMPAIGN_CHUNKS)],
            "more-results",
        )
        results = [{"score": 0.9, "chunk": campaign_chunk(0)}]

        expanded = expand_campaign_results(results)

        self.assertEqual(MAX_CAMPAIGN_CHUNKS, len(expanded))
        get_client.return_value.scroll.assert_called_once()

    @patch("app.services.vector_store.get_qdrant_client")
    def test_page_expansion_limit_and_original_results_are_preserved(self, get_client):
        get_client.return_value.scroll.return_value = ([], None)
        results = [
            {"score": 0.9, "chunk": campaign_chunk(i, doc_id=f"event-{i}")}
            for i in range(MAX_CAMPAIGN_PAGES + 1)
        ]

        self.assertEqual(results, expand_campaign_results(results))
        self.assertEqual(MAX_CAMPAIGN_PAGES, get_client.return_value.scroll.call_count)


if __name__ == "__main__":
    unittest.main()
