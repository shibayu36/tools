#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "yt-dlp>=2026.8.19",
#     "youtube-transcript-api>=1.2.4,<2",
# ]
# ///

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree.ElementTree import ParseError

import requests
from yt_dlp.utils import DownloadError
from youtube_transcript_api import (
    FetchedTranscript,
    NoTranscriptFound,
    TranscriptList,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)

from request_control import (
    RateLimitError,
    RateLimitedSession,
    RateLimitedYoutubeDL,
    RequestControl,
)


def playlist_url(value: str) -> str:
    parsed = urlparse(value)
    playlist_id = parse_qs(parsed.query).get("list", [""])[0]
    if (
        parsed.scheme not in {"https", "http"}
        or parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}
        or not re.fullmatch(r"[A-Za-z0-9_-]+", playlist_id)
    ):
        raise argparse.ArgumentTypeError(
            "list=...を含むYouTubeプレイリストURLを指定してください"
        )
    return "https://www.youtube.com/playlist?" + urlencode({"list": playlist_id})


def load_videos(url: str, control: RequestControl) -> list[dict]:
    with RateLimitedYoutubeDL(
        {
            "extract_flat": "in_playlist",
            "skip_download": True,
            "quiet": True,
            "socket_timeout": 30,
            "ignoreerrors": False,
        },
        control,
    ) as downloader:
        playlist = downloader.extract_info(url, download=False)
        if not playlist or playlist.get("_type") != "playlist":
            raise ValueError("プレイリストを取得できませんでした")
        if playlist.get("entries") is None:
            raise ValueError("プレイリストの動画一覧を取得できませんでした")
        return list(playlist["entries"])


def original_language(video: dict, transcripts: TranscriptList) -> str:
    # yt-dlpの元音声は優先度10。既定音声（優先度5）は吹き替えの場合がある。
    languages = {
        audio["language"]
        for audio in video.get("formats", [])
        if audio.get("language_preference") == 10 and audio.get("language")
    }
    if not languages:
        languages = {track.language_code for track in transcripts if track.is_generated}
    if len(languages) != 1:
        raise ValueError("動画の元言語を一意に判定できませんでした")
    return languages.pop()


def render_markdown(title: str, transcript: FetchedTranscript) -> str:
    body = "\n".join(
        snippet.text.strip() for snippet in transcript if snippet.text.strip()
    )
    if not body:
        raise ValueError("取得した字幕が空でした")
    title = " ".join(title.splitlines())
    subtitle_type = "自動生成" if transcript.is_generated else "手動"
    return (
        f"# {title}\n\n"
        f"URL: https://www.youtube.com/watch?v={transcript.video_id}\n"
        f"字幕: {transcript.language_code}（{subtitle_type}）\n\n"
        f"## 文字起こし\n\n{body}\n"
    )


def save_markdown(path: Path, content: str) -> None:
    temporary = path.with_suffix(".md.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def download_playlist(url: str, output: Path) -> int:
    saved = skipped = failed = 0
    control = RequestControl()
    try:
        videos = load_videos(url, control)
        output.mkdir(parents=True, exist_ok=True)
        print(f"対象: {len(videos)}動画")
        with RateLimitedSession(control) as session, RateLimitedYoutubeDL(
            {
                "quiet": True,
                "skip_download": True,
                "socket_timeout": 30,
                "ignore_no_formats_error": True,
                "no_warnings": True,
            },
            control,
        ) as downloader:
            api = YouTubeTranscriptApi(http_client=session)
            for index, video in enumerate(videos, start=1):
                video_id = (video or {}).get("id") or ""
                title = (video or {}).get("title")
                if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) or not title:
                    raise ValueError(f"{index}番目の動画のID・タイトルを取得できませんでした")
                print(f"[{index}/{len(videos)}] {title} ({video_id})", flush=True)
                try:
                    transcripts = api.list(video_id)
                    if not list(transcripts):
                        raise TranscriptsDisabled(video_id)
                    metadata = downloader.extract_info(
                        f"https://www.youtube.com/watch?v={video_id}",
                        download=False,
                        process=False,
                    )
                    if (
                        not metadata
                        or metadata.get("id") != video_id
                        or not metadata.get("title")
                    ):
                        raise ValueError("動画のタイトルを取得できませんでした")
                    language = original_language(metadata, transcripts)
                    transcript = transcripts.find_transcript([language]).fetch()
                except (TranscriptsDisabled, NoTranscriptFound):
                    skipped += 1
                    print("  スキップ: 元言語の字幕がありません")
                    continue
                if not re.fullmatch(r"[A-Za-z0-9-]+", transcript.language_code):
                    raise ValueError("字幕の言語コードが不正です")
                content = render_markdown(metadata["title"], transcript)
                path = output / f"{video_id}.{transcript.language_code}.md"
                save_markdown(path, content)
                saved += 1
                print(f"  保存: {path}")
    except (
        RateLimitError,
        DownloadError,
        YouTubeTranscriptApiException,
        requests.RequestException,
        ParseError,
        OSError,
        ValueError,
    ) as error:
        failed = 1
        print(f"エラー: {error}\n処理を中断しました。", file=sys.stderr)
    print(f"保存: {saved} / 字幕なし: {skipped} / 失敗: {failed}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="YouTubeプレイリストのタイトルと既存字幕を動画ごとのMarkdownに保存する"
    )
    parser.add_argument("url", type=playlist_url, help="YouTubeプレイリストURL")
    parser.add_argument(
        "--output", type=Path, default=Path("transcripts"), help="保存先（既定: transcripts）"
    )
    args = parser.parse_args(argv)
    return download_playlist(args.url, args.output)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n中断しました。保存済みのファイルは保持されます。", file=sys.stderr)
        sys.exit(130)
