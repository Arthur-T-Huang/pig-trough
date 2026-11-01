"""Append-only JSONL trend log: one line per API call, written the moment the call finishes."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .http import ApiError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TrendLog:
    def __init__(self, path: Path, echo: bool = True):
        self.path = Path(path)
        self.echo = echo

    def write(self, entry: dict) -> None:
        # Open, append and close per entry so the file is complete up to the last call even if the run dies.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": utc_now(), **entry}, ensure_ascii=False) + "\n")

    def call(self, source: str, call: str, params: dict | None = None) -> CallRecord:
        """`params` is what gets logged, so never put keys, secrets or tokens in it."""
        return CallRecord(self, source, call, dict(params or {}))

    def note(self, message: str) -> None:
        if self.echo:
            print(f"[trends] {message}", flush=True)


class CallRecord:
    """Wraps one API call. On exit the outcome is logged; an ApiError is recorded and swallowed so later calls still run."""

    def __init__(self, log: TrendLog, source: str, call: str, params: dict):
        self.log, self.source, self.call, self.params = log, source, call, params
        self.items: list[dict] = []
        self.meta: dict = {}
        self.data: dict = {}  # raw response, for pagination; not logged
        self.error: ApiError | None = None

    def __enter__(self) -> CallRecord:
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        entry = {
            "event": "call",
            "source": self.source,
            "call": self.call,
            "params": self.params,
            "ok": exc is None,
            "elapsed_ms": int((time.monotonic() - self._start) * 1000),
            **self.meta,
        }
        if isinstance(exc, ApiError):
            self.error = exc
            entry |= {"status": exc.status, "error": str(exc)}
        elif exc is not None:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        entry |= {"count": len(self.items), "items": self.items}
        self.log.write(entry)
        shown = " ".join(f"{k}={v}" for k, v in self.params.items() if k not in ("part", "maxResults", "first"))
        outcome = f"FAILED ({entry['error']})" if exc is not None else f"{len(self.items)} items"
        self.log.note(f"{self.source} {self.call} {shown} -> {outcome}")
        return isinstance(exc, ApiError)
