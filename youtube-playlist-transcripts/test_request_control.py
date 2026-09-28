import contextlib
import io
import unittest
from email.utils import formatdate
from unittest.mock import patch

import requests
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError

from request_control import (
    MAX_LOG_BODY_BYTES,
    RateLimitError,
    RateLimitedSession,
    RateLimitedYoutubeDL,
    RequestControl,
    retry_delay,
)


URL = "https://www.youtube.com/watch?v=abcdefghijk"


class FakeClock:
    def __init__(self):
        self.elapsed = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.elapsed

    def time(self):
        return 1_700_000_000 + self.elapsed

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.elapsed += seconds


def response(status=200, headers=None, body=b""):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result.raw = io.BytesIO()
    result.raw.release_conn = result.raw.close
    result._content = body
    result._content_consumed = True
    return result


class RequestControlTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.enterContext(patch("request_control.time.monotonic", self.clock.monotonic))
        self.enterContext(patch("request_control.time.time", self.clock.time))
        self.enterContext(patch("request_control.time.sleep", self.clock.sleep))
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stderr(self.stderr))
        self.control = RequestControl()
        self.starts = []

    def requests_responses(self, *responses):
        remaining = iter(responses)

        def send(request, **kwargs):
            self.starts.append(self.clock.monotonic())
            result = next(remaining)
            result.request = request
            result.url = request.url
            return result

        return self.enterContext(patch("requests.adapters.HTTPAdapter.send", side_effect=send))

    def ytdlp_responses(self, *responses):
        remaining = iter(responses)

        def send(request):
            self.starts.append(self.clock.monotonic())
            result = next(remaining)
            if isinstance(result, Exception):
                raise result
            return result

        return self.enterContext(patch("request_control.YoutubeDL.urlopen", side_effect=send))

    def limited_ytdlp(self):
        return self.enterContext(
            RateLimitedYoutubeDL({"quiet": True, "cachedir": False}, self.control)
        )

    def ytdlp_response(self, status=200, headers=None, body=b"", url=URL):
        result = Response(io.BytesIO(body), url, headers or {}, status=status)
        self.addCleanup(result.close)
        return result

    def test_minimum_interval_is_shared_by_both_clients(self):
        self.requests_responses(response(), response())
        self.ytdlp_responses(self.ytdlp_response())
        with RateLimitedSession(self.control) as session:
            downloader = self.limited_ytdlp()
            session.get(URL)
            downloader.urlopen(URL)
            session.get(URL)
        self.assertEqual(self.starts, [0, 3, 6])

    def test_time_spent_on_a_request_counts_toward_the_interval(self):
        self.control.wait()
        self.clock.elapsed += 2
        self.control.wait()
        self.assertEqual(self.clock.sleeps, [1])
        self.clock.elapsed += 10
        self.control.wait()
        self.assertEqual(self.clock.sleeps, [1])

    def test_retry_after_supports_seconds_and_http_date(self):
        self.assertEqual(retry_delay(" 45 ", 0), 45)
        date = formatdate(self.clock.time() + 60, usegmt=True)
        self.assertEqual(retry_delay(date, 0), 60)
        self.assertEqual(retry_delay(formatdate(self.clock.time() - 60, usegmt=True), 0), 0)

    def test_invalid_or_missing_retry_after_uses_increasing_delays(self):
        for value in (None, "", "invalid", "-1", "NaN"):
            with self.subTest(value=value):
                self.assertEqual([retry_delay(value, attempt) for attempt in range(3)], [30, 60, 120])

    def test_requests_retries_429_at_increasing_intervals(self):
        limited = [response(429) for _ in range(3)]
        self.requests_responses(*limited, response())
        with RateLimitedSession(self.control) as session:
            self.assertEqual(session.get(URL).status_code, 200)
        self.assertEqual(self.starts, [0, 30, 90, 210])
        self.assertTrue(all(item.raw.closed for item in limited))
        self.assertIn("120秒待って再試行します (3/3)", self.stderr.getvalue())

    def test_requests_respects_retry_after_and_keeps_the_post_body(self):
        adapter = self.requests_responses(response(429, {"Retry-After": "45"}), response())
        with RateLimitedSession(self.control) as session:
            session.post(URL, json={"videoId": "abcdefghijk"})
        self.assertEqual(self.starts, [0, 45])
        first, second = [call.args[0] for call in adapter.call_args_list]
        self.assertEqual((first.method, first.body), (second.method, second.body))

    def test_requests_retries_a_redirect_target_without_restarting_the_redirect(self):
        target = "https://www.youtube.com/redirected"
        adapter = self.requests_responses(
            response(302, {"Location": target}),
            response(429, {"Retry-After": "10"}),
            response(),
        )
        with RateLimitedSession(self.control) as session:
            self.assertEqual(session.get(URL).status_code, 200)
        self.assertEqual(self.starts, [0, 3, 13])
        self.assertEqual([call.args[0].url for call in adapter.call_args_list], [URL, target, target])

    def test_requests_stops_after_three_retries(self):
        limited = [response(429) for _ in range(4)]
        self.requests_responses(*limited)
        with RateLimitedSession(self.control) as session:
            with self.assertRaisesRegex(RateLimitError, "3回再試行"):
                session.get(URL)
        self.assertEqual(self.starts, [0, 30, 90, 210])
        self.assertTrue(all(item.raw.closed for item in limited))
        self.assertEqual(self.stderr.getvalue().count("HTTP 429 詳細"), 4)

    def test_requests_logs_rate_limit_details_without_query_or_cookies(self):
        headers = {
            "Retry-After": "45",
            "Content-Type": "application/json",
            "Date": "Sat, 26 Sep 2026 00:00:00 GMT",
            "Server": "test-server",
            "Set-Cookie": "session=private-cookie",
        }
        self.requests_responses(
            response(429, headers, b'{"error":"Too Many Requests"}'), response()
        )
        with RateLimitedSession(self.control) as session:
            session.get("https://www.youtube.com/api/timedtext?v=abcdefghijk&sig=private-token")
        log = self.stderr.getvalue()
        self.assertIn("HTTP 429 詳細 (youtube-transcript-api)", log)
        self.assertIn("接続先: https://www.youtube.com/api/timedtext\n", log)
        self.assertIn('Retry-After: "45"', log)
        self.assertIn('Content-Type: "application/json"', log)
        self.assertIn('Date: "Sat, 26 Sep 2026 00:00:00 GMT"', log)
        self.assertIn('Server: "test-server"', log)
        self.assertIn("Too Many Requests", log)
        self.assertNotIn("private-token", log)
        self.assertNotIn("private-cookie", log)

    def test_requests_logs_missing_retry_after_and_empty_body(self):
        self.requests_responses(response(429), response())
        with RateLimitedSession(self.control) as session:
            session.get(URL)
        self.assertIn("Retry-After: なし", self.stderr.getvalue())
        self.assertIn("本文: 空", self.stderr.getvalue())
        self.assertEqual(self.starts, [0, 30])

    def test_requests_truncates_and_escapes_logged_body(self):
        body = b"blocked\n\x1b[31m" + b"x" * MAX_LOG_BODY_BYTES + b"hidden-tail"
        self.requests_responses(response(429, body=body), response())
        with RateLimitedSession(self.control) as session:
            session.get(URL)
        log = self.stderr.getvalue()
        self.assertIn(r"blocked\n\u001b[31m", log)
        self.assertIn(f"先頭{MAX_LOG_BODY_BYTES}バイトで省略", log)
        self.assertNotIn("hidden-tail", log)

    def test_requests_does_not_retry_other_status_codes(self):
        self.requests_responses(response(403))
        with RateLimitedSession(self.control) as session:
            self.assertEqual(session.get(URL).status_code, 403)
        self.assertEqual(self.starts, [0])
        self.assertEqual(self.stderr.getvalue(), "")

    def test_ytdlp_respects_retry_after_date(self):
        date = formatdate(self.clock.time() + 45, usegmt=True)
        limited = self.ytdlp_response(429, {"Retry-After": date})
        success = self.ytdlp_response()
        self.ytdlp_responses(HTTPError(limited), success)
        downloader = self.limited_ytdlp()
        self.assertIs(downloader.urlopen(URL), success)
        self.assertEqual(self.starts, [0, 45])
        self.assertTrue(limited.fp.closed)
        self.assertEqual(downloader.params["extractor_retries"], 0)

    def test_ytdlp_stops_after_three_retries(self):
        limited = [self.ytdlp_response(429) for _ in range(4)]
        self.ytdlp_responses(*(HTTPError(item) for item in limited))
        downloader = self.limited_ytdlp()
        with self.assertRaisesRegex(RateLimitError, "3回再試行"):
            downloader.urlopen(URL)
        self.assertEqual(self.starts, [0, 30, 90, 210])
        self.assertTrue(all(item.fp.closed for item in limited))
        self.assertEqual(self.stderr.getvalue().count("HTTP 429 詳細"), 4)

    def test_ytdlp_logs_response_url_headers_and_body(self):
        limited = self.ytdlp_response(
            429,
            {"Content-Type": "text/html", "Set-Cookie": "session=private-cookie"},
            "<html>取得制限</html>".encode(),
            "https://www.youtube.com/sorry/index?continue=private-token",
        )
        self.ytdlp_responses(HTTPError(limited), self.ytdlp_response())
        self.limited_ytdlp().urlopen(URL)
        log = self.stderr.getvalue()
        self.assertIn("HTTP 429 詳細 (yt-dlp)", log)
        self.assertIn("接続先: https://www.youtube.com/sorry/index\n", log)
        self.assertIn("Retry-After: なし", log)
        self.assertIn('Content-Type: "text/html"', log)
        self.assertIn("<html>取得制限</html>", log)
        self.assertNotIn("private-token", log)
        self.assertNotIn("private-cookie", log)
        self.assertTrue(limited.fp.closed)

    def test_ytdlp_bounds_body_read_and_handles_invalid_utf8(self):
        limited = self.ytdlp_response(429, body=b"\xff" * (MAX_LOG_BODY_BYTES + 20))
        self.ytdlp_responses(HTTPError(limited), self.ytdlp_response())
        with patch.object(limited, "read", wraps=limited.read) as read:
            self.limited_ytdlp().urlopen(URL)
        read.assert_called_once_with(MAX_LOG_BODY_BYTES + 1)
        self.assertIn("\ufffd", self.stderr.getvalue())
        self.assertIn(f"先頭{MAX_LOG_BODY_BYTES}バイトで省略", self.stderr.getvalue())

    def test_ytdlp_retries_even_when_reading_error_body_fails(self):
        limited = self.ytdlp_response(429)
        self.ytdlp_responses(HTTPError(limited), self.ytdlp_response())
        with patch.object(limited.fp, "read", side_effect=OSError("broken connection")):
            self.limited_ytdlp().urlopen(URL)
        self.assertEqual(self.starts, [0, 30])
        self.assertIn("本文: 読み取り失敗 (TransportError)", self.stderr.getvalue())
        self.assertTrue(limited.fp.closed)

    def test_ytdlp_does_not_retry_other_status_codes(self):
        error = HTTPError(self.ytdlp_response(403))
        self.ytdlp_responses(error)
        downloader = self.limited_ytdlp()
        with self.assertRaises(HTTPError) as raised:
            downloader.urlopen(URL)
        self.assertIs(raised.exception, error)
        self.assertEqual(self.starts, [0])

    def test_ytdlp_extraction_propagates_the_retry_limit_without_another_retry(self):
        self.ytdlp_responses(*(HTTPError(self.ytdlp_response(429)) for _ in range(4)))
        downloader = self.limited_ytdlp()
        with self.assertRaises(RateLimitError):
            downloader.extract_info(
                "https://www.youtube.com/playlist?list=PLtest1234567890", download=False
            )
        self.assertEqual(self.starts, [0, 30, 90, 210])

    def test_zero_retry_after_still_observes_the_normal_interval(self):
        self.requests_responses(response(429, {"Retry-After": "0"}), response())
        with RateLimitedSession(self.control) as session:
            session.get(URL)
        self.assertEqual(self.starts, [0, 3])

    def test_unrepresentable_retry_after_stops_instead_of_retrying_early(self):
        self.requests_responses(response(429, {"Retry-After": "9" * 400}))
        with RateLimitedSession(self.control) as session:
            with self.assertRaisesRegex(RateLimitError, "待機時間が大きすぎる"):
                session.get(URL)
        self.assertEqual(self.starts, [0])

    def test_wait_can_be_interrupted(self):
        self.control.wait()
        with patch("request_control.time.sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.control.wait()


if __name__ == "__main__":
    unittest.main()
