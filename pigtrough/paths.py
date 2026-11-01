from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
RUNTIME_DIR = PACKAGE_DIR / "runtime"


def search_dirs(name: str) -> list[Path]:
    """`<cwd>/<name>` first so projects can add their own, then the repo's built-ins."""
    dirs = []
    for d in (Path.cwd() / name, REPO_DIR / name):
        d = d.resolve()
        if d.is_dir() and d not in dirs:
            dirs.append(d)
    return dirs


def themes_dirs() -> list[Path]:
    return search_dirs("themes")


def games_dir() -> Path:
    return Path.cwd() / "games"
