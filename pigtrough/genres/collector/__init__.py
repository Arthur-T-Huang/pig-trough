"""Collector: timed rounds of grabbing themed collectibles around a generated arena.

The map is static geometry; collectibles are spawned at runtime by the server
from the spawn points written into GameConfig.genre.coinSpawns.
"""

from __future__ import annotations

from ...rbx import Instance, model, pad, part
from ..base import BuildContext, Genre


class _Layout:
    """Rejection sampling of non-overlapping circles on the arena floor."""

    def __init__(self, ctx: BuildContext, half: float) -> None:
        self.rng = ctx.rng
        self.half = half
        self.taken: list[tuple[float, float, float]] = [(0.0, 0.0, 22.0)]  # keep spawn clear

    def place(self, radius: float, margin: float = 4, tries: int = 40) -> tuple[float, float] | None:
        limit = self.half - radius - margin
        for _ in range(tries):
            x, z = self.rng.uniform(-limit, limit), self.rng.uniform(-limit, limit)
            if all((x - ox) ** 2 + (z - oz) ** 2 > (radius + r + margin) ** 2 for ox, oz, r in self.taken):
                self.taken.append((x, z, radius))
                return x, z
        return None


class CollectorGenre(Genre):
    name = "collector"
    description = "Arena with platforms where players race to collect the most items per round"
    defaults = {
        "arenaSize": 220.0,
        "platforms": 10,
        "props": 24,
        "hazardPatches": 4,
        "coinCount": 30,
        "coinRespawnSeconds": 5.0,
        "roundSeconds": 120,
        "intermissionSeconds": 15,
    }

    def validate_params(self, params: dict) -> None:
        if not 80 <= params["arenaSize"] <= 1000:
            raise ValueError("arenaSize must be between 80 and 1000")
        if params["roundSeconds"] < 10 or params["intermissionSeconds"] < 3:
            raise ValueError("roundSeconds must be >= 10 and intermissionSeconds >= 3")

    def build(self, ctx: BuildContext) -> None:
        theme, rng, p = ctx.theme, ctx.rng, ctx.params
        size = p["arenaSize"]
        half = size / 2
        layout = _Layout(ctx, half)
        spawns: list[list[float]] = []

        arena = model("Arena")
        arena.add(pad("Ground", (size, 4, size), (0, 0, 0), theme.color("ground"), theme.material("ground")))
        for i, (x, z, w, d) in enumerate(((0, half + 2, size + 8, 4), (0, -half - 2, size + 8, 4),
                                          (half + 2, 0, 4, size), (-half - 2, 0, 4, size))):
            arena.add(part(f"Wall{i + 1}", (w, 24, d), (x, 12, z), theme.color("secondary"), theme.material("platform")))
        arena.add(pad("SpawnLocation", (12, 1, 12), (0, 1, 0), theme.color("checkpoint"), theme.material("checkpoint"),
                      class_name="SpawnLocation", Neutral=True, Duration=0))
        ctx.add_map_model("Arena", arena)

        platforms = model("Platforms")
        for i in range(p["platforms"]):
            s = rng.uniform(14, 28)
            spot = layout.place(s * 0.75)
            if not spot:
                break
            x, z = spot
            h = 2 * rng.randint(4, 14)
            platforms.add(pad(f"Platform{i + 1}", (s, 1.5, s), (x, h, z), theme.color("primary"), theme.material("platform")))
            platforms.add(part(f"Support{i + 1}", (h, 3, 3), (x, h / 2, z), theme.color("secondary"),
                               theme.material("platform"), Shape="Cylinder", rotation=(0, 0, 90)))
            platforms.add(part(f"Truss{i + 1}", (2, h, 2), (x + s / 2 + 1, h / 2, z), theme.color("accent"),
                               theme.material("truss"), class_name="TrussPart"))
            spawns += [[x + rng.uniform(-s / 3, s / 3), h + 3, z + rng.uniform(-s / 3, s / 3)] for _ in range(2)]
        ctx.add_map_model("Platforms", platforms)

        hazards = model("Hazards")
        for i in range(p["hazardPatches"]):
            w, d = rng.uniform(12, 26), rng.uniform(12, 26)
            spot = layout.place(max(w, d) / 2)
            if spot:
                hazards.add(pad(theme.text("hazardName", "Hazard"), (w, 0.4, d), (spot[0], 0.2, spot[1]),
                                theme.color("hazard"), theme.material("hazard"), tags=["Hazard"]))
        ctx.add_map_model("Hazards", hazards)

        props = model("Props")
        for i in range(p["props"]):
            if rng.random() < 0.5:
                r = rng.uniform(2, 5)
                spot = layout.place(r)
                if spot:
                    props.add(part("Rock", (2 * r, 2 * r, 2 * r), (spot[0], r * 0.4, spot[1]), theme.color("secondary"),
                                   theme.material("platform"), Shape="Ball"))
            else:
                h, r = rng.uniform(6, 16), rng.uniform(1, 2)
                spot = layout.place(r)
                if spot:
                    props.add(part("Pillar", (h, 2 * r, 2 * r), (spot[0], h / 2, spot[1]), theme.color("accent"),
                                   theme.material("accent"), Shape="Cylinder", rotation=(0, 0, 90)))
        ctx.add_map_model("Props", props)

        while len(spawns) < 2 * p["coinCount"]:
            spot = layout.place(1.5, margin=1, tries=20)
            if not spot:
                break
            spawns.append([spot[0], 3, spot[1]])

        ctx.config.update(
            collectible=theme.text("collectible", "Coins"),
            coinCount=p["coinCount"],
            coinRespawnSeconds=p["coinRespawnSeconds"],
            roundSeconds=p["roundSeconds"],
            intermissionSeconds=p["intermissionSeconds"],
            coinSpawns=[[round(c, 2) for c in s] for s in spawns],
        )
