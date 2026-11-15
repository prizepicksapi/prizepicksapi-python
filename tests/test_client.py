import json
import os
import sys
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from prizepicksapi import APIError, PrizePicksAPI, RateLimitError  # noqa: E402


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, timeout):
        self.calls.append((method, url, headers))
        status, body, headers_out = self.responses.pop(0)
        raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        return status, headers_out, raw


def page(rows, cursor=None):
    return {"data": rows, "meta": {"next_cursor": cursor}}


class ClientTests(unittest.TestCase):
    def test_demo_needs_no_key(self):
        t = FakeTransport([(200, page([{"id": "demo_nba_001"}]), {})])
        api = PrizePicksAPI(api_key="", transport=t)
        out = api.demo_projections(league="NBA", limit=2)
        self.assertEqual(out["data"][0]["id"], "demo_nba_001")
        _, url, headers = t.calls[0]
        self.assertNotIn("Authorization", headers)
        self.assertEqual(urlparse(url).path, "/api/v1/demo/projections")
        self.assertEqual(parse_qs(urlparse(url).query), {"league": ["NBA"], "limit": ["2"]})

    def test_live_sends_bearer_and_user_request(self):
        t = FakeTransport([(200, page([]), {})])
        api = PrizePicksAPI(api_key="pk_test", user_request="NBA dashboard check", transport=t)
        api.projections(league=["NBA", "NFL"], view="compact", tier=None)
        _, url, headers = t.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer pk_test")
        self.assertEqual(headers["X-User-Request"], "NBA dashboard check")
        self.assertEqual(parse_qs(urlparse(url).query), {"league": ["NBA,NFL"], "view": ["compact"]})

    def test_missing_key_raises_before_request(self):
        t = FakeTransport([])
        api = PrizePicksAPI(api_key="", transport=t)
        with self.assertRaises(APIError) as ctx:
            api.projections()
        self.assertEqual(ctx.exception.code, "INVALID_API_KEY")
        self.assertEqual(t.calls, [])

    def test_paginate_follows_cursor_and_keeps_filters(self):
        t = FakeTransport([(200, page([{"id": 1}, {"id": 2}], "c1"), {}), (200, page([{"id": 3}]), {})])
        api = PrizePicksAPI(api_key="k", transport=t)
        rows = list(api.iter_projections(league="NBA", limit=2))
        self.assertEqual([r["id"] for r in rows], [1, 2, 3])
        q2 = parse_qs(urlparse(t.calls[1][1]).query)
        self.assertEqual(q2, {"league": ["NBA"], "limit": ["2"], "cursor": ["c1"]})

    def test_api_error_code(self):
        body = {"error": {"code": "INVALID_API_KEY", "message": "Provide a valid API key"}}
        t = FakeTransport([(401, body, {})])
        api = PrizePicksAPI(api_key="bad", transport=t)
        with self.assertRaises(APIError) as ctx:
            api.coverage()
        self.assertEqual((ctx.exception.status, ctx.exception.code), (401, "INVALID_API_KEY"))

    def test_per_minute_429_is_retried_with_retry_after(self):
        slept = []
        limited = {"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "slow down"}}
        t = FakeTransport([(429, limited, {"Retry-After": "7"}), (200, page([]), {})])
        api = PrizePicksAPI(api_key="k", transport=t, sleep=slept.append)
        api.changes(league="NBA")
        self.assertEqual(slept, [7.0])
        self.assertEqual(len(t.calls), 2)

    def test_monthly_quota_is_not_retried(self):
        quota = {"error": {"code": "MONTHLY_QUOTA_EXCEEDED", "message": "monthly limit"}}
        t = FakeTransport([(429, quota, {"Retry-After": "60"})])
        api = PrizePicksAPI(api_key="k", transport=t, sleep=lambda s: None)
        with self.assertRaises(RateLimitError):
            api.projections()
        self.assertEqual(len(t.calls), 1)

    def test_history_path_is_encoded(self):
        t = FakeTransport([(200, page([]), {})])
        PrizePicksAPI(api_key="k", transport=t).history("abc/1")
        self.assertTrue(t.calls[0][1].startswith("https://prizepicksapi.com/api/v1/projections/abc%2F1/history"))

    def test_export_returns_csv_text(self):
        t = FakeTransport([(200, "id,player\n1,A\n", {})])
        csv = PrizePicksAPI(api_key="", transport=t).demo_export_csv(league="NBA", limit=1)
        self.assertTrue(csv.startswith("id,player"))
        self.assertEqual(t.calls[0][2]["Accept"], "text/csv")


@unittest.skipUnless(os.environ.get("PRIZEPICKS_LIVE_TEST"), "set PRIZEPICKS_LIVE_TEST=1 to call the keyless demo endpoint")
class LiveDemoTest(unittest.TestCase):
    def test_demo_projections_live(self):
        out = PrizePicksAPI(api_key="").demo_projections(league="NBA", limit=2)
        self.assertTrue(out["meta"]["is_demo"])
        self.assertEqual(len(out["data"]), 2)


if __name__ == "__main__":
    unittest.main()
