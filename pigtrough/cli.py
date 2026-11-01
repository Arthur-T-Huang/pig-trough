"""pigtrough command line: list | new | build | check | serve."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .builder import build_game, build_to_disk, output_dir
from .genres import GENRES, get_genre
from .paths import PACKAGE_DIR, games_dir, themes_dirs
from .spec import load_spec, resolve_spec_path, slugify
from .themes import available_themes, load_theme
from .tools import rojo_build, rojo_serve
from .validate import check_luau, validate_tree

DEFAULT_OUT = Path("build")


def cmd_list(args) -> int:
    print("Genres:")
    for g in GENRES.values():
        print(f"  {g.name:<12} {g.description}")
    print("Themes:")
    for name in available_themes():
        print(f"  {name:<12} {load_theme(name).display_name}")
    specs = sorted(games_dir().glob("*.json"))
    if specs:
        print("Games:")
        for p in specs:
            print(f"  {p.stem}")
    return 0


def cmd_new(args) -> int:
    genre = get_genre(args.genre)
    load_theme(args.theme)
    slug = slugify(args.slug)
    path = games_dir() / f"{slug}.json"
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    spec = {
        "name": args.name or slug.replace("-", " ").title(),
        "genre": genre.name,
        "theme": args.theme,
        "seed": args.seed if args.seed is not None else random.randrange(1, 1_000_000),
        "params": dict(genre.defaults),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n", "utf-8")
    print(f"Created {path}")
    return 0


def cmd_build(args) -> int:
    spec = load_spec(resolve_spec_path(args.spec))
    out, result = build_to_disk(spec, args.out, force=args.force)
    print(f"[pigtrough] {spec.slug} -> {out}: {result.summary()}")
    if args.place:
        rojo_build(out / "default.project.json", Path(args.place))
    return 0


def cmd_check(args) -> int:
    spec = load_spec(resolve_spec_path(args.spec))
    tree = build_game(spec)
    problems = validate_tree(tree)
    luau = check_luau(tree)
    if luau is None:
        print("luau-compile not found; skipping Luau syntax check")
    else:
        problems += luau
    if not problems:
        with tempfile.TemporaryDirectory() as tmp:
            from .filetree import sync

            sync(tree, Path(tmp) / spec.slug)
            try:
                rojo_build(Path(tmp) / spec.slug / "default.project.json", Path(tmp) / "check.rbxlx")
            except RuntimeError as e:
                print(f"{e}; skipping Rojo build check")
            except subprocess.CalledProcessError:
                problems.append("rojo build failed (see output above)")
    for p in problems:
        print(f"  x {p}")
    print(f"{spec.slug}: {len(tree)} files, {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def _watch_snapshot(paths: list[Path]) -> dict[Path, float]:
    snap = {}
    for root in paths:
        files = [root] if root.is_file() else root.rglob("*") if root.is_dir() else []
        for f in files:
            if f.is_file() and "__pycache__" not in f.parts:
                snap[f] = f.stat().st_mtime
    return snap


def cmd_serve(args) -> int:
    spec_path = resolve_spec_path(args.spec)
    spec = load_spec(spec_path)
    out = output_dir(spec, args.out)
    # Builds run in a subprocess so edits to generator Python code are picked up too.
    build_cmd = [sys.executable, "-m", "pigtrough", "build", str(spec_path), "--out", str(args.out)]
    if args.force:
        build_cmd.append("--force")

    def rebuild() -> bool:
        return subprocess.run(build_cmd).returncode == 0

    if not rebuild():
        return 1
    rojo = None if args.no_rojo else rojo_serve(out / "default.project.json", args.port)
    watched = [spec_path, PACKAGE_DIR, *themes_dirs(), *spec.include]
    print(f"[pigtrough] watching {len(watched)} locations; edit the spec, themes or generators to regenerate. Ctrl+C to stop.")
    snapshot = _watch_snapshot(watched)
    try:
        while True:
            time.sleep(0.5)
            if rojo and rojo.poll() is not None:
                print("[pigtrough] rojo exited", file=sys.stderr)
                return rojo.returncode or 1
            current = _watch_snapshot(watched)
            if current != snapshot:
                time.sleep(0.3)  # let editors finish writing
                snapshot = _watch_snapshot(watched)
                if not rebuild():
                    print("[pigtrough] build failed; Studio keeps the last good version", file=sys.stderr)
    except KeyboardInterrupt:
        return 0
    finally:
        if rojo and rojo.poll() is None:
            rojo.terminate()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pigtrough", description="Generate Roblox games and sync them with Rojo.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list genres, themes and game specs").set_defaults(func=cmd_list)

    p = sub.add_parser("new", help="create a game spec in ./games")
    p.add_argument("slug")
    p.add_argument("--genre", required=True)
    p.add_argument("--theme", required=True)
    p.add_argument("--name")
    p.add_argument("--seed", type=int)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_new)

    for name, func, help_text in (
        ("build", cmd_build, "generate the Rojo project for a spec"),
        ("check", cmd_check, "generate in memory and validate (JSON, Luau syntax, rojo build)"),
        ("serve", cmd_serve, "build, run `rojo serve`, and regenerate on changes"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("spec", help="spec path or slug in ./games")
        if name != "check":
            p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output root (default: build)")
            p.add_argument("--force", action="store_true", help="allow writing into a non-pigtrough directory")
        if name == "build":
            p.add_argument("--place", help="also run `rojo build` to this .rbxl/.rbxlx file")
        if name == "serve":
            p.add_argument("--port", type=int)
            p.add_argument("--no-rojo", action="store_true", help="only regenerate; run rojo yourself")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
