import contextlib
import io
import unittest
from email.utils import formatdate
from unittest.mock import patch

import requests
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError

from request_control import (
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


def response(status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result.raw = io.BytesIO()
    result.raw.release_conn = result.raw.close
    result._content = b""
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

    def ytdlp_response(self, status=200, headers=None):
        result = Response(io.BytesIO(), URL, headers or {}, status=status)
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

    def test_requests_does_not_retry_other_status_codes(self):
        self.requests_responses(response(403))
        with RateLimitedSession(self.control) as session:
            self.assertEqual(session.get(URL).status_code, 403)
        self.assertEqual(self.starts, [0])

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
