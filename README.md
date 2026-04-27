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
