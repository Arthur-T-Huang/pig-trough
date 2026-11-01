# Plan: trend-driven theme generation

Status: proposal · Last checked against platform docs/news: 2026-10-31

## Goal

Pull trend signals from major social platforms, rank the topics that are
rising, and turn the best ones into new `themes/*.json` files that any genre
can use: palette, materials, lighting, atmosphere and flavor text.

What it is **not**: a live dependency of `build`/`serve`. Builds stay
deterministic (same spec → same bytes). Trend fetching is a separate step that
produces reviewed theme files, which then go through the normal pipeline.

```
 sources ──► snapshot (raw signals, dated JSON) ──► normalize + cluster ──► score ──► filter
                                                                                        │
 themes/trend-<slug>.json ◄── validate (load_theme_file) ◄── synthesize (LLM) ◄── top-N concepts
          │
          └─► human review / commit ──► normal `pigtrough new --theme trend-<slug>`
```

## 1. Can we use the platforms' own APIs?

We wanted direct platform APIs. Several platforms don't offer one for this use,
so each platform below has a fallback.

| Platform | Official API usable for trends? | What we use |
| --- | --- | --- |
| **YouTube** | ✅ Yes, free. Data API v3, `videos.list?chart=mostPopular&regionCode=…&videoCategoryId=20` (Gaming). Since July 2025 `mostPopular` draws from the music, movies and gaming charts, not the old curated Trending list. 10k quota units/day. | Direct API. Pull the gaming chart for each region and take keywords from titles and tags. Avoid `search.list` (100 units per call). |
| **Roblox** (target platform) | ⚠️ First-party data, but the endpoint is unofficial. `explore-api.roblox.com/v1/get-sorts` and `get-sort-content` power the home-page charts but are undocumented, need a session ID, and return about 100 games per sort. | Direct but defensive. Low volume, cache everything, read Roblox ToS before use. **This is our most relevant signal**: it shows what themes players are actually choosing right now. |
| **Twitch** | ✅ Yes, free. Helix `Get Top Games` and `Get Streams` with an app access token. | Direct API. Finds which games and genres are rising. Optional source. |
| **Google Trends** | ⚠️ The official Trends API is still an **invite-only alpha** (announced July 2025, no general release). `pytrends` is broken. | Apply for the alpha now. Until approved, use the public "Trending now" RSS feed per region (verify the URL and terms before relying on it). |
| **Instagram** | ⚠️ Only partly usable. Graph API Hashtag Search needs a Business/Creator account plus App Review, allows **30 unique hashtags per rolling 7 days**, and has **no trending or discovery endpoint**. `top_media` and `recent_media` exclude Reels and Stories. | Use it to **validate**, not to discover. After other sources propose candidates, spend the 30 weekly lookups confirming the best ones. |
| **TikTok** | ❌ No. The Research API is limited to academic researchers, bans commercial use and has no trending endpoint. The Display, Login and Content Posting APIs don't expose trends. Creative Center shows trending hashtags and songs on a web page but has no public API. | **Fallback A (default):** skip TikTok in v1. TikTok trends usually spread to YouTube Shorts and Google Trends within days, so those sources cover it. **Fallback B (if budgeted):** a licensed third-party data vendor behind the same adapter interface. Don't scrape TikTok ourselves; it breaks the ToS and the scraper is fragile. |
| **X (Twitter)** | ⚠️ Yes, but paid. Pay-per-use became the default in Feb 2026 and there is no free tier. A trends-by-location endpoint exists. | Optional and low volume: a few trend calls per day should cost very little. Check current per-call pricing on docs.x.com first. |
| **Pinterest** | ⚠️ A Trends API exists (`/v5/trends/keywords/{region}/top/{type}`, 50 results, today only), but access is limited to partners and enterprise clients. | Apply for access. It is the best source for **aesthetics** (color and style trends match our palette and lighting fields). Optional until approved. |
| **Reddit** | ⚠️ Free tier is 100 QPM but needs manual approval and is non-commercial only. Reports say new requests may close around now (unconfirmed). | Optional. Useful for r/roblox and r/RobloxDevelopers vocabulary. Only add it if approval is still open and our use counts as non-commercial. |

