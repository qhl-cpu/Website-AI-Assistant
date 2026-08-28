import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.rate_limiter import (
    InMemorySlidingWindowRateLimiter,
    RateLimitRule,
)


class RateLimiterTests(unittest.TestCase):
    def test_visitor_burst_limit_and_retry_time(self):
        limiter = InMemorySlidingWindowRateLimiter(
            visitor_rules=(RateLimitRule("burst", 3, 30),),
            ip_rules=(),
        )

        self.assertTrue(limiter.check("visitor", "ip", now=0).allowed)
        self.assertTrue(limiter.check("visitor", "ip", now=1).allowed)
        self.assertTrue(limiter.check("visitor", "ip", now=2).allowed)

        blocked = limiter.check("visitor", "ip", now=3)

        self.assertFalse(blocked.allowed)
        self.assertEqual("visitor_burst", blocked.rule_name)
        self.assertEqual(27, blocked.retry_after_seconds)
        self.assertTrue(limiter.check("visitor", "ip", now=30).allowed)

    def test_ip_limit_aggregates_different_visitors(self):
        limiter = InMemorySlidingWindowRateLimiter(
            visitor_rules=(RateLimitRule("burst", 10, 30),),
            ip_rules=(RateLimitRule("sustained", 2, 10),),
        )

        self.assertTrue(limiter.check("visitor-1", "shared-ip", now=0).allowed)
        self.assertTrue(limiter.check("visitor-2", "shared-ip", now=0).allowed)

        blocked = limiter.check("visitor-3", "shared-ip", now=1)

        self.assertFalse(blocked.allowed)
        self.assertEqual("ip_sustained", blocked.rule_name)
        self.assertEqual(9, blocked.retry_after_seconds)

    @patch("app.main.answer_question")
    def test_chat_endpoint_returns_structured_429_without_model_call(
        self,
        answer_question_mock,
    ):
        answer_question_mock.return_value = {
            "answer": "Clinic answer",
            "sources": [],
        }
        limiter = InMemorySlidingWindowRateLimiter(
            visitor_rules=(RateLimitRule("burst", 1, 30),),
            ip_rules=(),
        )

        with patch("app.main.chat_rate_limiter", limiter):
            client = TestClient(app)
            payload = {
                "message": "What treatments do you offer?",
                "session_id": "rate-limit-test",
                "history": [],
            }

            first_response = client.post("/chat", json=payload)
            blocked_response = client.post("/chat", json=payload)

        self.assertEqual(200, first_response.status_code)
        self.assertEqual(429, blocked_response.status_code)
        self.assertEqual("30", blocked_response.headers["Retry-After"])
        self.assertEqual(30, blocked_response.json()["retry_after_seconds"])
        self.assertIn("little quickly", blocked_response.json()["detail"])
        answer_question_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
