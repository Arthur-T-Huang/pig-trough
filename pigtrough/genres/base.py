from __future__ import annotations

import inspect
import random
from pathlib import Path

from ..filetree import FileTree
from ..rbx import Instance
from ..spec import GameSpec
from ..themes import Theme


class BuildContext:
    """Everything a genre needs to emit one game.

    Output layout (mapped by the generated default.project.json):
      src/map/     -> Workspace.Map                         (.model.json geometry)
      src/shared/  -> ReplicatedStorage.PigTrough           (modules, GameConfig, Remotes)
      src/server/  -> ServerScriptService.PigTrough         (*.server.luau)
      src/client/  -> StarterPlayerScripts.PigTrough        (*.client.luau)
    """

    def __init__(self, spec: GameSpec, theme: Theme, params: dict) -> None:
        self.spec = spec
        self.theme = theme
        self.params = params
        self.rng = random.Random(spec.seed)
        self.tree = FileTree()
        # Genre-specific data exposed to Luau as GameConfig.genre
        self.config: dict = {}

    def add_map_model(self, name: str, instance: Instance) -> None:
        self.tree.add_model(f"src/map/{name}.model.json", instance)

    def add_remote(self, name: str, class_name: str = "RemoteEvent") -> None:
        self.tree.add_model(f"src/shared/Remotes/{name}.model.json", Instance(class_name))


class Genre:
    name: str = ""
    description: str = ""
    # Every tunable parameter with its default; spec params are type-checked against these.
    defaults: dict = {}

    @property
    def luau_dir(self) -> Path:
        """Hand-written Luau for this genre, laid out as server/ client/ shared/."""
        return Path(inspect.getfile(type(self))).parent / "luau"

    def resolve_params(self, overrides: dict) -> dict:
        params = dict(self.defaults)
        for key, value in overrides.items():
            if key not in self.defaults:
                raise ValueError(f"Genre '{self.name}' has no param '{key}'; known: {sorted(self.defaults)}")
            expected = type(self.defaults[key])
            ok = isinstance(value, expected) or (expected is float and isinstance(value, int))
            if not ok or (expected is not bool and isinstance(value, bool)):
                raise ValueError(f"Param '{key}' must be {expected.__name__}, got {value!r}")
            params[key] = value
        self.validate_params(params)
        return params

    def validate_params(self, params: dict) -> None:
        pass

    def build(self, ctx: BuildContext) -> None:
        raise NotImplementedError
