"""YouTube Data API v3: the most-popular chart for a category, plus recent top videos for keyword searches."""

from __future__ import annotations

import html
import os
import re
from datetime import datetime, timedelta, timezone

from .http import Http
from .log import CallRecord, TrendLog

API = "https://www.googleapis.com/youtube/v3"
GAMING_CATEGORY = "20"
ENV_KEY = "PIGTROUGH_YOUTUBE_KEY"
HASHTAG = re.compile(r"#(\w+)")

# Quota cost per call (default daily quota is 10,000 units).
CHART_UNITS, SEARCH_UNITS, VIDEOS_UNITS = 1, 100, 1


def _video(v: dict, region: str, kind: str) -> dict:
    snippet, stats = v.get("snippet", {}), v.get("statistics", {})
    text = f"{snippet.get('title', '')} {snippet.get('description', '')}"
    return {
        "kind": kind,
        "id": v.get("id"),
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "published": snippet.get("publishedAt"),
        "tags": snippet.get("tags", []),
        "hashtags": sorted({h.lower() for h in HASHTAG.findall(text) if not h.isdigit()}),
        "language": snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
        "region": region,
        "url": f"https://www.youtube.com/watch?v={v.get('id')}",
    }


class YouTubeSource:
    name = "youtube"

    def __init__(self, api_key: str, http: Http | None = None, regions=("US",), category: str = GAMING_CATEGORY,
                 chart_pages: int = 1, searches=("roblox",), search_days: int = 7):
        self.api_key = api_key
        self.http = http or Http()
        self.regions = list(regions)
        self.category = category
        self.chart_pages = chart_pages
        self.searches = [q for q in searches if q]
        self.search_days = search_days
        self.units_used = 0
        self._quota_exhausted = False

    @classmethod
    def from_env(cls, **kwargs) -> YouTubeSource | None:
        key = os.environ.get(ENV_KEY)
        return cls(key, **kwargs) if key else None

    def collect(self, log: TrendLog) -> list[dict]:
        videos = []
        for region in self.regions:
            videos += self._chart(log, region)
            for query in self.searches:
                videos += self._search(log, region, query)
        log.note(f"youtube: {len(videos)} videos, ~{self.units_used} quota units used")
        return videos

    def _get(self, log: TrendLog, call: str, endpoint: str, params: dict, units: int, parse) -> CallRecord | None:
        """One logged request; None once the daily quota is known to be gone."""
        if self._quota_exhausted:
            return None
        self.units_used += units
        with log.call(self.name, call, params) as rec:
            rec.meta["quota_units"] = units
            rec.data = self.http.get(f"{API}/{endpoint}", {**params, "key": self.api_key}).data
            rec.items = parse(rec.data)
        if rec.error and "quota" in str(rec.error).lower():
            self._quota_exhausted = True
            log.note("youtube: daily quota exhausted; skipping the remaining YouTube calls")
        return rec

    def _chart(self, log: TrendLog, region: str) -> list[dict]:
        videos, token = [], None
        for _ in range(self.chart_pages):
            params = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region,
                      "videoCategoryId": self.category, "maxResults": 50}
            if token:
                params["pageToken"] = token
            rec = self._get(log, "videos.list:mostPopular", "videos", params, CHART_UNITS,
                            lambda d: [_video(v, region, "chart") for v in d.get("items", [])])
            if rec is None:
                break
            videos += rec.items
            token = rec.data.get("nextPageToken")
            if not token:
                break
        return videos

    def _search(self, log: TrendLog, region: str, query: str) -> list[dict]:
        """search.list finds the most-viewed recent videos; a follow-up videos.list fetches their tags and stats."""
        since = datetime.now(timezone.utc) - timedelta(days=self.search_days)
        params = {"part": "snippet", "q": query, "type": "video", "order": "viewCount",
                  "publishedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "regionCode": region, "maxResults": 50}
        found = self._get(log, "search.list", "search", params, SEARCH_UNITS, lambda d: [
            {"id": i["id"]["videoId"], "title": html.unescape(i.get("snippet", {}).get("title", ""))}
            for i in d.get("items", []) if i.get("id", {}).get("videoId")
        ])
        if found is None or not found.items:
            return []
        params = {"part": "snippet,statistics", "id": ",".join(v["id"] for v in found.items)}
        details = self._get(log, "videos.list", "videos", params, VIDEOS_UNITS,
                            lambda d: [_video(v, region, f"search:{query}") for v in d.get("items", [])])
        return details.items if details else []
