#!/usr/bin/env python3
"""Notify Discord when a new release is published on the watched repo."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = os.environ.get("WATCH_REPO", "openai/codex")
STATE_FILE = Path(os.environ.get("STATE_FILE", "state/last_release.txt"))
DISCORD_BODY_LIMIT = 1800


def fetch_latest_release() -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "codex-update-watcher",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def post_discord(webhook: str, release: dict) -> None:
    body = (release.get("body") or "(release notes なし)").strip()
    if len(body) > DISCORD_BODY_LIMIT:
        body = body[:DISCORD_BODY_LIMIT] + "\n... (truncated)"
    payload = {
        "embeds": [
            {
                "title": f"{REPO} {release['tag_name']} がリリースされました",
                "url": release["html_url"],
                "description": body,
            }
        ]
    }
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        resp.read()


def main() -> int:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        return 1

    try:
        release = fetch_latest_release()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"{REPO} has no releases yet")
            return 0
        raise

    tag = release["tag_name"]
    last = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not last:
        STATE_FILE.write_text(tag + "\n")
        print(f"Initialized state without notifying: {tag}")
        return 0

    if tag == last:
        print(f"No new release (current: {tag})")
        return 0

    post_discord(webhook, release)
    STATE_FILE.write_text(tag + "\n")
    print(f"Notified: {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
