"""Game specs: the JSON contract describing one game (genre + theme + parameters).

A spec is the single input to the pipeline, so anything that can write JSON
(a person, a script, or an LLM) can drive generation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import games_dir

KNOWN_KEYS = {"name", "genre", "theme", "seed", "params", "include"}


@dataclass
class GameSpec:
    slug: str
    name: str
    genre: str
    theme: str
    seed: int
    params: dict = field(default_factory=dict)
    include: list[Path] = field(default_factory=list)
    path: Path | None = None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "game"


def resolve_spec_path(arg: str) -> Path:
    """Accept a path to a spec file or a bare slug from ./games."""
    p = Path(arg)
    if p.suffix == ".json" or p.exists():
        return p
    return games_dir() / f"{arg}.json"


def load_spec(path: Path) -> GameSpec:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Spec not found: {path}")
    data = json.loads(path.read_text("utf-8"))
    unknown = set(data) - KNOWN_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown spec keys {sorted(unknown)}")
    for key in ("genre", "theme"):
        if not isinstance(data.get(key), str):
            raise ValueError(f"{path}: '{key}' must be a string")
    seed = data.get("seed", 0)
    if not isinstance(seed, int):
        raise ValueError(f"{path}: 'seed' must be an integer")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"{path}: 'params' must be an object")
    include = [(path.parent / p).resolve() for p in data.get("include", [])]
    for inc in include:
        if not inc.is_dir():
            raise FileNotFoundError(f"{path}: include directory not found: {inc}")
    return GameSpec(
        slug=path.stem,
        name=data.get("name", path.stem.replace("-", " ").title()),
        genre=data["genre"],
        theme=data["theme"],
        seed=seed,
        params=params,
        include=include,
        path=path,
    )
