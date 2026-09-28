# YouTube Playlist Transcripts

YouTubeプレイリストのタイトルと字幕を、動画ごとのMarkdownに保存します。

## 使い方

`uv`を用意し、リポジトリのルートから実行します。以下のURLを対象のプレイリストURLに置き換えてください。

```bash
uv run youtube-playlist-transcripts/download.py \
  'https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID' \
  --output ./transcripts
```

動画の元言語を自動で判定し、その言語の字幕を保存します。日本語・英語などが混在するプレイリストでも言語の指定は不要です。翻訳は行いません。

| 引数 | 内容 | 既定値 |
| --- | --- | --- |
| `url` | `list=...`を含むYouTubeのURL | 必須 |
| `--output` | 保存先ディレクトリ。存在しなければ作成する | `./transcripts` |

## 保存内容

`transcripts/動画ID.言語.md`に元のタイトル・動画URL・字幕の種類・本文を保存します。本文はタイムスタンプを付けずに字幕の区切りで改行します。

同じ動画・言語で再実行すると、取得が成功したファイルを上書きします。

### playlist.json

全動画の処理後（致命的エラーや`Ctrl+C`による中断時も、そこまでの結果で）に`transcripts/playlist.json`へマニフェストを保存します。プレイリスト名・チャンネル名・動画の順序・公開日・字幕ファイル名などを、他のスクリプトから決定論的に読み取れるようにするためのものです。取得できなかった項目は`null`にします。

```json
{
  "playlist_id": "PLxxxx",
  "playlist_url": "https://www.youtube.com/playlist?list=PLxxxx",
  "playlist_title": "…",
  "channel": "…",
  "channel_url": "…",
  "videos": [
    {
      "index": 1,
      "video_id": "abc",
      "title": "…",
      "url": "https://www.youtube.com/watch?v=abc",
      "upload_date": "2024-01-31",
      "channel": "…",
      "status": "saved",
      "language_code": "ja",
      "transcript_file": "abc.ja.md"
    }
  ]
}
```

`videos[].status`は次のいずれかです。

| status | 意味 |
| --- | --- |
| `saved` | Markdownを保存した |
| `no_transcript` | 元言語の字幕がなくスキップした |
| `failed` | 取得・保存に失敗した |
| `skipped` | 中断により未処理のまま終わった |

`status`が`saved`以外の`upload_date`・`channel`・`language_code`・`transcript_file`は`null`です。

## 字幕の選択とエラー

- 元言語の手動字幕を優先し、なければ同じ言語の自動生成字幕を取得します。
- 元言語の字幕がない動画はスキップします。
- 取得リクエストは最低3秒空けます。取得制限を受けると待機して最大3回再試行し、待機時間を表示します。
- 元言語を判定できない場合や通信・保存エラーが発生した場合は、取得済みファイルを残して中断します。
- `Ctrl+C`でも中断できます。

取得対象はログインせずにアクセスできるプレイリスト・動画です。正常終了は終了コード`0`、取得・保存失敗は`1`、`Ctrl+C`による中断は`130`です。字幕なしのスキップは正常終了に含まれます。

HTTP 429が発生するたびに、使用ライブラリ・接続先のホストとパス・`Retry-After`・`Content-Type`・`Date`・`Server`・レスポンス本文の先頭4KiBを標準エラーに出力します。`Retry-After`がない場合は「なし」と表示します。URLのクエリとCookieヘッダーは出力しません。ログをファイルに残す場合は、実行コマンドの末尾に`2> youtube-errors.log`を付けてください。

## 取得ライブラリの更新

YouTube側の変更により取得できなくなった場合は、依存ライブラリを更新して再実行できます。

```bash
uv run --upgrade youtube-playlist-transcripts/download.py \
  'https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID'
```

## 開発時のテスト

```bash
uv run --no-project \
  --with 'yt-dlp>=2026.8.19' \
  --with 'youtube-transcript-api>=1.2.4,<2' \
  python -m unittest discover -s youtube-playlist-transcripts -v
```
