from .base import Genre
from .collector import CollectorGenre
from .obby import ObbyGenre

GENRES: dict[str, Genre] = {g.name: g for g in (ObbyGenre(), CollectorGenre())}


def get_genre(name: str) -> Genre:
    if name not in GENRES:
        raise KeyError(f"Unknown genre {name!r}; available: {', '.join(sorted(GENRES))}")
    return GENRES[name]
