import json
import tempfile
import unittest
from pathlib import Path

from pigtrough.trends import TrendLog, TwitchSource, YouTubeSource, collect
from pigtrough.trends.http import ApiError, Response
from pigtrough.trends.topics import Tally, summarize, title_terms


class FakeHttp:
    """Routes requests to `handler(method, url, params, headers)`; records every request."""

    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def get(self, url, params=None, headers=None):
        return self._send("GET", url, params or {}, headers or {})

    def post_form(self, url, form):
        return self._send("POST", url, form, {})

    def _send(self, method, url, params, headers):
        self.requests.append((method, url, params, headers))
        return Response(self.handler(method, url, params, headers), 200, 1)


def yt_video(vid, title, views, channel="chan", tags=(), description=""):
    return {"id": vid, "snippet": {"title": title, "channelTitle": channel, "tags": list(tags),
                                   "description": description, "publishedAt": "2026-10-30T00:00:00Z"},
            "statistics": {"viewCount": str(views), "likeCount": "10"}}


def read_log(path):
    return [json.loads(line) for line in Path(path).read_text("utf-8").splitlines()]


class TrendTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = TrendLog(Path(tmp.name) / "logs" / "run.jsonl", echo=False)


class YouTube(TrendTestCase):
    def handler(self, method, url, params, headers):
        if url.endswith("/search"):
            return {"items": [{"id": {"videoId": "s1"}, "snippet": {"title": "Grow a Garden &amp; more"}}]}
        if params.get("chart") == "mostPopular":
            return {"items": [yt_video("c1", "Spooky Halloween Obby", 50_000, "A", ["Halloween", "obby"],
                                       "#halloween #roblox"),
                              yt_video("c2", "Halloween obby speedrun", 9_000, "B", ["halloween"])]}
        return {"items": [yt_video("s1", "Grow a Garden & more", 1_000_000, "C", ["grow a garden"])]}

    def test_chart_and_search_are_logged_per_call_without_the_key(self):
        http = FakeHttp(self.handler)
        source = YouTubeSource("SECRET-KEY", http, regions=["US"], searches=["roblox"])
        videos = collect([source], self.log)["youtube"]
        entries = read_log(self.log.path)
        self.assertEqual([e["event"] for e in entries], ["run_start", "call", "call", "call", "summary"])
        self.assertEqual([e["call"] for e in entries[1:4]], ["videos.list:mostPopular", "search.list", "videos.list"])
        self.assertEqual(entries[2]["items"][0]["title"], "Grow a Garden & more")  # HTML entities decoded
        self.assertEqual(entries[3]["params"]["id"], "s1")
        self.assertEqual(source.units_used, 102)
        self.assertNotIn("SECRET-KEY", self.log.path.read_text("utf-8"))
        self.assertTrue(all(req[2]["key"] == "SECRET-KEY" for req in http.requests))
        self.assertEqual(videos["videos"], 3)
        self.assertEqual(entries[1]["items"][0]["hashtags"], ["halloween", "roblox"])
        self.assertEqual(videos["top_tags"][0]["term"], "halloween")  # two channels; "obby" only one

    def test_log_is_written_after_each_call(self):
        seen = []

        def handler(method, url, params, headers):
            seen.append(len(self.log.path.read_text("utf-8").splitlines()) if self.log.path.exists() else 0)
            return {"items": [yt_video(f"v{len(seen)}", "t", 1)], "nextPageToken": "next"}

        YouTubeSource("k", FakeHttp(handler), chart_pages=3, searches=[]).collect(self.log)
        self.assertEqual(seen, [0, 1, 2])

    def test_quota_exhaustion_stops_remaining_calls(self):
        def handler(method, url, params, headers):
            raise ApiError(403, "The request cannot be completed because you have exceeded your quota.")

        http = FakeHttp(handler)
        videos = YouTubeSource("k", http, regions=["US", "GB"], searches=["roblox"]).collect(self.log)
        self.assertEqual(videos, [])
        self.assertEqual(len(http.requests), 1)
        entry = read_log(self.log.path)[0]
        self.assertEqual((entry["ok"], entry["status"]), (False, 403))

    def test_failed_call_does_not_stop_other_regions(self):
        def handler(method, url, params, headers):
            if params["regionCode"] == "XX":
                raise ApiError(400, "Invalid region")
            return {"items": [yt_video("v1", "t", 5)]}

        videos = YouTubeSource("k", FakeHttp(handler), regions=["XX", "US"], searches=[]).collect(self.log)
        self.assertEqual([v["region"] for v in videos], ["US"])


