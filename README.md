# codex-update-watcher

`openai/codex` の新しいリリースを検知して、Discord にまとめて通知する GitHub Actions です。

## しくみ

- 30分おきに cron で `openai/codex` の最新リリースを取得
- 前回通知済みのタグ (`state/last_release.txt`) と比較
- 新しいリリースがあれば Discord Webhook に投稿し、タグをコミットして記録

リリース毎に1通だけ届く想定なので Discord が荒れません。

## セットアップ

1. このリポジトリの **Settings → Secrets and variables → Actions** に以下を登録:
   - `DISCORD_WEBHOOK_URL`: 通知先チャンネルの Webhook URL
2. **Settings → Actions → General → Workflow permissions** で **Read and write permissions** を有効化（state ファイルを commit するため）
3. デフォルトでは `openai/codex` を監視。別リポジトリにする場合はワークフローの `WATCH_REPO` を変更

## 手動実行

`Actions` タブから `notify-release` ワークフローを `Run workflow` で即時実行できます。

## 初回実行

初回は通知をスキップして現在の最新タグを `state/` に記録するだけにしています（過去リリースの再通知を防ぐため）。

## トラブルシュート

### Discord 投稿が `error code: 1010` で失敗する

Cloudflare がデフォルトの `Python-urllib/...` User-Agent をボット判定して弾くためです。`scripts/notify_release.py` の `post_discord` で `User-Agent` ヘッダを明示しているので、外さないでください。失敗通知 step の `curl` も `-A 'codex-update-watcher'` で UA を付けています。

### Workflow log の `Discord rejected: HTTP ... body=...` の読み方

診断用の出力です。URL 本体は出力していないので公開リポでも安全。

- `HTTP 403 body=error code: 1010` → Cloudflare ブロック（UA 問題）
- `HTTP 404 body=...Unknown Webhook...` → webhook が削除済み or secret 値が壊れている
- `HTTP 401 body=...Invalid Webhook Token...` → secret 値の URL 末尾が破損

`webhook_len` と `starts_https=True/False` も同時に出力されるので、secret 値の体裁も確認できます。

### 失敗通知が届く

cron / 手動実行が失敗すると、同じ Discord webhook に「⚠️ codex-update-watcher の workflow が失敗しました」と Run URL が届きます。Run URL を開いて該当ジョブの log を確認してください。

### Webhook URL が漏洩した時

1. Discord のチャンネル設定 → 連携サービス → ウェブフック → 既存削除 → 新規作成
2. **どこにも貼らずに** 自分のターミナルで `gh secret set DISCORD_WEBHOOK_URL --repo <owner>/<repo>` を**対話モード**で実行（プロンプトに URL を貼って Enter）
3. `--body` 引数や `printf | gh secret set` で履歴に残る方法は避ける