**v1 sources:** Roblox + YouTube + Google Trends (RSS, then the API once approved)
+ a **manual source** (a hand-edited CSV of seasonal events such as Halloween, the
summer break and big movie releases). All of these are free and need no approval.
Twitch, X, Pinterest and the Instagram validator plug in later through the same
interface.

## 2. Architecture (fits the existing codebase)

Keep the stdlib-only rule. HTTP uses `urllib.request` and JSON uses `json`. The
LLM call is the only thing that might need an optional extra (`pip install
pigtrough[trends]`), or it can also use `urllib`.

```
pigtrough/trends/
  __init__.py
  signal.py        TrendSignal dataclass + snapshot read/write
  sources/
    base.py        Source protocol: name, fetch(region, now) -> list[TrendSignal]
    youtube.py  roblox.py  google_trends.py  manual.py
    twitch.py  x.py  pinterest.py  instagram.py   (later)
  normalize.py     term cleanup, alias merge, concept clustering
  score.py         ranking (section 3)
  safety.py        IP / brand / Roblox-community-standards filter
  synthesize.py    concept -> theme JSON (LLM) + repair loop
trends/
  snapshots/2026-10-31.json     raw signals, committed or gitignored (team decision)
  manual.csv                    seasonal and editorial signals
```

```python
@dataclass(frozen=True)
class TrendSignal:
    source: str        # "youtube", "roblox", ...
    term: str          # raw text: hashtag, game title, query
    metric: str        # "views", "ccu", "rank", "search_index", ...
    value: float
    region: str        # "US", "GB", ...
    observed_at: str   # ISO date
    url: str | None = None
```

Credentials come from env vars, following the `PIGTROUGH_*` convention:
`PIGTROUGH_YOUTUBE_KEY`, `PIGTROUGH_TWITCH_CLIENT_ID/SECRET`,
`PIGTROUGH_X_BEARER`, and so on. A source with no credentials is skipped with a
warning, never a crash.

**CLI** (added to `cli.py`):

| Command | Does |
| --- | --- |
| `trends fetch [--region US] [--sources a,b]` | Runs the adapters and writes today's snapshot |
| `trends report [--top 20]` | Prints the scored concept list with evidence per source |
| `trends theme <concept> \| --top N` | Synthesizes, validates and writes `themes/trend-<slug>.json` |

## 3. The algorithm

**Step 1: Collect.** Each adapter returns `TrendSignal`s. Only raw data goes
into the snapshot, so we can re-score old days without re-fetching.

**Step 2: Normalize and cluster terms into *concepts*.**
- Clean up the text: lowercase, strip `#`/emoji/`[UPDATE]`/`🎃 EVENT` tags,
  split camelCase hashtags.
- Merge aliases ("halloween", "spooky", "trick or treat" → `halloween`). Start
  with a small alias table and add an LLM clustering pass over the day's top
  ~200 terms. Cache its output in the snapshot so reruns stay deterministic.
- Roblox game titles are noisy ("[🎃] Grow a Garden 🌱"), so pull theme nouns
  out of them, not the title itself.

**Step 3: Score each concept.** We care about *velocity* and *fit*, not raw
volume. Volume alone would rank "Minecraft" first forever.

```
velocity_s(c) = z-score of c's metric today vs. its trailing 14-day history in source s
                (a new entry with no history gets a fixed "new arrival" score)

score(c) =  Σ_s  w_s · clip(velocity_s(c), -3, 3)       # rising in each source
          + β · (#sources where c is rising − 1)         # cross-platform agreement
          + γ · roblox_fit(c)                            # does it show up in Roblox charts?
          + δ · season(c, today)                         # manual calendar boost/decay
          − ε · saturation(c)                            # already many top Roblox games on it
          − ∞ · blocked(c)                               # safety / IP filter
```

