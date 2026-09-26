import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree.ElementTree import ParseError

import requests
from yt_dlp.utils import DownloadError
from youtube_transcript_api import (
    FetchedTranscript,
    FetchedTranscriptSnippet,
    NoTranscriptFound,
    RequestBlocked,
    Transcript,
    TranscriptList,
    TranscriptsDisabled,
)

import download


VIDEO_ID = "abcdefghijk"
NEXT_ID = "lmnopqrstuv"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLexample"


def fetched(video_id=VIDEO_ID, language="ja", generated=False, text="こんにちは。"):
    return FetchedTranscript(
        snippets=[FetchedTranscriptSnippet(text=text, start=0, duration=2)],
        video_id=video_id,
        language=language,
        language_code=language,
        is_generated=generated,
    )


def available(video_id=VIDEO_ID, language="ja", generated=True, text="こんにちは。"):
    track = Transcript(MagicMock(), video_id, "url", language, language, generated, [])
    track.fetch = MagicMock(return_value=fetched(video_id, language, generated, text))
    return TranscriptList(
        video_id,
        {} if generated else {language: track},
        {language: track} if generated else {},
        [],
    )


def metadata(video_id=VIDEO_ID, language="ja"):
    return {
        "id": video_id,
        "title": "元の日本語 / 同じタイトル",
        "formats": [{"language": language, "language_preference": 10}],
    }


class PlaylistUrlTest(unittest.TestCase):
    def test_watch_url_is_normalized_to_playlist(self):
        self.assertEqual(
            download.playlist_url(
                f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PLexample&index=2"
            ),
            PLAYLIST_URL,
        )

    def test_invalid_urls_are_rejected(self):
        for url in (
            f"https://www.youtube.com/watch?v={VIDEO_ID}",
            "https://example.com/playlist?list=PLexample",
            "https://youtube.com.example.com/playlist?list=PLexample",
            "file:///playlist?list=PLexample",
            "https://www.youtube.com/playlist?list=../bad",
            "https://www.youtube.com/playlist?list=",
        ):
            with self.subTest(url=url), self.assertRaises(argparse.ArgumentTypeError):
                download.playlist_url(url)


class LoadVideosTest(unittest.TestCase):
    @patch("download.RateLimitedYoutubeDL")
    def test_only_playlist_metadata_is_requested(self, downloader):
        videos = [{"id": VIDEO_ID, "title": "動画"}]
        instance = downloader.return_value.__enter__.return_value
        instance.extract_info.return_value = {"_type": "playlist", "entries": videos}
        self.assertEqual(download.load_videos(PLAYLIST_URL, download.RequestControl()), videos)
        instance.extract_info.assert_called_once_with(PLAYLIST_URL, download=False)
        options = downloader.call_args.args[0]
        self.assertEqual(options["extract_flat"], "in_playlist")
        self.assertTrue(options["skip_download"])
        self.assertFalse(options["ignoreerrors"])

    @patch("download.RateLimitedYoutubeDL")
    def test_incomplete_playlist_is_an_error(self, downloader):
        instance = downloader.return_value.__enter__.return_value
        for value in (None, {"_type": "video"}, {"_type": "playlist"}):
            instance.extract_info.return_value = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                download.load_videos(PLAYLIST_URL, download.RequestControl())


