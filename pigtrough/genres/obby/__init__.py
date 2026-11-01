"""Obby: a linear obstacle course of procedurally chosen segments with checkpoints.

The course runs along +Z. A cursor tracks the top-centre of the last walkable
pad; each segment appends pads relative to it. Behaviour is attached by tags
(Hazard, Mover, Spinner, Fader, Checkpoint, Finish) handled by the Luau runtime.
"""

from __future__ import annotations

import math

from ...rbx import Instance, model, pad, part, udim2, vector3
from ..base import BuildContext, Genre

# Segment pools are ordered easiest -> hardest; later stages unlock more of the pool.
DIFFICULTY = {
    "easy": dict(gap=(3, 5), rise=(-1, 1.5), spin=(50, 70), period=(5, 6), fade=1.0, beam=2.0,
                 pool=("jumps", "stones", "beam", "truss", "movers")),
    "medium": dict(gap=(4, 7), rise=(-1, 2.5), spin=(70, 110), period=(3.5, 5), fade=0.7, beam=1.6,
                   pool=("jumps", "stones", "truss", "beam", "movers", "faders", "spinner")),
    "hard": dict(gap=(6, 9), rise=(-1, 3), spin=(110, 160), period=(2.5, 3.5), fade=0.45, beam=1.2,
                 pool=("jumps", "stones", "beam", "truss", "movers", "faders", "spinner")),
}
MAX_PART = 2000  # Roblox caps part dimensions at 2048 studs


def billboard(text: str, color, height: float = 2.0) -> Instance:
    gui = Instance("BillboardGui", "Sign", {
        "Size": udim2(0, 200, 0, 50),
        "StudsOffset": [0, height, 0],
        "MaxDistance": 150,
    })
    gui.add(Instance("TextLabel", "Label", {
        "Size": udim2(1, 0, 1, 0),
        "BackgroundTransparency": 1,
        "Text": text,
        "TextScaled": True,
        "TextColor3": color,
        "TextStrokeTransparency": 0.2,
        "Font": "FredokaOne",
    }))
    return gui