- Starting weights: Roblox 0.35, YouTube 0.25, Google Trends 0.2, others split
  the rest. Keep the weights in a JSON file so we can tune them without code
  changes.
- `roblox_fit` rewards concepts that already appear in Roblox charts or
  titles. A topic that is huge on TikTok but has no game version yet scores
  lower on fit and higher on opportunity, so `report` shows both columns.
- `saturation` keeps us out of themes where the top 10 games already dominate.
- Use exponential decay (half-life about 5 days) so a one-day spike doesn't
  win.

**Step 4: Filter (`safety.py`). Required, not optional.**
- Drop trademarked IP, characters, brands and real people (Roblox moderation
  and copyright risk). A blocklist plus an LLM yes/no check is enough to start.
- Drop topics that break Roblox Community Standards: violence against real
  groups, tragedies and news events, politics, adult content.
- Drop concepts that are near-duplicates of existing `themes/*.json`.

**Step 5: Synthesize the theme.** For each concept that passes:
- Prompt an LLM with the concept, its evidence (top terms and example titles)
  and the **exact theme contract**: the 7 required palette keys, `materials`
  values from an allow-list of `Enum.Material` names, `lighting` and
  `atmosphere` keys copied from the existing themes, and the 5 `flavor` keys.
  Ask for structured JSON output.
- Validate with `themes.load_theme_file` plus a material allow-list and a
  contrast check (`hazard` must stand out from `ground` and `primary`; `goal`
  must be visible in fog). On failure, send the errors back to the LLM, at
  most 2 repair rounds.
- Write `themes/trend-<slug>.json` with an extra `"provenance"` block (concept,
  score, sources, snapshot date). `load_theme_file` ignores unknown keys, so it
  needs no change.

**Step 6: Human gate.** Someone reviews generated themes before they're
committed or used in a published game. The `tests/` suite already builds every
genre against every theme, so a committed trend theme gets tested
automatically.

## 4. Known limitation

The theme schema only covers colors, materials, lighting and text. Many current
Roblox trends are about **objects and mechanics** (gardens, pets, "brainrot"
characters), and a palette can't express those. The trend report will often
suggest things we can't build yet. This connects to the README's "richer
per-theme props" and "mesh and asset support" next steps. Plan for `report` to
also tag each concept with a suggested *genre*, since that input will matter
once more genres exist.

## 5. Phases

| Phase | Scope | Done when |
| --- | --- | --- |
| **P0** | `TrendSignal`, snapshot I/O, Source protocol; `manual`, `youtube`, `roblox`, `google_trends` (RSS) adapters; `trends fetch` | A dated snapshot with three or more sources is written. Adapters are tested against recorded fixture responses (no network in tests). |
| **P1** | normalize + score + safety; `trends report` | The ranked list with per-source evidence looks reasonable to a human over a week of snapshots |
| **P2** | synthesize + validation/repair; `trends theme` | Generated themes pass `check` for every genre |
| **P3** | Gated sources as approvals arrive: Google Trends API, Pinterest, Twitch, X, Instagram validator | Each one is a single adapter file plus a weight |
| **P4** | TikTok via a vendor (if budgeted); feedback loop: compare published games' Roblox analytics with the scores and re-tune weights | — |

**Start today**, because approvals take weeks: apply for the Google Trends API
alpha, Pinterest Trends access, a Meta app with Instagram Public Content Access
review, and a Reddit token (if still open).

## 6. Open decisions

1. **Commercial or not?** This decides whether the Reddit free tier is allowed
   and rules out TikTok Research for good. We assume commercial.
2. **Data budget.** Is $0 a hard limit? If not, X pay-per-use (small) and a
   TikTok vendor (larger) become options.
3. **Snapshots in git?** Committing them gives reproducibility and history for
   the z-scores. Ignoring them keeps the repo small. Suggestion: commit the
   scored summaries and ignore the raw data.
4. **Roblox explore-api risk.** It is unofficial and may break or conflict with
   the ToS. Is that acceptable for a low-volume, cached internal tool?