class MarkdownTest(unittest.TestCase):
    def test_title_url_language_and_subtitle_text_are_saved(self):
        transcript = fetched(generated=True)
        transcript.snippets.extend(
            [
                FetchedTranscriptSnippet(text=" ", start=2, duration=1),
                FetchedTranscriptSnippet(text="次の行です。", start=3, duration=2),
            ]
        )
        self.assertEqual(
            download.render_markdown("日本語の動画", transcript),
            "# 日本語の動画\n\n"
            f"URL: https://www.youtube.com/watch?v={VIDEO_ID}\n"
            "字幕: ja（自動生成）\n\n"
            "## 文字起こし\n\nこんにちは。\n次の行です。\n",
        )

    def test_empty_subtitles_are_an_error(self):
        with self.assertRaisesRegex(ValueError, "空"):
            download.render_markdown("動画", fetched(text=" \n"))

    def test_failed_replacement_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.ja.md"
            path.write_text("保存済み", encoding="utf-8")
            with patch.object(Path, "replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    download.save_markdown(path, "新しい字幕")
            self.assertEqual(path.read_text(encoding="utf-8"), "保存済み")
            self.assertEqual(list(Path(directory).iterdir()), [path])


class DownloadPlaylistTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "output"
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))
        self.loader = self.enterContext(patch("download.load_videos"))
        self.loader.return_value = [
            {"id": VIDEO_ID, "title": "日本語 / 同じタイトル"},
            {"id": NEXT_ID, "title": "日本語 / 同じタイトル"},
        ]
        self.api = self.enterContext(patch("download.YouTubeTranscriptApi")).return_value
        self.api.list.side_effect = [available(), available(video_id=NEXT_ID)]
        downloader = self.enterContext(patch("download.RateLimitedYoutubeDL"))
        self.downloader = downloader.return_value.__enter__.return_value
        self.downloader.extract_info.side_effect = [metadata(), metadata(NEXT_ID)]

    def run_download(self):
        return download.download_playlist(PLAYLIST_URL, self.output)

    def test_same_titles_are_saved_separately(self):
        self.assertEqual(self.run_download(), 0)
        self.assertEqual(len(list(self.output.glob("*.md"))), 2)
        self.assertIn("保存: 2 / 字幕なし: 0 / 失敗: 0", self.stdout.getvalue())

    def test_cli_uses_original_title_instead_of_playlist_translation(self):
        self.loader.return_value[0]["title"] = "A translated title..."
        self.assertEqual(download.main([PLAYLIST_URL, "--output", str(self.output)]), 0)
        text = (self.output / f"{VIDEO_ID}.ja.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 元の日本語 / 同じタイトル\n"))
        self.downloader.extract_info.assert_any_call(
            f"https://www.youtube.com/watch?v={VIDEO_ID}", download=False, process=False
        )

    def test_mixed_japanese_and_english_videos_need_no_language_option(self):
        self.api.list.side_effect = [available(), available(NEXT_ID, "en", text="Hello.")]
        self.downloader.extract_info.side_effect = [metadata(), metadata(NEXT_ID, "en")]
        self.assertEqual(self.run_download(), 0)
        self.assertTrue((self.output / f"{VIDEO_ID}.ja.md").exists())
        self.assertIn("Hello.", (self.output / f"{NEXT_ID}.en.md").read_text())

    def test_missing_subtitles_are_skipped_and_next_video_is_saved(self):
        for error in (
            TranscriptsDisabled(VIDEO_ID),
            NoTranscriptFound(VIDEO_ID, ["ja"], ""),
        ):
            with self.subTest(error=type(error).__name__):
                self.api.list.side_effect = [error, available(video_id=NEXT_ID)]
                self.downloader.extract_info.side_effect = [metadata(NEXT_ID)]
                self.assertEqual(self.run_download(), 0)
                self.assertFalse((self.output / f"{VIDEO_ID}.ja.md").exists())
                self.assertTrue((self.output / f"{NEXT_ID}.ja.md").exists())
                self.assertIn("字幕なし: 1 / 失敗: 0", self.stdout.getvalue())

    def test_request_or_parse_failure_stops_and_preserves_saved_files(self):
        self.loader.return_value.append({"id": "wxyz0123456", "title": "未処理"})
        for error in (
            RequestBlocked(NEXT_ID),
            requests.Timeout("timeout"),
            ParseError("invalid XML"),
            download.RateLimitError("HTTP 429"),
        ):
            with self.subTest(error=type(error).__name__):
                self.api.list.reset_mock()
                self.api.list.side_effect = [available(), error]
                self.downloader.extract_info.side_effect = [metadata()]
                self.assertEqual(self.run_download(), 1)
                self.assertTrue((self.output / f"{VIDEO_ID}.ja.md").exists())
                self.assertFalse((self.output / f"{NEXT_ID}.ja.md").exists())
                self.assertEqual(self.api.list.call_count, 2)
                self.assertIn("失敗: 1", self.stdout.getvalue())
                self.assertIn("処理を中断しました", self.stderr.getvalue())

    def test_playlist_failure_does_not_start_subtitle_requests(self):
        self.loader.side_effect = DownloadError("playlist unavailable")
        self.assertEqual(self.run_download(), 1)
        self.api.list.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_invalid_video_id_cannot_escape_output_directory(self):
        self.loader.return_value = [{"id": "../outside", "title": "動画"}]
        self.assertEqual(self.run_download(), 1)
        self.api.list.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_output_write_failure_is_reported(self):
        with patch("download.save_markdown", side_effect=OSError("disk full")):
            self.assertEqual(self.run_download(), 1)
        self.assertIn("disk full", self.stderr.getvalue())

    def test_empty_playlist_finishes_without_subtitle_requests(self):
        self.loader.return_value = []
        self.assertEqual(self.run_download(), 0)
        self.api.list.assert_not_called()
        self.assertIn("保存: 0 / 字幕なし: 0 / 失敗: 0", self.stdout.getvalue())

    def test_original_language_missing_does_not_download_a_translation(self):
        self.api.list.side_effect = [available(language="en", generated=False), available(NEXT_ID)]
        self.downloader.extract_info.side_effect = [metadata(), metadata(NEXT_ID)]
        self.assertEqual(self.run_download(), 0)
        self.assertFalse((self.output / f"{VIDEO_ID}.en.md").exists())
        self.assertTrue((self.output / f"{NEXT_ID}.ja.md").exists())
        self.assertIn("字幕なし: 1", self.stdout.getvalue())

    def test_dubbed_subtitles_are_not_chosen_before_original_subtitles(self):
        dubbed = available(language="en-US").find_transcript(["en-US"])
        original = available().find_transcript(["ja"])
        self.api.list.side_effect = [
            TranscriptList(VIDEO_ID, {}, {"en-US": dubbed, "ja": original}, []),
            available(NEXT_ID),
        ]
        self.assertEqual(self.run_download(), 0)
        dubbed.fetch.assert_not_called()
        original.fetch.assert_called_once_with()
        self.assertTrue((self.output / f"{VIDEO_ID}.ja.md").exists())

    def test_original_manual_subtitles_are_preferred(self):
        manual = available(generated=False).find_transcript(["ja"])
        generated = available().find_transcript(["ja"])
        translated = available(language="en", generated=False).find_transcript(["en"])
        self.api.list.side_effect = [
            TranscriptList(VIDEO_ID, {"en": translated, "ja": manual}, {"ja": generated}, []),
            available(NEXT_ID),
        ]
        self.assertEqual(self.run_download(), 0)
        manual.fetch.assert_called_once_with()
        generated.fetch.assert_not_called()
        translated.fetch.assert_not_called()

    def test_missing_original_language_is_reported_as_error(self):
        self.api.list.side_effect = [available(generated=False)]
        self.downloader.extract_info.side_effect = [{"id": VIDEO_ID, "title": "動画"}]
        self.assertEqual(self.run_download(), 1)
        self.assertIn("元言語を一意に判定できませんでした", self.stderr.getvalue())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_empty_subtitle_list_is_skipped_without_metadata_request(self):
        self.api.list.side_effect = [TranscriptList(VIDEO_ID, {}, {}, []), available(NEXT_ID)]
        self.downloader.extract_info.side_effect = [metadata(NEXT_ID)]
        self.assertEqual(self.run_download(), 0)
        self.assertEqual(self.downloader.extract_info.call_count, 1)

    def test_missing_original_title_is_an_error(self):
        self.downloader.extract_info.side_effect = [{"id": VIDEO_ID}]
        self.assertEqual(self.run_download(), 1)
        self.assertIn("タイトルを取得できませんでした", self.stderr.getvalue())

    def test_language_code_cannot_escape_output_directory(self):
        self.api.list.side_effect = [available(language="../../en")]
        self.downloader.extract_info.side_effect = [metadata(language="../../en")]
        self.assertEqual(self.run_download(), 1)
        self.assertIn("言語コードが不正", self.stderr.getvalue())
        self.assertEqual(list(self.output.iterdir()), [])


