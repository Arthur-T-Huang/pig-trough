# pig-trough

Automated Roblox game development. Describe a game as a small JSON **spec**
(genre + theme + parameters). pig-trough generates the Luau scripts, JSON
config and `.model.json` geometry as a Rojo project, and Rojo live-syncs it
into Roblox Studio.

```
games/lava-obby.json ──► genre generator (Python) ──► build/lava-obby/ ──► rojo serve ──► Studio
        spec              + theme + Luau runtime        Rojo project       (live sync)
```

## Setup

1. **Python 3.10+**. No third-party dependencies. Optionally `pip install -e .` to get a `pigtrough` command; otherwise use `python -m pigtrough`.
2. **Rojo 7.7** (pinned in `rokit.toml`):
   - Install [Rokit](https://github.com/rojo-rbx/rokit), then run `rokit install` in this repo.
   - Install the Studio plugin with `rojo plugin install`.
3. *(Optional)* **luau-compile** from the [Luau releases](https://github.com/luau-lang/luau/releases), on your PATH or set via `PIGTROUGH_LUAU_COMPILE`. Used by `check` to syntax-check generated scripts.

You can also point at specific binaries with `PIGTROUGH_ROJO` / `PIGTROUGH_LUAU_COMPILE`.

## Usage

```sh
python -m pigtrough list                          # genres, themes, specs
python -m pigtrough new my-obby --genre obby --theme space
python -m pigtrough serve lava-obby               # build + rojo serve + regenerate on change
```

Then, in Studio, open an empty Baseplate place, open the Rojo plugin, and click **Connect**.
`serve` watches the spec, the themes and the generator code. Save any of them
and the game regenerates and syncs into Studio within about a second.

| Command | What it does |
| --- | --- |
| `build <spec> [--place out.rbxlx]` | Generate `build/<slug>/`; optionally also produce a place file with `rojo build` |
| `check <spec>` | Generate in memory, validate JSON/models, parse all Luau, run a real `rojo build` |
| `serve <spec> [--port N] [--no-rojo]` | Build, run `rojo serve`, and rebuild whenever inputs change |
| `new <slug> --genre G --theme T` | Write a starter spec with every parameter set to its default |

`<spec>` is a path or a slug in `./games`.

## Spec format

```json
{
  "name": "Lava Obby",
  "genre": "obby",
  "theme": "volcano",
  "seed": 1337,
  "params": { "stages": 12, "difficulty": "medium" },
  "include": ["lava-obby-extras"]
}
```

- **seed**: generation is deterministic. The same spec always produces byte-identical output.
- **params**: checked against the genre's `defaults` for unknown keys and wrong types.
- **include** *(optional)*: directories of hand-written files laid out as `server/ client/ shared/ map/`. They are merged over the generated output, so they can add or replace any file.

## How it is organised

```
pigtrough/
  cli.py            commands
  builder.py        spec -> FileTree -> default.project.json
  filetree.py       in-memory tree + minimal, atomic sync to disk (manifest-tracked)
  rbx.py            Instance builder -> Rojo .model.json
  themes.py spec.py validate.py tools.py
  runtime/          Luau shared by every genre (Tagged, Leaderstats, Hud, Hazards, Animators)
  genres/
    base.py         Genre + BuildContext
    obby/           __init__.py (generator) + luau/{server,client}
    collector/
themes/*.json       palette, materials, Lighting/Atmosphere, flavour text
games/*.json        game specs
tests/              python -m unittest discover -s tests
```

Generated project layout. Each service only gets a single managed child, so
anything else you add in Studio is left alone (`$ignoreUnknownInstances`):

| Output | Studio location |
| --- | --- |
| `src/map/*.model.json` | `Workspace.Map` |
| `src/shared/` (modules, `GameConfig.json`, `Remotes/`) | `ReplicatedStorage.PigTrough` |
| `src/server/*.server.luau` | `ServerScriptService.PigTrough` |
| `src/client/*.client.luau` | `StarterPlayer.StarterPlayerScripts.PigTrough` |
| theme `lighting` / `atmosphere` | `Lighting` properties + `Atmosphere` |

**Design rule: data is generated, behaviour is hand-written.** Generators emit
geometry with **tags and attributes** (`Hazard`, `Mover` + `MoveOffset`,
`Checkpoint` + `Stage`, …) plus a `GameConfig` module. Generic Luau in
`runtime/` and `genres/*/luau/` binds behaviour to those tags. Adding variety
then usually means changing Python, not writing new Luau.

## Adding a genre

1. Create `pigtrough/genres/<name>/__init__.py` with a `Genre` subclass: set `name`, `description` and `defaults`, and implement `build(ctx)`.
   - Use `ctx.rng` for all randomness so output stays deterministic.
   - Emit geometry with `ctx.add_map_model(name, instance)` (see `rbx.part` / `rbx.pad` / `rbx.model`).
   - Put runtime data in `ctx.config`; it becomes `GameConfig.genre` in Luau.
   - Declare remotes with `ctx.add_remote("Name")`.
2. Put its scripts in `pigtrough/genres/<name>/luau/{server,client,shared}/`.
3. Register it in `pigtrough/genres/__init__.py`. The test suite then builds it against every theme automatically.

## Adding a theme

Copy a file in `themes/`. A theme needs the palette keys `ground primary secondary accent hazard checkpoint goal`.
`materials` values are `Enum.Material` names. Any `#rrggbb` string under
`lighting` or `atmosphere` is converted to a `Color3`. The `flavor` strings
(`title`, `intro`, `hazardName`, `collectible`, `finishText`) appear in-game.

## Rojo `.model.json` notes (verified against Rojo 7.7)

- Implicit values work for `Vector3` `[x,y,z]`, `Color3` `[r,g,b]` (0–1), enums (`"Neon"`), bools, numbers, strings and `Tags` (`["A","B"]`).
- `CFrame` and `UDim2` **must** be explicit: `{"CFrame": {"position": …, "orientation": [[row],[row],[row]]}}`, `{"UDim2": [[sx,ox],[sy,oy]]}`. Use `rbx.cframe()` / `rbx.udim2()`.
- Attributes go in a top-level `"attributes"` key, not inside `properties`. A `Vector3` attribute needs `{"Vector3": [...]}` (`rbx.vector3()`).
- The validator flags the common mistakes before Rojo sees them.

## Next steps

- An LLM-driven spec author: prompt → spec JSON (the spec is already the full contract), or generating `include` layers of custom Luau.
- More genres (tycoon, tower defense, simulator) and richer per-theme props.
- Mesh and asset support (uploaded MeshIds / `.rbxm` assets referenced from themes).
