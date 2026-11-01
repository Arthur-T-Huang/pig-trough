"""The pipeline: spec -> genre generator -> file tree -> Rojo project on disk."""

from __future__ import annotations

from pathlib import Path

from .filetree import FileTree, SyncResult, sync
from .genres import get_genre
from .genres.base import BuildContext
from .paths import RUNTIME_DIR
from .spec import GameSpec
from .themes import Theme, load_theme

# Source layer subdirectory -> location in the generated project
LAYER_LAYOUT = {
    "server": "src/server",
    "client": "src/client",
    "shared": "src/shared",
    "map": "src/map",
}


def add_layer(tree: FileTree, source_dir: Path, overwrite: bool = False) -> None:
    for sub, dest in LAYER_LAYOUT.items():
        if (source_dir / sub).is_dir():
            tree.add_dir(source_dir / sub, dest, overwrite)


def make_project(spec: GameSpec, theme: Theme, tree: FileTree) -> dict:
    """Map each generated source folder to a `PigTrough`/`Map` child of its service.

    Every service node sets $ignoreUnknownInstances so live sync only manages our
    folders and never deletes Studio's own instances (Camera, Terrain, ...).
    """

    def has(prefix: str) -> bool:
        return any(p.startswith(prefix + "/") for p in tree.files)

    def service(class_name: str, **children) -> dict:
        node = {"$className": class_name, "$ignoreUnknownInstances": True}
        node.update({k: v for k, v in children.items() if v is not None})
        return node

    def mount(prefix: str) -> dict | None:
        return {"$path": prefix} if has(prefix) else None

    lighting = service("Lighting")
    lighting["$properties"] = theme.lighting_properties()
    atmosphere = theme.atmosphere_properties()
    if atmosphere:
        lighting["Atmosphere"] = {"$className": "Atmosphere", "$properties": atmosphere}

    return {
        "name": spec.slug,
        "tree": {
            "$className": "DataModel",
            "Workspace": service("Workspace", Map=mount("src/map")),
            "ReplicatedStorage": service("ReplicatedStorage", PigTrough=mount("src/shared")),
            "ServerScriptService": service("ServerScriptService", PigTrough=mount("src/server")),
            "StarterPlayer": service(
                "StarterPlayer",
                StarterPlayerScripts=service("StarterPlayerScripts", PigTrough=mount("src/client")),
            ),
            "Lighting": lighting,
        },
    }


def build_game(spec: GameSpec) -> FileTree:
    genre = get_genre(spec.genre)
    theme = load_theme(spec.theme)
    params = genre.resolve_params(spec.params)

    ctx = BuildContext(spec, theme, params)
    add_layer(ctx.tree, RUNTIME_DIR)
    add_layer(ctx.tree, genre.luau_dir)
    ctx.add_remote("Announce")
    genre.build(ctx)

    ctx.tree.add_json(
        "src/shared/GameConfig.json",
        {
            "game": {"name": spec.name, "slug": spec.slug, "genre": spec.genre, "seed": spec.seed},
            "theme": {
                "name": theme.name,
                "displayName": theme.display_name,
                "title": theme.text("title", spec.name),
                "flavor": theme.flavor,
                "palette": theme.palette,
            },
            "params": params,
            "genre": ctx.config,
        },
    )
    # Hand-written overrides/extras declared by the spec win over generated files.
    for include in spec.include:
        add_layer(ctx.tree, include, overwrite=True)
    ctx.tree.add_json("default.project.json", make_project(spec, theme, ctx.tree))
    return ctx.tree


def output_dir(spec: GameSpec, root: Path) -> Path:
    return Path(root) / spec.slug


def build_to_disk(spec: GameSpec, root: Path, force: bool = False) -> tuple[Path, SyncResult]:
    tree = build_game(spec)
    from .validate import validate_tree

    problems = validate_tree(tree)
    if problems:
        raise ValueError("Generated tree failed validation:\n  " + "\n  ".join(problems))
    out = output_dir(spec, root)
    return out, sync(tree, out, force=force)
