import unittest
from unittest.mock import patch

from app.knowledge.recovery_kit import RECOVERY_KIT_URL
from app.schemas import ChatResponse
from app.services.rag_service import answer_question


class ProductSourceTests(unittest.TestCase):
    def answer_with_results(self, answer, results):
        with (
            patch(
                "app.services.rag_service.create_contextualized_retrieval_query",
                return_value="aftercare",
            ),
            patch("app.services.rag_service.search_chunks", return_value=results),
            patch("app.services.rag_service.generate_answer", return_value=answer),
        ):
            return ChatResponse(**answer_question("What should I use afterwards?"))

    def search_result(self, url):
        return {
            "score": 0.8,
            "chunk": {
                "chunk_id": url,
                "title": "Clinic information",
                "url": url,
                "text": "Follow your provider's aftercare instructions.",
            },
        }

    def test_product_link_is_clickable_without_product_retrieval(self):
        answer = f"Follow your provider's instructions. Shop the kit: {RECOVERY_KIT_URL}"

        response = self.answer_with_results(answer, [])

        self.assertEqual(answer, response.answer)
        self.assertEqual([RECOVERY_KIT_URL], [source.url for source in response.sources])
        self.assertIn("Skin Recovery & Glow Kit", response.sources[0].title)

    def test_product_link_is_visible_within_widget_source_limit_without_duplicates(self):
        urls = [f"https://www.vancouverlaser.com/treatment-{index}/" for index in range(4)]
        results = [self.search_result(url) for url in [*urls, RECOVERY_KIT_URL]]

        response = self.answer_with_results(f"View the kit: {RECOVERY_KIT_URL}", results)
        source_urls = [source.url for source in response.sources]

        self.assertIn(RECOVERY_KIT_URL, source_urls[:3])
        self.assertEqual(1, source_urls.count(RECOVERY_KIT_URL))
        self.assertEqual(urls, source_urls[1:])

    def test_answer_without_product_keeps_original_sources(self):
        url = "https://www.vancouverlaser.com/booking/"

        response = self.answer_with_results(
            "New customers should first book a free consultation.",
            [self.search_result(url)],
        )

        self.assertEqual([url], [source.url for source in response.sources])


if __name__ == "__main__":
    unittest.main()
