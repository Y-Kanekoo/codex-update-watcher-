"""notify_release.py の主要ロジックの unittest"""
from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import notify_release  # noqa: E402


def _release(tag: str, body: str = "notes", published_at: str | None = "2026-01-01T00:00:00Z") -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://example.com/r/{tag}",
        "body": body,
        "published_at": published_at,
    }


class BuildPayloadTests(unittest.TestCase):
    def test_basic_shape(self):
        payload = notify_release.build_payload(_release("v1.0.0", body="hello"))
        self.assertEqual(len(payload["embeds"]), 1)
        embed = payload["embeds"][0]
        self.assertIn("v1.0.0", embed["title"])
        self.assertEqual(embed["url"], "https://example.com/r/v1.0.0")
        self.assertEqual(embed["description"], "hello")
        self.assertEqual(embed["color"], 0x4F46E5)
        self.assertEqual(embed["footer"], {"text": "codex-update-watcher"})
        self.assertEqual(embed["timestamp"], "2026-01-01T00:00:00Z")

    def test_truncates_long_body(self):
        long_body = "x" * (notify_release.DISCORD_BODY_LIMIT + 500)
        payload = notify_release.build_payload(_release("v1", body=long_body))
        desc = payload["embeds"][0]["description"]
        self.assertTrue(desc.endswith("(truncated)"))
        # 切り詰め前の本文長 + 注記分のみ
        self.assertLessEqual(len(desc), notify_release.DISCORD_BODY_LIMIT + 30)

    def test_default_body_when_none(self):
        payload = notify_release.build_payload(_release("v1", body=None))
        self.assertEqual(payload["embeds"][0]["description"], "(release notes なし)")

    def test_omits_timestamp_when_published_at_missing(self):
        payload = notify_release.build_payload(_release("v1", published_at=None))
        self.assertNotIn("timestamp", payload["embeds"][0])


class SelectUnnotifiedTests(unittest.TestCase):
    def test_returns_newer_releases_in_newest_first_order(self):
        releases = [_release("v3"), _release("v2"), _release("v1")]
        result = notify_release.select_unnotified(releases, last_tag="v1")
        self.assertEqual([r["tag_name"] for r in result], ["v3", "v2"])

    def test_empty_when_last_is_newest(self):
        releases = [_release("v3"), _release("v2"), _release("v1")]
        result = notify_release.select_unnotified(releases, last_tag="v3")
        self.assertEqual(result, [])

    def test_caps_to_one_when_last_not_found(self):
        releases = [_release("v3"), _release("v2"), _release("v1")]
        result = notify_release.select_unnotified(releases, last_tag="v0_old")
        self.assertEqual([r["tag_name"] for r in result], ["v3"])

    def test_empty_when_releases_empty(self):
        result = notify_release.select_unnotified([], last_tag="v0")
        self.assertEqual(result, [])


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.com", code=code, msg="x", hdrs=None, fp=None
    )


class UrlopenWithRetryTests(unittest.TestCase):
    def setUp(self):
        # sleep を mock してテストを高速化
        self._sleep_patcher = patch.object(notify_release.time, "sleep")
        self.mock_sleep = self._sleep_patcher.start()

    def tearDown(self):
        self._sleep_patcher.stop()

    def test_succeeds_on_first_attempt(self):
        with patch.object(notify_release.urllib.request, "urlopen", return_value="ok") as mock:
            result = notify_release._urlopen_with_retry("req", retries=2)
        self.assertEqual(result, "ok")
        self.assertEqual(mock.call_count, 1)
        self.mock_sleep.assert_not_called()

    def test_retries_on_503_then_succeeds(self):
        side_effects = [_http_error(503), "ok"]
        with patch.object(notify_release.urllib.request, "urlopen", side_effect=side_effects) as mock:
            result = notify_release._urlopen_with_retry("req", retries=2, backoff=1.0)
        self.assertEqual(result, "ok")
        self.assertEqual(mock.call_count, 2)
        self.mock_sleep.assert_called_once_with(1.0)

    def test_does_not_retry_on_404(self):
        with patch.object(notify_release.urllib.request, "urlopen", side_effect=_http_error(404)) as mock:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                notify_release._urlopen_with_retry("req", retries=2)
        self.assertEqual(ctx.exception.code, 404)
        self.assertEqual(mock.call_count, 1)
        self.mock_sleep.assert_not_called()

    def test_retries_exhausted_raises_last_error(self):
        with patch.object(notify_release.urllib.request, "urlopen", side_effect=_http_error(500)) as mock:
            with self.assertRaises(urllib.error.HTTPError):
                notify_release._urlopen_with_retry("req", retries=2, backoff=1.0)
        self.assertEqual(mock.call_count, 3)
        # backoff = 1.0 * 2**0, 1.0 * 2**1
        self.assertEqual(self.mock_sleep.call_args_list[0].args, (1.0,))
        self.assertEqual(self.mock_sleep.call_args_list[1].args, (2.0,))

    def test_retries_on_url_error(self):
        side_effects = [urllib.error.URLError("netfail"), urllib.error.URLError("netfail"), "ok"]
        with patch.object(notify_release.urllib.request, "urlopen", side_effect=side_effects) as mock:
            result = notify_release._urlopen_with_retry("req", retries=2, backoff=0.5)
        self.assertEqual(result, "ok")
        self.assertEqual(mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