class OriginalLanguageTest(unittest.TestCase):
    def test_original_audio_wins_over_default_dubbed_audio(self):
        video = metadata()
        video["formats"].append({"language": "en-US", "language_preference": 5})
        self.assertEqual(download.original_language(video, available()), "ja")

    def test_single_generated_language_is_used_when_audio_has_no_language(self):
        self.assertEqual(download.original_language({}, available(language="en")), "en")

    def test_multiple_generated_languages_are_ambiguous_without_audio_metadata(self):
        original = available().find_transcript(["ja"])
        dubbed = available(language="en-US").find_transcript(["en-US"])
        tracks = TranscriptList(VIDEO_ID, {}, {"en-US": dubbed, "ja": original}, [])
        with self.assertRaisesRegex(ValueError, "元言語"):
            download.original_language({}, tracks)

    def test_manual_subtitle_language_alone_does_not_prove_original_language(self):
        with self.assertRaisesRegex(ValueError, "元言語"):
            download.original_language({}, available(language="en", generated=False))


class TranscriptSelectionTest(unittest.TestCase):
    def test_library_prefers_manual_subtitles_and_falls_back_to_generated(self):
        manual = Transcript(MagicMock(), VIDEO_ID, "url", "Japanese", "ja", False, [])
        generated = Transcript(MagicMock(), VIDEO_ID, "url", "Japanese", "ja", True, [])
        both = TranscriptList(VIDEO_ID, {"ja": manual}, {"ja": generated}, [])
        auto_only = TranscriptList(VIDEO_ID, {}, {"ja": generated}, [])
        self.assertIs(both.find_transcript(["ja"]), manual)
        self.assertIs(auto_only.find_transcript(["ja"]), generated)


class TimeoutTest(unittest.TestCase):
    @patch("requests.Session.request")
    def test_subtitle_requests_have_a_timeout(self, request):
        with download.RateLimitedSession(download.RequestControl()) as session:
            session.get("https://www.youtube.com/")
        self.assertEqual(request.call_args.kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
