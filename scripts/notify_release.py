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
RELEASES_PER_PAGE = 20
# state より古い tag が見つからない場合の暴発防止上限
CATCH_UP_CAP = 5


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


def fetch_releases(per_page: int = RELEASES_PER_PAGE) -> list[dict]:
    """新しい順に release 一覧を取得。draft / prerelease は除外"""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases?per_page={per_page}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "codex-update-watcher",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())
    return [r for r in data if not r.get("draft") and not r.get("prerelease")]


def select_unnotified(releases: list[dict], last_tag: str) -> list[dict]:
    """last_tag より新しい release を新しい順で返す。
    last_tag が見つからない場合は最新 1件のみに絞り、暴発を防ぐ。
    """
    new_releases: list[dict] = []
    for r in releases:
        if r["tag_name"] == last_tag:
            return new_releases
        new_releases.append(r)
    # last_tag が範囲外（page から漏れている）→ 最新 1 件のみ
    if new_releases:
        print(
            f"warning: {last_tag} が直近 {len(releases)} 件に見つからず。最新のみ通知",
            file=sys.stderr,
        )
        return new_releases[:1]
    return []


def build_payload(release: dict) -> dict:
    body = (release.get("body") or "(release notes なし)").strip()
    if len(body) > DISCORD_BODY_LIMIT:
        body = body[:DISCORD_BODY_LIMIT] + "\n... (truncated)"
    embed: dict = {
        "title": f"{REPO} {release['tag_name']} がリリースされました",
        "url": release["html_url"],
        "description": body,
        "color": 0x4F46E5,
        "footer": {"text": "codex-update-watcher"},
    }
    published_at = release.get("published_at")
    if published_at:
        embed["timestamp"] = published_at
    return {"embeds": [embed]}


def post_discord(webhook: str, release: dict) -> None:
    payload = build_payload(release)
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
        releases = fetch_releases()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"{REPO} has no releases yet")
            return 0
        raise

    if not releases:
        print(f"{REPO} has no stable releases yet")
        return 0

    latest = releases[0]
    last = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not last:
        STATE_FILE.write_text(latest["tag_name"] + "\n")
        print(f"Initialized state without notifying: {latest['tag_name']}")
        return 0

    if latest["tag_name"] == last:
        print(f"No new release (current: {last})")
        return 0

    new_releases = select_unnotified(releases, last)
    if len(new_releases) > CATCH_UP_CAP:
        print(
            f"warning: 未通知 {len(new_releases)} 件 → 上限 {CATCH_UP_CAP} 件に制限",
            file=sys.stderr,
        )
        new_releases = new_releases[:CATCH_UP_CAP]

    # 新しい順 → 古い順に並べ替えて時系列で投稿
    for release in reversed(new_releases):
        post_discord(webhook, release)

    STATE_FILE.write_text(latest["tag_name"] + "\n")
    tags = ", ".join(r["tag_name"] for r in reversed(new_releases))
    print(f"Notified {len(new_releases)} release(s): {tags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
