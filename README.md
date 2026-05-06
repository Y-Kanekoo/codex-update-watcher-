# codex-update-watcher

`openai/codex` の新しいリリースを検知して、Discord にまとめて通知する GitHub Actions です。

## しくみ

- 30分おきに cron で `openai/codex` の最新リリースを取得（pre-release/draft は除外）
- 前回通知済みのタグ (`state/<owner>__<repo>.txt`) と比較
- 新しいリリースがあれば Discord Webhook に投稿し、タグをコミットして記録
- 30分間に複数リリースが出た場合は時系列順で全件 catch-up 通知（最大5件）
- 一過性 (429/5xx/network) のエラーは指数バックオフで最大2回 retry
- ジョブ自体が失敗した場合も Discord に通知が届く
- push / PR 時には `test` workflow が unittest を実行

## セットアップ

1. このリポジトリの **Settings → Secrets and variables → Actions** に以下を登録:
   - `DISCORD_WEBHOOK_URL`: 通知先チャンネルの Webhook URL
2. **Settings → Actions → General → Workflow permissions** で **Read and write permissions** を有効化（state ファイルを commit するため）
3. デフォルトでは `openai/codex` を監視。継続的に別 repo を監視したい場合は `.github/workflows/notify-release.yml` の `WATCH_REPO` のフォールバック値 (`'openai/codex'`) を変更

## 手動実行

`Actions` タブから `notify-release` ワークフローを `Run workflow` で即時実行できます。`watch_repo` input に `<owner>/<repo>` を指定すると一時的に他 repo を試せます（state ファイルが repo 別 (`state/<owner>__<repo>.txt`) なので本来の監視対象 (`openai/codex`) の履歴は壊れません）。

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

### 定期的な webhook rotation

漏洩していなくても、半年〜1年程度を目安に webhook URL を再生成しておくと安全です。手順は上記「Webhook URL が漏洩した時」と同じ。`gh secret list --repo <owner>/<repo>` で `Updated` 日付を確認できるので運用の目安になります。