class Twitch(TrendTestCase):
    def handler(self, method, url, params, headers):
        if url.endswith("/oauth2/token"):
            return {"access_token": "TOKEN", "expires_in": 5000}
        self.assertEqual(headers["Authorization"], "Bearer TOKEN")
        if url.endswith("/games/top"):
            return {"data": [{"id": "1", "name": "Just Chatting"}, {"id": "23020", "name": "Roblox"}]}
        if url.endswith("/games"):
            return {"data": [{"id": "23020", "name": params["name"]}]}
        page = 2 if params.get("after") else 1
        return {"data": [{"id": f"st{page}", "user_name": f"u{page}", "user_login": f"u{page}", "game_name": "Roblox",
                          "title": "Halloween event grind", "tags": ["English", "Halloween"], "viewer_count": 100}],
                "pagination": {"cursor": "c"} if page == 1 else {}}

    def test_streams_paginate_and_secrets_stay_out_of_the_log(self):
        source = TwitchSource("CLIENT", "SHH-SECRET", FakeHttp(self.handler), games=["Roblox"], stream_pages=5)
        summary = collect([source], self.log)["twitch"]
        calls = [e["call"] for e in read_log(self.log.path) if e["event"] == "call"]
        self.assertEqual(calls, ["oauth2/token", "games/top", "games", "streams:Roblox", "streams:Roblox"])
        text = self.log.path.read_text("utf-8")
        self.assertNotIn("SHH-SECRET", text)
        self.assertNotIn("TOKEN", text.replace("oauth2/token", ""))
        self.assertEqual(summary["streams"], 2)
        self.assertEqual(summary["top_games"], ["Just Chatting", "Roblox"])
        self.assertEqual([t["term"] for t in summary["top_tags"]], ["halloween"])  # "english" is noise

    def test_bad_credentials_are_logged_and_skip_the_rest(self):
        def handler(method, url, params, headers):
            raise ApiError(400, "invalid client secret")

        http = FakeHttp(handler)
        self.assertEqual(TwitchSource("c", "s", http).collect(self.log), [])
        self.assertEqual(len(http.requests), 1)
        self.assertIn("invalid client secret", read_log(self.log.path)[0]["error"])


class Topics(unittest.TestCase):
    def test_title_terms(self):
        self.assertEqual(title_terms("I Built a HUGE Pet Farm in Roblox! (Part 2)"),
                         {"built", "huge", "pet", "farm", "huge pet", "pet farm"})  # no pair across "a"

    def test_tally_counts_each_creator_once(self):
        tally = Tally()
        for _ in range(5):
            tally.add("spam", 3.0, "one-channel")
        tally.add("real", 1.0, "a")
        tally.add("real", 1.0, "b")
        self.assertEqual([r["term"] for r in tally.top(5)], ["real"])

    def test_cross_platform_terms(self):
        yt = [{"id": "1", "title": "zombie survival", "channel": "a", "views": 10, "url": ""},
              {"id": "2", "title": "zombie tower", "channel": "b", "views": 10, "url": ""}]
        tw = [{"kind": "stream", "id": "s", "title": "zombie grind", "user": "u", "viewers": 3, "url": ""}]
        shared = summarize({"youtube": yt, "twitch": tw})["cross_platform"]
        self.assertEqual([r["term"] for r in shared], ["zombie"])


if __name__ == "__main__":
    unittest.main()
