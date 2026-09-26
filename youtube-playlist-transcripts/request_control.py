from __future__ import annotations

import math
import re
import sys
import time
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests
from yt_dlp import YoutubeDL
from yt_dlp.networking.exceptions import HTTPError


MAX_RETRIES = 3


class RateLimitError(RuntimeError):
    pass


def retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after is not None:
        value = retry_after.strip()
        if re.fullmatch(r"[0-9]+", value):
            return float(value)
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0, date.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            pass
    return 30 * 2**attempt


class RequestControl:
    def __init__(self):
        self.interval = 3.0
        self.next_request = 0.0

    def wait(self) -> None:
        delay = self.next_request - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.next_request = time.monotonic() + self.interval

    def retry(self, retry_after: str | None, attempt: int) -> None:
        if attempt >= MAX_RETRIES:
            raise RateLimitError(f"HTTP 429: {MAX_RETRIES}回再試行しても取得制限が続いています")
        delay = max(self.interval, retry_delay(retry_after, attempt))
        if not math.isfinite(delay):
            raise RateLimitError("HTTP 429: Retry-Afterの待機時間が大きすぎるため中断します")
        self.next_request = max(self.next_request, time.monotonic() + delay)
        print(
            f"HTTP 429: {delay:g}秒待って再試行します ({attempt + 1}/{MAX_RETRIES})",
            file=sys.stderr,
            flush=True,
        )


class RateLimitedSession(requests.Session):
    def __init__(self, control: RequestControl):
        super().__init__()
        self.control = control

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 30)
        return super().request(method, url, **kwargs)

    def send(self, request, **kwargs):
        for attempt in range(MAX_RETRIES + 1):
            self.control.wait()
            response = super().send(request, **kwargs)
            if response.status_code != 429:
                return response
            response.close()
            self.control.retry(response.headers.get("Retry-After"), attempt)


class RateLimitedYoutubeDL(YoutubeDL):
    def __init__(self, params: dict, control: RequestControl):
        self.control = control
        # 再試行はこの通信層に集約し、extractor側で回数が増えるのを防ぐ。
        super().__init__({**params, "extractor_retries": 0})

    def urlopen(self, request):
        for attempt in range(MAX_RETRIES + 1):
            self.control.wait()
            try:
                return super().urlopen(request)
            except HTTPError as error:
                if error.status != 429:
                    raise
                error.close()
                self.control.retry(error.response.headers.get("Retry-After"), attempt)