class _Course:
    def __init__(self, ctx: BuildContext, start_height: float) -> None:
        self.ctx = ctx
        self.theme = ctx.theme
        self.rng = ctx.rng
        self.diff = DIFFICULTY[ctx.params["difficulty"]]
        self.x, self.y, self.z, self.half = 0.0, start_height, 0.0, 8.0
        self.bounds = [0.0, 0.0, 0.0, 0.0, start_height]  # min x, max x, min z, max z, min y

    def _track(self, x: float, y: float, z: float, size) -> None:
        b = self.bounds
        b[0] = min(b[0], x - size[0]); b[1] = max(b[1], x + size[0])
        b[2] = min(b[2], z - size[2]); b[3] = max(b[3], z + size[2])
        b[4] = min(b[4], y)

    def gap(self, t: float, scale: float = 1.0) -> float:
        lo, hi = self.diff["gap"]
        return scale * (lo + (hi - lo) * self.rng.random() * (0.5 + 0.5 * t))

    def rise(self) -> float:
        return self.rng.uniform(*self.diff["rise"])

    def next_pad(self, m: Instance, name: str, size, gap: float, rise: float = 0.0, dx: float = 0.0,
                 color: str = "primary", material: str = "platform", **kw) -> Instance:
        x, y = self.x + dx, self.y + rise
        z = self.z + self.half + gap + size[2] / 2
        inst = m.add(pad(name, size, (x, y, z), self.theme.color(color), self.theme.material(material), **kw))
        self.x, self.y, self.z, self.half = x, y, z, size[2] / 2
        self._track(x, y, z, size)
        return inst

    # --- segments -----------------------------------------------------------------

    def jumps(self, m: Instance, t: float) -> None:
        for i in range(self.rng.randint(3, 5)):
            s = self.rng.uniform(5, 7)
            self.next_pad(m, "Jump", (s, 1.2, s), self.gap(t), self.rise(), self.rng.uniform(-4, 4),
                          color="primary" if i % 2 == 0 else "secondary")

    def stones(self, m: Instance, t: float) -> None:
        for _ in range(self.rng.randint(5, 7)):
            self.next_pad(m, "Stone", (3, 1, 3), self.gap(t, 0.7), self.rng.uniform(0, 0.6),
                          self.rng.uniform(-2.5, 2.5), color="secondary")

    def beam(self, m: Instance, t: float) -> None:
        length = self.rng.uniform(18, 30)
        self.next_pad(m, "Beam", (self.diff["beam"], 1, length), 2, 0, color="accent", material="accent")

    def truss(self, m: Instance, t: float) -> None:
        h = 2 * self.rng.randint(4, 7)
        z = self.z + self.half + 1
        m.add(part("Truss", (2, h, 2), (self.x, self.y + h / 2, z), self.theme.color("secondary"),
                   self.theme.material("truss"), class_name="TrussPart"))
        self.z, self.half = z, 1.0
        self.next_pad(m, "Ledge", (8, 1.2, 8), 0, h)

    def movers(self, m: Instance, t: float) -> None:
        lo, hi = self.diff["period"]
        for _ in range(2):
            travel = self.rng.uniform(10, 14)
            mover = self.next_pad(m, "Mover", (7, 1, 7), self.gap(t, 0.5), 0, -travel / 2, color="accent",
                                  material="accent", tags=["Mover"])
            mover.attributes.update(MoveOffset=vector3((travel, 0, 0)), MovePeriod=round(self.rng.uniform(lo, hi), 2),
                                    MovePhase=round(self.rng.uniform(0, math.tau), 2))
            self.x += travel / 2
        self.next_pad(m, "Landing", (8, 1.2, 8), self.gap(t, 0.5))

    def faders(self, m: Instance, t: float) -> None:
        for _ in range(self.rng.randint(4, 6)):
            fader = self.next_pad(m, "Fader", (5, 1, 5), self.gap(t, 0.6), self.rng.uniform(-0.5, 0.5),
                                  self.rng.uniform(-3, 3), color="accent", material="accent",
                                  tags=["Fader"], Transparency=0.15)
            fader.attributes.update(FadeDelay=self.diff["fade"], FadeRespawn=2.5)

    def spinner(self, m: Instance, t: float) -> None:
        self.next_pad(m, "SpinArena", (16, 1.2, 16), self.gap(t), 0)
        speed = round(self.rng.uniform(*self.diff["spin"]) * self.rng.choice((1, -1)), 1)
        bars = 2 if self.ctx.params["difficulty"] == "hard" else 1
        for i in range(bars):
            bar = part("SpinBar", (15, 1, 1), (self.x, self.y + 1.2, self.z), self.theme.color("hazard"),
                       self.theme.material("hazard"), rotation=(0, 90 * i, 0), tags=["Hazard", "Spinner"])
            bar.attributes["SpinSpeed"] = speed
            m.add(bar)
        m.add(part("Hub", (3, 2.5, 2.5), (self.x, self.y + 1.5, self.z), self.theme.color("secondary"),
                   self.theme.material("platform"), Shape="Cylinder", rotation=(0, 0, 90)))

    # --- landmarks ----------------------------------------------------------------

    def checkpoint(self, m: Instance, stage: int, t: float) -> None:
        cp = self.next_pad(m, "Checkpoint", (10, 1.2, 10), self.gap(t, 0.6), color="checkpoint",
                           material="checkpoint", tags=["Checkpoint"])
        cp.attributes["Stage"] = stage
        for side in (-1, 1):
            post = (self.x + side * 4.3, self.y + 3, self.z - 4.3)
            m.add(part("LampPost", (6, 0.6, 0.6), post, self.theme.color("secondary"), "Metal",
                       Shape="Cylinder", rotation=(0, 0, 90)))
            lamp = m.add(part("Lamp", (1.4, 1.4, 1.4), (post[0], self.y + 6.5, post[2]), self.theme.color("accent"),
                              "Neon", Shape="Ball", CanCollide=False))
            lamp.add(Instance("PointLight", "Glow", {"Color": self.theme.color("accent"), "Range": 14,
                                                     "Brightness": 1.5}))
        cp.add(billboard(f"Stage {stage}", self.theme.color("goal"), 4))

    def finish(self, m: Instance) -> None:
        fin = self.next_pad(m, "Finish", (16, 1.2, 16), 4, 0, color="goal", material="goal", tags=["Finish"])
        for side in (-1, 1):
            m.add(part("GatePillar", (1.5, 12, 1.5), (self.x + side * 7, self.y + 6, self.z), self.theme.color("goal"),
                       "Neon"))
        m.add(part("GateTop", (15.5, 1.5, 1.5), (self.x, self.y + 12.75, self.z), self.theme.color("goal"), "Neon"))
        fin.add(billboard(self.theme.text("finishText", "FINISH"), self.theme.color("goal"), 9))

    def hazard_floor(self) -> Instance:
        min_x, max_x, min_z, max_z, min_y = self.bounds
        min_x, max_x, min_z, max_z = min_x - 60, max_x + 60, min_z - 60, max_z + 60
        top = min_y - 20
        floor = model("HazardFloor")
        name = self.theme.text("hazardName", "Hazard")
        width = min(max_x - min_x, MAX_PART)
        z = min_z
        while z < max_z:
            depth = min(MAX_PART, max_z - z)
            floor.add(pad(name, (width, 2, depth), ((min_x + max_x) / 2, top, z + depth / 2),
                          self.theme.color("hazard"), self.theme.material("hazard"), tags=["Hazard"]))
            z += depth
        return floor


class ObbyGenre(Genre):
    name = "obby"
    description = "Linear obstacle course with checkpoints, hazards and moving parts"
    defaults = {"stages": 12, "difficulty": "medium", "startHeight": 40.0}

    def validate_params(self, params: dict) -> None:
        if params["difficulty"] not in DIFFICULTY:
            raise ValueError(f"difficulty must be one of {sorted(DIFFICULTY)}")
        if not 1 <= params["stages"] <= 100:
            raise ValueError("stages must be between 1 and 100")

    def build(self, ctx: BuildContext) -> None:
        stages = ctx.params["stages"]
        course = _Course(ctx, ctx.params["startHeight"])
        theme = ctx.theme

        start = model("Start")
        spawn = start.add(pad("SpawnLocation", (16, 1.2, 16), (0, course.y, 0), theme.color("checkpoint"),
                              theme.material("checkpoint"), class_name="SpawnLocation", Neutral=True, Duration=0))
        spawn.add(billboard(theme.text("title", ctx.spec.name), theme.color("accent"), 6))
        ctx.add_map_model("Start", start)

        pool = course.diff["pool"]
        kind = None
        for stage in range(1, stages + 1):
            t = (stage - 1) / max(1, stages - 1)
            unlocked = pool[: max(2, math.ceil(len(pool) * (0.35 + 0.65 * t)))]
            kind = ctx.rng.choice([k for k in unlocked if k != kind])
            m = model(f"Stage{stage:02d}")
            m.attributes["Segment"] = kind
            getattr(course, kind)(m, t)
            if stage < stages:
                course.checkpoint(m, stage, t)
            else:
                course.finish(m)
            ctx.add_map_model(f"Stage{stage:02d}", m)

        ctx.add_map_model("HazardFloor", course.hazard_floor())
        ctx.config.update(stageCount=stages, checkpointCount=stages - 1)
