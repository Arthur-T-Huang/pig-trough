"""Locate and run external tools (Rojo, luau-compile)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ENV_OVERRIDES = {"rojo": "PIGTROUGH_ROJO", "luau-compile": "PIGTROUGH_LUAU_COMPILE"}


def find_tool(name: str) -> str | None:
    env = ENV_OVERRIDES.get(name)
    if env and os.environ.get(env):
        return os.environ[env]
    return shutil.which(name)


def require_tool(name: str) -> str:
    path = find_tool(name)
    if not path:
        hint = " (install with `rokit install`)" if name == "rojo" else ""
        raise RuntimeError(f"'{name}' not found on PATH{hint}; or set {ENV_OVERRIDES.get(name, '')}")
    return path


def rojo_build(project: Path, output: Path) -> None:
    subprocess.run([require_tool("rojo"), "build", str(project), "-o", str(output)], check=True)


def rojo_serve(project: Path, port: int | None = None) -> subprocess.Popen:
    cmd = [require_tool("rojo"), "serve", str(project)]
    if port:
        cmd += ["--port", str(port)]
    return subprocess.Popen(cmd)


def luau_syntax_errors(files: list[Path]) -> list[str] | None:
    """Parse-check Luau files; None when luau-compile isn't installed."""
    compiler = find_tool("luau-compile")
    if not compiler or not files:
        return None if not compiler else []
    proc = subprocess.run(
        [compiler, "--null", *map(str, files)], capture_output=True, text=True
    )
    return [line for line in (proc.stdout + proc.stderr).splitlines() if "Error" in line]
