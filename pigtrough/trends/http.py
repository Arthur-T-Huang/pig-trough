"""Minimal JSON-over-HTTPS client (stdlib only) shared by the trend sources."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

USER_AGENT = "pigtrough-trends/0.1"


class ApiError(RuntimeError):
    """A failed request. `status` is the HTTP status, or 0 when the server was never reached."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status = status


@dataclass(frozen=True)
class Response:
    data: dict
    status: int
    elapsed_ms: int


def _error_message(body: bytes) -> str:
    """Pull the readable message out of a YouTube (`error.message`) or Twitch (`message`) error body."""
    try:
        data = json.loads(body)
    except ValueError:
        return body.decode("utf-8", "replace")[:200] or "no response body"
    error = data.get("error")
    if isinstance(error, dict):
        return error.get("message") or json.dumps(error)[:200]
    return data.get("message") or str(error or data)[:200]


class Http:
    def __init__(self, timeout: float = 20):
        self.timeout = timeout

    def get(self, url: str, params: dict | None = None, headers: dict | None = None) -> Response:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._send(urllib.request.Request(url, headers=headers or {}))

    def post_form(self, url: str, form: dict) -> Response:
        body = urllib.parse.urlencode(form).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        return self._send(urllib.request.Request(url, data=body, headers=headers, method="POST"))

    def _send(self, req: urllib.request.Request) -> Response:
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body, status = resp.read(), resp.status
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, _error_message(e.read())) from None
        except OSError as e:  # URLError, timeouts, connection resets
            raise ApiError(0, f"request failed: {getattr(e, 'reason', e)}") from None
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            raise ApiError(status, "response was not JSON") from None
        return Response(data, status, int((time.monotonic() - start) * 1000))
