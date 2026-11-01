"""Structural checks on a generated tree, run before anything reaches Rojo/Studio."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .filetree import FileTree
from .tools import luau_syntax_errors

MODEL_KEYS = {"name", "className", "properties", "attributes", "children"}
SCRIPT_SUFFIXES = (".luau", ".lua")


def _check_model(node, where: str, problems: list[str], root: bool) -> None:
    if not isinstance(node, dict):
        problems.append(f"{where}: instance must be an object")
        return
    unknown = set(node) - MODEL_KEYS
    if unknown:
        problems.append(f"{where}: unknown keys {sorted(unknown)}")
    if not isinstance(node.get("className"), str):
        problems.append(f"{where}: missing className")
    if not root and not isinstance(node.get("name"), str):
        problems.append(f"{where}: child missing name")
    props = node.get("properties", {})
    if not isinstance(props, dict):
        problems.append(f"{where}: properties must be an object")
    else:
        if "CFrame" in props and not (isinstance(props["CFrame"], dict) and "CFrame" in props["CFrame"]):
            problems.append(f"{where}: CFrame must use the explicit {{\"CFrame\": ...}} form")
        for key, value in props.items():
            # Nested lists (e.g. UDim2 [[s, o], [s, o]]) have no implicit form in Rojo 7
            if isinstance(value, list) and value and all(isinstance(v, list) for v in value):
                problems.append(f"{where}: property {key} needs an explicit typed value (e.g. {{\"UDim2\": ...}})")
    if not isinstance(node.get("attributes", {}), dict):
        problems.append(f"{where}: attributes must be an object")
    children = node.get("children", [])
    if not isinstance(children, list):
        problems.append(f"{where}: children must be a list")
        return
    for i, child in enumerate(children):
        name = child.get("name", i) if isinstance(child, dict) else i
        _check_model(child, f"{where}/{name}", problems, root=False)


def validate_tree(tree: FileTree) -> list[str]:
    problems: list[str] = []
    for path, data in tree.files.items():
        if path.endswith(".json"):
            try:
                obj = json.loads(data)
            except json.JSONDecodeError as e:
                problems.append(f"{path}: invalid JSON ({e})")
                continue
            if path.endswith(".model.json"):
                _check_model(obj, path, problems, root=True)
    if "default.project.json" not in tree:
        problems.append("missing default.project.json")
    return problems


def check_luau(tree: FileTree) -> list[str] | None:
    """Syntax-check every script via luau-compile. None if the compiler is unavailable."""
    scripts = {p: d for p, d in tree.files.items() if p.endswith(SCRIPT_SUFFIXES)}
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for rel, data in scripts.items():
            target = Path(tmp) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files.append(target)
        errors = luau_syntax_errors(files)
        if errors is None:
            return None
        return [e.replace(tmp.replace("\\", "/"), "").replace(tmp, "") for e in errors]
