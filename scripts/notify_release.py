#!/usr/bin/env python3
"""Notify Discord when a new release is published on the watched repo."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = os.environ.get("WATCH_REPO", "openai/codex")
STATE_FILE = Path(os.environ.get("STATE_FILE", "state/last_release.txt"))
DISCORD_BODY_LIMIT = 1800
RETRY_STATUS = {429, 500, 502, 503, 504}


def _urlopen_with_retry(req, retries: int = 2, backoff: float = 1.0):
    """指数バックオフ付きで urlopen。一過性 (429/5xx/network) のみ retry"""
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise


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
    with _urlopen_with_retry(req) as resp:
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
        headers={
            "Content-Type": "application/json",
            # Cloudflare がデフォルト Python-urllib UA を error 1010 で弾くため明示
            "User-Agent": "codex-update-watcher",
        },
        method="POST",
    )
    try:
        with _urlopen_with_retry(req) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        # URL本体は出力しない。長さと先頭スキームのみで secret 破損を判定する
        print(
            f"Discord rejected: HTTP {e.code} body={err_body}",
            file=sys.stderr,
        )
        print(
            f"webhook_len={len(webhook)} starts_https={webhook.startswith('https://')}",
            file=sys.stderr,
        )
        raise


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
