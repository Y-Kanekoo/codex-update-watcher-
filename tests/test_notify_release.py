"""notify_release.py の主要ロジックの unittest"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
