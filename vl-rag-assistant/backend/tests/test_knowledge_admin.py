import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from qdrant_client import QdrantClient, models

from app.admin import knowledge as admin
from app.knowledge import index
from app.knowledge.managed_content import ContentError, download, read_file
from app.main import app
from app.services import knowledge_service as service, vector_store


class KnowledgeAdminTests(unittest.TestCase):
    def setUp(self):
        self.store = QdrantClient(":memory:")
        self.addCleanup(self.store.close)
        for module in (service, vector_store, index):
            patcher = patch.object(module, "QDRANT_COLLECTION_NAME", "knowledge-test")
            patcher.start()
            self.addCleanup(patcher.stop)
        self.store.create_collection(
            collection_name="knowledge-test",
            vectors_config=models.VectorParams(size=service.DIMENSIONS, distance=models.Distance.COSINE),
        )
        self.vector = [1.0] + [0.0] * (service.DIMENSIONS - 1)
        patches = [
            patch.object(admin, "KNOWLEDGE_ADMIN_TOKEN", "local-testing-token"),
            patch.object(admin, "get_qdrant_client", return_value=self.store),
            patch.object(vector_store, "get_qdrant_client", return_value=self.store),
            patch("app.knowledge.managed_content.get_encoding", return_value=TestEncoding()),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        embedding = patch.object(service.openai_client.embeddings, "create", side_effect=self.embedding_response)
        self.embedding_api = embedding.start()
        self.addCleanup(embedding.stop)
        self.http = TestClient(app, headers={"Authorization": "Bearer local-testing-token"})
        self.addCleanup(self.http.close)
        self.url = "https://www.vancouverlaser.com/example/"
        self.page_id = self.seed_page(100, self.url, "Original page", count=2)
        self.other_id = self.seed_page(101, self.url, "Another page sharing a URL")

    def embedding_response(self, *, model, input):
        return SimpleNamespace(data=[
            SimpleNamespace(index=index, embedding=self.vector) for index, _ in enumerate(input)
        ])

    def seed_page(self, wp_id, url, title, count=1):
        payload = {
            "wp_id": wp_id, "doc_id": f"pages-{wp_id}", "title": title, "url": url,
            "status": "publish", "post_type": "pages", "source": "wordpress_rest_api",
            "section_type": "overview", "text": f"Original text for {title}.",
        }
        self.store.upsert("knowledge-test", [
            models.PointStruct(
                id=str(uuid4()), vector=self.vector,
                payload={**payload, "chunk_index": i, "chunk_id": f"{wp_id}-{i}"},
            ) for i in range(count)
        ])
        return service.source_id(payload)

    def page_document(self, wp_id=100):
        return {
            "wp_id": wp_id, "doc_id": f"pages-{wp_id}", "title": "Updated page",
            "url": self.url, "status": "publish", "post_type": "pages", "page_type": "page",
            "source": "wordpress_rest_api",
            "content": "New website details with enough words to preserve the complete paragraph.",
        }

    def get_sources(self):
        response = self.http.get("/admin/knowledge/sources")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["sources"]

    def retrieve(self):
        return [entry["chunk"] for entry in vector_store.search_qdrant(self.vector, top_k=20)]

    def test_selective_page_update_reembeds_the_source_and_removes_old_chunks(self):
        source_ids = {row["id"] for row in self.get_sources()}
        self.assertEqual(source_ids, {self.page_id, self.other_id})
        path = f"/admin/knowledge/sources/{self.page_id}/refresh"
        with patch.object(service, "read_page", side_effect=lambda *a, **kw: self.page_document()) as fetch:
            self.assertEqual(self.http.post(path).status_code, 200)
            self.assertEqual(self.http.post(path).status_code, 200)
        self.assertEqual(fetch.call_count, 2)
        fetch.assert_called_with(self.url, wp_id=100, post_type="pages")
        self.assertEqual(self.embedding_api.call_count, 2)
        self.assertEqual(len(self.embedding_api.call_args.kwargs["input"]), 1)
        self.assertCountEqual([entry["title"] for entry in self.retrieve()], [
            "Updated page", "Another page sharing a URL",
        ])
        points, _ = self.store.scroll("knowledge-test", limit=100)
        self.assertEqual(len(points), 3)  # The two live chunks and the source record.
        self.assertEqual(self.http.delete(f"/admin/knowledge/sources/{self.page_id}").status_code, 200)
        self.assertEqual([entry["wp_id"] for entry in self.retrieve()], [101])
        self.assertEqual(self.embedding_api.call_count, 2)

    def test_add_by_url_matches_the_wordpress_identity(self):
        with patch.object(service, "read_page", return_value=self.page_document(102)) as fetch:
            response = self.http.post("/admin/knowledge/pages", json={"url": self.url + "?utm=demo"})
        self.assertEqual(response.status_code, 200, response.text)
        fetch.assert_called_once_with(self.url)
        self.assertEqual({entry["wp_id"] for entry in self.retrieve()}, {100, 101, 102})

    def test_failed_publication_leaves_previous_chunks_visible(self):
        with (
            patch.object(service, "read_page", return_value=self.page_document()),
            patch.object(service, "write_record", side_effect=RuntimeError("write failed")),
            self.assertLogs("app.admin.knowledge", level="ERROR"),
        ):
            response = self.http.post(f"/admin/knowledge/sources/{self.page_id}/refresh")
        self.assertEqual(response.status_code, 502)
        self.assertCountEqual([entry["title"] for entry in self.retrieve()], [
            "Original page", "Original page", "Another page sharing a URL",
        ])
        self.assertNotIn("Updated page", [chunk["title"] for chunk in vector_store.iter_published_page_chunks()])

    def test_upload_replace_and_remove_use_the_same_record(self):
        headers = {"X-Knowledge-Filename": "policy.txt", "X-Knowledge-Public": "yes"}
        response = self.http.post("/admin/knowledge/files", headers=headers, content=b"Original file")
        self.assertEqual(response.status_code, 200, response.text)
        [original] = [row for row in self.get_sources() if row["kind"] == "file"]
        path = f"/admin/knowledge/files?key={original['id']}"
        headers["X-Knowledge-Filename"] = "new-policy.md"
        response = self.http.post(path, headers=headers, content=b"Updated file")
        self.assertEqual(response.status_code, 200, response.text)
        [replacement] = [row for row in self.get_sources() if row["kind"] == "file"]
        self.assertEqual(replacement["id"], original["id"])
        self.assertEqual(replacement["title"], "new-policy.md")
        self.assertEqual([chunk["text"] for chunk in self.retrieve() if chunk["status"] == "manual"], ["Updated file"])
        self.assertEqual(self.http.delete(f"/admin/knowledge/sources/{original['id']}").status_code, 200)
        self.assertFalse([chunk for chunk in self.retrieve() if chunk["status"] == "manual"])
        self.assertEqual(self.embedding_api.call_count, 2)

    def test_admin_and_upload_require_explicit_access(self):
        with TestClient(app) as anonymous:
            self.assertEqual(anonymous.get("/admin/knowledge/sources").status_code, 401)
            page = anonymous.get("/admin/knowledge")
            self.assertEqual(page.status_code, 200)
            self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        self.assertEqual(self.http.post("/admin/knowledge/files", content=b"private file").status_code, 422)
        with patch.object(admin, "KNOWLEDGE_ADMIN_TOKEN", ""):
            self.assertEqual(self.http.get("/admin/knowledge").status_code, 404)
        self.embedding_api.assert_not_called()

    def test_strict_collection_can_be_previewed_before_index_setup(self):
        strict = models.StrictModeConfig(enabled=True, unindexed_filtering_retrieve=False)
        info = self.store.get_collection("knowledge-test")
        info.config.strict_mode_config = strict
        real_scroll = self.store.scroll

        def strict_scroll(*args, **kwargs):
            if kwargs.get("scroll_filter") is not None:
                raise AssertionError("A collection without indexes rejects payload filters")
            return real_scroll(*args, **kwargs)

        with (
            patch.object(self.store, "get_collection", return_value=info),
            patch.object(self.store, "scroll", side_effect=strict_scroll),
        ):
            self.assertEqual(len(self.get_sources()), 2)
            response = self.http.post(
                "/admin/knowledge/files",
                headers={"X-Knowledge-Filename": "policy.txt", "X-Knowledge-Public": "yes"},
                content=b"Public policy",
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("knowledge_record", response.json()["detail"])
        self.embedding_api.assert_not_called()

    def test_document_formats_and_scanned_pdf_failure(self):
        word = Document()
        word.add_paragraph("First paragraph")
        word.add_table(rows=1, cols=1).cell(0, 0).text = "Table policy"
        data = BytesIO()
        word.save(data)
        self.assertIn("Table policy", read_file("policy.docx", data.getvalue())["content"])

        data = BytesIO()
        pdf = PdfWriter()
        pdf.add_blank_page(100, 100)
        pdf.write(data)
        with self.assertRaisesRegex(ContentError, "OCR"):
            read_file("scanned.pdf", data.getvalue())

    def test_webpage_redirect_stays_within_clinic_hosts(self):
        visited = []

        def redirect(request):
            visited.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://example.com/unapproved"})

        with httpx.Client(transport=httpx.MockTransport(redirect)) as client:
            with self.assertRaises(ContentError):
                download(client, self.url)
        self.assertEqual(visited, [self.url])


class TestEncoding:
    """An in-memory tokenizer for short fixture text."""

    @staticmethod
    def encode_ordinary(text):
        return text.split()
