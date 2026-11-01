"""Themes: palette, materials, lighting and flavour text shared by every genre."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import themes_dirs

REQUIRED_COLORS = ("ground", "primary", "secondary", "accent", "hazard", "checkpoint", "goal")


def hex_to_rgb(value: str) -> list[float]:
    h = value.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected #rrggbb colour, got {value!r}")
    return [round(int(h[i : i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def _convert_colors(props: dict) -> dict:
    return {k: hex_to_rgb(v) if isinstance(v, str) and v.startswith("#") else v for k, v in props.items()}


@dataclass(frozen=True)
class Theme:
    name: str
    display_name: str
    palette: dict[str, str]
    materials: dict[str, str]
    lighting: dict
    atmosphere: dict | None
    flavor: dict[str, str]
    path: Path

    def color(self, key: str) -> list[float]:
        return hex_to_rgb(self.palette[key])

    def material(self, key: str) -> str:
        return self.materials.get(key, "SmoothPlastic")

    def text(self, key: str, default: str = "") -> str:
        return self.flavor.get(key, default)

    def lighting_properties(self) -> dict:
        return _convert_colors(self.lighting)

    def atmosphere_properties(self) -> dict | None:
        return _convert_colors(self.atmosphere) if self.atmosphere else None


def load_theme_file(path: Path) -> Theme:
    data = json.loads(Path(path).read_text("utf-8"))
    palette = data.get("palette", {})
    missing = [c for c in REQUIRED_COLORS if c not in palette]
    if missing:
        raise ValueError(f"Theme {path} is missing palette colours: {', '.join(missing)}")
    for value in palette.values():
        hex_to_rgb(value)
    return Theme(
        name=data.get("name", Path(path).stem),
        display_name=data.get("displayName", Path(path).stem.title()),
        palette=palette,
        materials=data.get("materials", {}),
        lighting=data.get("lighting", {}),
        atmosphere=data.get("atmosphere"),
        flavor=data.get("flavor", {}),
        path=Path(path),
    )


def available_themes() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for d in themes_dirs():
        for f in sorted(d.glob("*.json")):
            found.setdefault(f.stem, f)
    return found


def load_theme(name: str) -> Theme:
    themes = available_themes()
    if name not in themes:
        raise KeyError(f"Unknown theme {name!r}; available: {', '.join(sorted(themes)) or 'none'}")
    return load_theme_file(themes[name])
