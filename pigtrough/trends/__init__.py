"""Trend collection: trending videos and streams from YouTube and Twitch, logged to a JSONL file.

Every API call appends one line to the log as soon as it finishes. The run ends with a
`summary` line that ranks tags, hashtags and title terms across everything collected.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .log import TrendLog
from .topics import format_summary, summarize
from .twitch import TwitchSource
from .youtube import YouTubeSource

DEFAULT_LOG_DIR = Path("trends") / "logs"


def default_log_path() -> Path:
    return DEFAULT_LOG_DIR / f"trends-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.jsonl"


def load_env_file(path: Path = Path(".env")) -> None:
    """Read KEY=value lines into os.environ. Variables already set in the shell take precedence."""
    if not path.is_file():
        return
    for line in path.read_text("utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def collect(sources: list, log: TrendLog, top: int = 15, skipped: dict[str, str] | None = None) -> dict:
    log.write({"event": "run_start", "sources": [s.name for s in sources], "skipped": skipped or {}})
    collected = {source.name: source.collect(log) for source in sources}
    summary = summarize(collected, top)
    log.write({"event": "summary", **summary})
    return summary


__all__ = ["TrendLog", "TwitchSource", "YouTubeSource", "collect", "default_log_path", "format_summary",
           "load_env_file", "summarize"]
