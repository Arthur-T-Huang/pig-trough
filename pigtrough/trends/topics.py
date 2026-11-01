"""Rank tags, hashtags and title terms across collected YouTube videos and Twitch streams.

Each item is weighted by 1 + log10(1 + views/viewers), so one viral video can't drown out the rest.
A term counts once per channel/streamer, so creators who paste the same tag list on every
upload don't dominate.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from itertools import pairwise

WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
STOPWORDS = frozenset("""
    a an and are as at be but by can do for from get got has have how i i'm if in into is it it's its just me my
    new no not now of on or our out so than that the their them then there this to too up us vs was we what when
    who why will with you your
""".split())
# Words found in nearly all gaming content (or Twitch language tags) that say nothing about a theme.
NOISE = frozenset("""
    game games gaming gameplay play playing played video videos live stream streaming streamer twitch youtube
    shorts short roblox channel subscribe episode ep part full english español spanish deutsch german français
    french português portuguese 日本語 japanese 한국어 korean русский russian italiano italian
""".split())


def normalize_tag(tag: str) -> str:
    tag = " ".join(tag.lower().lstrip("#").split())
    return "" if tag in STOPWORDS or tag in NOISE or tag.isdigit() else tag


def title_terms(text: str) -> set[str]:
    """Words and adjacent-word pairs from a title, without stopwords, noise, numbers or single letters."""
    words = [w for w in WORD.findall(text.lower()) if not w.isdigit()]
    keep = [w not in STOPWORDS and w not in NOISE and len(w) > 1 for w in words]
    found = {w for w, k in zip(words, keep) if k}
    found |= {f"{a} {b}" for (a, ka), (b, kb) in pairwise(zip(words, keep)) if ka and kb}
    return found


class Tally:
    """Score per term = sum over distinct creators of that creator's best item weight."""

    def __init__(self):
        self._best: dict[tuple[str, str], float] = {}

    def add(self, term: str, weight: float, creator: str) -> None:
        if term:
            key = (term, creator)
            self._best[key] = max(self._best.get(key, 0.0), weight)

    def scores(self, min_creators: int = 2) -> dict[str, tuple[float, int]]:
        totals: dict[str, list] = defaultdict(lambda: [0.0, 0])
        for (term, _), weight in self._best.items():
            totals[term][0] += weight
            totals[term][1] += 1
        return {t: (s, n) for t, (s, n) in totals.items() if n >= min_creators}

    def top(self, n: int, min_creators: int = 2) -> list[dict]:
        scored = self.scores(min_creators)
        ranked = sorted(scored, key=lambda t: (-scored[t][0], t))[:n]
        return [{"term": t, "score": round(scored[t][0], 2), "creators": scored[t][1]} for t in ranked]


def _weight(count: int) -> float:
    return 1 + math.log10(1 + max(count, 0))


def _dedupe(items: list[dict], metric: str) -> list[dict]:
    """The same video can come back from several regions/queries; keep one copy, with its highest count."""
    best: dict[str, dict] = {}
    for item in items:
        if item["id"] not in best or item[metric] > best[item["id"]][metric]:
            best[item["id"]] = item
    return list(best.values())


def _tallies(items: list[dict], metric: str, creator: str, hashtags: bool) -> dict[str, Tally]:
    out = {"tags": Tally(), "title_terms": Tally()} | ({"hashtags": Tally()} if hashtags else {})
    for item in items:
        w, who = _weight(item[metric]), item.get(creator) or item["id"]
        for tag in item.get("tags", []):
            out["tags"].add(normalize_tag(tag), w, who)
        for term in title_terms(item.get("title", "")):
            out["title_terms"].add(term, w, who)
        for tag in item.get("hashtags", []) if hashtags else ():
            out["hashtags"].add(normalize_tag(tag), w, who)
    return out


def _cross_platform(per_source: dict[str, dict[str, Tally]], top: int) -> list[dict]:
    """Terms (tag or title term) seen on more than one platform, ranked by the sum of per-platform normalized scores."""
    normalized: dict[str, dict[str, float]] = {}
    for source, tallies in per_source.items():
        merged: dict[str, float] = defaultdict(float)
        for tally in tallies.values():
            for term, (score, _) in tally.scores(min_creators=1).items():
                merged[term] = max(merged[term], score)
        peak = max(merged.values(), default=1.0)
        normalized[source] = {t: s / peak for t, s in merged.items()}
    if len(normalized) < 2:
        return []
    shared = set.intersection(*(set(terms) for terms in normalized.values()))
    ranked = sorted(shared, key=lambda t: (-sum(n[t] for n in normalized.values()), t))[:top]
    return [{"term": t, "score": round(sum(n[t] for n in normalized.values()), 3),
             **{s: round(n[t], 3) for s, n in normalized.items()}} for t in ranked]


def summarize(collected: dict[str, list[dict]], top: int = 15) -> dict:
    summary: dict = {}
    per_source: dict[str, dict[str, Tally]] = {}
    if "youtube" in collected:
        videos = _dedupe(collected["youtube"], "views")
        tallies = per_source["youtube"] = _tallies(videos, "views", "channel", hashtags=True)
        summary["youtube"] = {
            "videos": len(videos),
            **{f"top_{k}": t.top(top) for k, t in tallies.items()},
            "most_viewed": [{"title": v["title"], "views": v["views"], "url": v["url"]}
                            for v in sorted(videos, key=lambda v: -v["views"])[:5]],
        }
    if "twitch" in collected:
        items = collected["twitch"]
        streams = _dedupe([i for i in items if i["kind"] == "stream"], "viewers")
        tallies = per_source["twitch"] = _tallies(streams, "viewers", "user", hashtags=False)
        summary["twitch"] = {
            "streams": len(streams),
            "top_games": [g["name"] for g in items if g["kind"] == "top_game"][:top],
            **{f"top_{k}": t.top(top) for k, t in tallies.items()},
            "most_watched": [{"title": s["title"], "viewers": s["viewers"], "url": s["url"]}
                             for s in sorted(streams, key=lambda s: -s["viewers"])[:5]],
        }
    summary["cross_platform"] = _cross_platform(per_source, top)
    return summary


def format_summary(summary: dict, per_list: int = 10) -> str:
    def terms(rows):
        return ", ".join(r["term"] for r in rows[:per_list]) or "(none)"

    lines = []
    if yt := summary.get("youtube"):
        lines += [f"YouTube ({yt['videos']} videos)",
                  f"  tags:        {terms(yt['top_tags'])}",
                  f"  hashtags:    {terms(yt['top_hashtags'])}",
                  f"  title terms: {terms(yt['top_title_terms'])}"]
    if tw := summary.get("twitch"):
        lines += [f"Twitch ({tw['streams']} streams)",
                  f"  top games:   {', '.join(tw['top_games'][:per_list]) or '(none)'}",
                  f"  tags:        {terms(tw['top_tags'])}",
                  f"  title terms: {terms(tw['top_title_terms'])}"]
    if summary.get("cross_platform"):
        lines.append(f"On both platforms: {terms(summary['cross_platform'])}")
    return "\n".join(lines)
