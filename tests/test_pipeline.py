import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from pigtrough.builder import build_game
from pigtrough.filetree import FileTree, sync
from pigtrough.genres import GENRES
from pigtrough.rbx import rotation_rows
from pigtrough.spec import GameSpec
from pigtrough.themes import available_themes
from pigtrough.tools import find_tool, rojo_build
from pigtrough.validate import check_luau, validate_tree


def spec(genre: str, theme: str, seed: int = 7, **params) -> GameSpec:
    return GameSpec(slug=f"{genre}-{theme}", name="Test", genre=genre, theme=theme, seed=seed, params=params)


class EveryCombination(unittest.TestCase):
    def test_each_genre_and_theme_builds_valid_tree(self):
        for genre in GENRES:
            for theme in available_themes():
                with self.subTest(genre=genre, theme=theme):
                    tree = build_game(spec(genre, theme))
                    self.assertEqual(validate_tree(tree), [])
                    for required in ("default.project.json", "src/shared/GameConfig.json",
                                     "src/shared/Runtime/Tagged.luau", "src/shared/Remotes/Announce.model.json"):
                        self.assertIn(required, tree)

    @unittest.skipUnless(find_tool("luau-compile"), "luau-compile not installed")
    def test_luau_parses(self):
        for genre in GENRES:
            with self.subTest(genre=genre):
                self.assertEqual(check_luau(build_game(spec(genre, "volcano"))), [])

    @unittest.skipUnless(find_tool("rojo"), "rojo not installed")
    def test_rojo_builds_place(self):
        for genre in GENRES:
            with self.subTest(genre=genre), tempfile.TemporaryDirectory() as tmp:
                sync(build_game(spec(genre, "space")), Path(tmp) / "game")
                rojo_build(Path(tmp) / "game" / "default.project.json", Path(tmp) / "game.rbxlx")
                self.assertTrue((Path(tmp) / "game.rbxlx").stat().st_size > 1000)


class Determinism(unittest.TestCase):
    def test_same_seed_same_bytes(self):
        self.assertEqual(build_game(spec("obby", "candy", 42)).files, build_game(spec("obby", "candy", 42)).files)

    def test_different_seed_changes_map(self):
        a = build_game(spec("collector", "candy", 1)).files
        b = build_game(spec("collector", "candy", 2)).files
        self.assertNotEqual(a["src/map/Platforms.model.json"], b["src/map/Platforms.model.json"])


class Params(unittest.TestCase):
    def test_stage_count_drives_models(self):
        tree = build_game(spec("obby", "volcano", stages=3))
        stages = [p for p in tree.files if p.startswith("src/map/Stage")]
        self.assertEqual(len(stages), 3)
        config = json.loads(tree.files["src/shared/GameConfig.json"])
        self.assertEqual(config["genre"]["checkpointCount"], 2)

    def test_rejects_unknown_and_mistyped_params(self):
        with self.assertRaises(ValueError):
            build_game(spec("obby", "volcano", lives=3))
        with self.assertRaises(ValueError):
            build_game(spec("obby", "volcano", stages="many"))
        with self.assertRaises(ValueError):
            build_game(spec("obby", "volcano", difficulty="nightmare"))


class Include(unittest.TestCase):
    def test_include_layer_adds_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "server").mkdir()
            (Path(tmp) / "server" / "Extra.server.luau").write_text("print('extra')")
            (Path(tmp) / "shared" / "Runtime").mkdir(parents=True)
            (Path(tmp) / "shared" / "Runtime" / "Hud.luau").write_text("return {}")
            s = spec("obby", "volcano")
            s.include = [Path(tmp)]
            tree = build_game(s)
            self.assertIn("src/server/Extra.server.luau", tree)
            self.assertEqual(tree.files["src/shared/Runtime/Hud.luau"], b"return {}")


class Sync(unittest.TestCase):
    def test_incremental_writes_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            tree = FileTree()
            tree.add("a/one.luau", "return 1")
            tree.add("a/two.luau", "return 2")
            self.assertEqual(len(sync(tree, out).written), 2)

            tree.files.pop("a/two.luau")
            tree.add("a/one.luau", "return 1", overwrite=True)
            result = sync(tree, out)
            self.assertEqual((result.written, result.deleted, result.unchanged), ([], ["a/two.luau"], 1))
            self.assertFalse((out / "a" / "two.luau").exists())

    def test_refuses_unmanaged_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "precious.txt").write_text("keep me")
            with self.assertRaises(RuntimeError):
                sync(FileTree(), Path(tmp))

    def test_rejects_path_escape(self):
        with self.assertRaises(ValueError):
            FileTree().add("../evil.luau", "")


class Geometry(unittest.TestCase):
    def test_rotation_matches_cframe_angles(self):
        # CFrame.Angles(0, math.rad(90), 0) maps +X to -Z
        self.assertEqual(rotation_rows(0, 90, 0), [[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
        self.assertEqual(rotation_rows(0, 0, 0), [[1, 0, 0], [0, 1, 0], [0, 0, 1]])


class CliSmoke(unittest.TestCase):
    def test_build_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(__file__).resolve().parent.parent
            proc = subprocess.run(
                ["python", "-m", "pigtrough", "build", str(repo / "games" / "lava-obby.json"), "--out", tmp],
                capture_output=True, text=True, cwd=repo,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((Path(tmp) / "lava-obby" / "default.project.json").exists())


if __name__ == "__main__":
    unittest.main()
