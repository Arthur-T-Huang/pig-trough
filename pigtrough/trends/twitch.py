"""Twitch Helix: the top games overall, plus live streams (titles, tags, viewers) for chosen games."""

from __future__ import annotations

import os

from .http import ApiError, Http
from .log import CallRecord, TrendLog

AUTH_URL = "https://id.twitch.tv/oauth2/token"
API = "https://api.twitch.tv/helix"
ENV_ID, ENV_SECRET = "PIGTROUGH_TWITCH_CLIENT_ID", "PIGTROUGH_TWITCH_CLIENT_SECRET"


def _stream(s: dict) -> dict:
    return {
        "kind": "stream",
        "id": s.get("id"),
        "user": s.get("user_name"),
        "game": s.get("game_name"),
        "title": s.get("title", ""),
        "tags": s.get("tags") or [],
        "viewers": s.get("viewer_count", 0),
        "language": s.get("language"),
        "started": s.get("started_at"),
        "url": f"https://www.twitch.tv/{s.get('user_login')}",
    }


class TwitchSource:
    name = "twitch"

    def __init__(self, client_id: str, client_secret: str, http: Http | None = None, games=("Roblox",),
                 stream_pages: int = 3):
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http or Http()
        self.games = [g for g in games if g]
        self.stream_pages = stream_pages
        self._token: str | None = None

    @classmethod
    def from_env(cls, **kwargs) -> TwitchSource | None:
        client_id, secret = os.environ.get(ENV_ID), os.environ.get(ENV_SECRET)
        return cls(client_id, secret, **kwargs) if client_id and secret else None

    def collect(self, log: TrendLog) -> list[dict]:
        if not self._authenticate(log):
            return []
        items = self._top_games(log)
        for name in self.games:
            game = self._find_game(log, name)
            if game:
                items += self._streams(log, game)
        log.note(f"twitch: {sum(i['kind'] == 'stream' for i in items)} streams across {len(self.games)} game(s)")
        return items

    def _authenticate(self, log: TrendLog) -> bool:
        """App access token via the client-credentials flow. Only the grant type is logged."""
        with log.call(self.name, "oauth2/token", {"grant_type": "client_credentials"}) as rec:
            data = self.http.post_form(AUTH_URL, {"client_id": self.client_id, "client_secret": self.client_secret,
                                                  "grant_type": "client_credentials"}).data
            if not data.get("access_token"):
                raise ApiError(200, "token response had no access_token")
            self._token = data["access_token"]
            rec.meta["expires_in"] = data.get("expires_in")
        return self._token is not None

    def _get(self, log: TrendLog, call: str, endpoint: str, params: dict, parse) -> CallRecord:
        headers = {"Client-Id": self.client_id, "Authorization": f"Bearer {self._token}"}
        with log.call(self.name, call, params) as rec:
            rec.data = self.http.get(f"{API}/{endpoint}", params, headers).data
            rec.items = parse(rec.data)
        return rec

    def _top_games(self, log: TrendLog) -> list[dict]:
        return self._get(log, "games/top", "games/top", {"first": 100}, lambda d: [
            {"kind": "top_game", "rank": rank, "id": g.get("id"), "name": g.get("name")}
            for rank, g in enumerate(d.get("data", []), 1)
        ]).items

    def _find_game(self, log: TrendLog, name: str) -> dict | None:
        rec = self._get(log, "games", "games", {"name": name},
                        lambda d: [{"id": g.get("id"), "name": g.get("name")} for g in d.get("data", [])])
        if not rec.items and not rec.error:
            log.note(f"twitch: no game named {name!r} (names must match the Twitch category exactly)")
        return rec.items[0] if rec.items else None

    def _streams(self, log: TrendLog, game: dict) -> list[dict]:
        """Live streams in a category, most-watched first; each page of 100 is its own logged call."""
        streams, cursor = [], None
        for _ in range(self.stream_pages):
            params = {"game_id": game["id"], "first": 100}
            if cursor:
                params["after"] = cursor
            rec = self._get(log, f"streams:{game['name']}", "streams", params,
                            lambda d: [_stream(s) for s in d.get("data", [])])
            streams += rec.items
            cursor = rec.data.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return streams
