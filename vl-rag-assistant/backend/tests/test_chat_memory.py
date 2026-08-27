import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import ChatRequest
from app.services.rag_service import (
    answer_question,
    build_retrieval_query,
    create_contextualized_retrieval_query,
    generate_answer,
)


class ChatMemoryTests(unittest.TestCase):
    @patch("app.main.answer_question")
    def test_chat_endpoint_forwards_client_history(self, answer_question_mock):
        history = [
            {"role": "user", "content": "Tell me about Sofwave."},
            {"role": "assistant", "content": "What would you like to know?"},
        ]
        answer_question_mock.return_value = {
            "answer": "It depends on the treatment area.",
            "sources": [],
        }

        response = TestClient(app).post(
            "/chat",
            json={
                "message": "How much does it cost?",
                "session_id": "test-session",
                "history": history,
            },
        )

        self.assertEqual(200, response.status_code)
        answer_question_mock.assert_called_once_with(
            "How much does it cost?",
            history=history,
        )

    def test_retrieval_query_includes_recent_treatment_context(self):
        history = [
            {"role": "user", "content": "Tell me about Sofwave."},
            {"role": "assistant", "content": "Sofwave is a skin treatment."},
        ]

        query = build_retrieval_query("How much does it cost?", history)

        self.assertIn("Tell me about Sofwave.", query)
        self.assertIn("How much does it cost?", query)

    @patch("app.services.rag_service.generate_answer")
    @patch("app.services.rag_service.build_context")
    @patch("app.services.rag_service.search_chunks")
    @patch("app.services.rag_service.create_contextualized_retrieval_query")
    def test_answer_question_uses_history_for_retrieval_and_generation(
        self,
        contextualize_query_mock,
        search_chunks_mock,
        build_context_mock,
        generate_answer_mock,
    ):
        history = [
            {"role": "user", "content": "What is IPL?"},
            {"role": "assistant", "content": "It is a light-based treatment."},
        ]
        search_chunks_mock.return_value = []
        build_context_mock.return_value = ("website context", [])
        generate_answer_mock.return_value = "Follow-up answer"
        contextualize_query_mock.return_value = "IPL treatment downtime"

        result = answer_question("What is the downtime?", history)

        retrieval_query = search_chunks_mock.call_args.args[0]
        self.assertEqual("IPL treatment downtime", retrieval_query)
        generate_answer_mock.assert_called_once_with(
            "What is the downtime?",
            "website context",
            history,
        )
        self.assertEqual("Follow-up answer", result["answer"])

    def test_chat_request_rejects_more_than_sixty_history_messages(self):
        history = [
            {"role": "user", "content": f"Message {index}"}
            for index in range(61)
        ]

        with self.assertRaises(ValidationError):
            ChatRequest(message="Follow up", history=history)

    def test_chat_request_rejects_oversized_total_history(self):
        history = [
            {"role": "assistant", "content": "a" * 4000}
            for _ in range(16)
        ]

        with self.assertRaises(ValidationError):
            ChatRequest(message="Follow up", history=history)

    @patch("app.services.rag_service.client.chat.completions.create")
    def test_contextualized_retrieval_uses_older_session_context(
        self,
        create_completion_mock,
    ):
        history = [
            {"role": "user", "content": "My wedding is in three days."},
            {"role": "assistant", "content": "Understood."},
        ]
        history.extend(
            {"role": "user", "content": f"IPL follow-up {index}"}
            for index in range(8)
        )
        create_completion_mock.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="IPL suitability with a wedding in three days"
                    )
                )
            ]
        )

        query = create_contextualized_retrieval_query(
            "Would it fit my timeline?",
            history,
        )

        request_messages = create_completion_mock.call_args.kwargs["messages"]
        self.assertIn("My wedding is in three days.", request_messages[1]["content"])
        self.assertEqual(
            "IPL suitability with a wedding in three days",
            query,
        )

    @patch("app.services.rag_service.client.chat.completions.create")
    def test_generate_answer_places_history_before_current_question(
        self,
        create_completion_mock,
    ):
        history = [
            {"role": "user", "content": "Tell me about Sofwave."},
            {"role": "assistant", "content": "What would you like to know?"},
        ]
        create_completion_mock.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="It depends on the area.")
                )
            ]
        )

        answer = generate_answer(
            "How much does it cost?",
            "Sofwave pricing context",
            history,
        )

        messages = create_completion_mock.call_args.kwargs["messages"]
        self.assertEqual(history, messages[1:3])
        self.assertIn("How much does it cost?", messages[-1]["content"])
        self.assertEqual("It depends on the area.", answer)


if __name__ == "__main__":
    unittest.main()
