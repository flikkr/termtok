"""Where videos come from.

The player talks to a ``Source`` instead of a fixed file list, so it doesn't
care whether videos sit in a folder or stream in from TikTok. A source answers:

  * ``count()``     — how many videos are known right now (grows when streaming),
  * ``path(i)``     — the local file for video ``i``, or ``None`` if not ready,
  * ``label(i)``    — a short caption for the status bar,
  * ``status()``    — a global banner (connecting / error), or ``None``,
  * ``has_more()``  — whether ``count()`` may still grow,
  * ``set_playhead(i)`` — a hint of what the user is watching (for prefetch).
"""

from __future__ import annotations

import os
import re

_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


class Source:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def count(self) -> int: ...
    def path(self, i: int) -> str | None: ...
    def label(self, i: int) -> str: ...
    def status(self) -> str | None:
        return None
    def has_more(self) -> bool:
        return False
    def dead(self, i: int) -> bool:
        return False
    def set_playhead(self, i: int) -> None: ...


class LocalFolderSource(Source):
    """Plays a fixed set of files from a folder (offline / default mode)."""

    def __init__(self, folder: str, limit: int | None = None) -> None:
        self._paths = _discover(folder)
        if limit is not None:
            self._paths = self._paths[: max(0, limit)]

    @property
    def paths(self) -> list[str]:
        return self._paths

    def count(self) -> int:
        return len(self._paths)

    def path(self, i: int) -> str | None:
        return self._paths[i] if 0 <= i < len(self._paths) else None

    def label(self, i: int) -> str:
        return os.path.basename(self._paths[i]) if 0 <= i < len(self._paths) else ""


class StreamSource(Source):
    """Streams a feed via any :class:`~termtok.fetcher.BaseFetcher` backend."""

    def __init__(self, fetcher) -> None:
        self._f = fetcher

    def start(self) -> None:
        self._f.start()

    def stop(self) -> None:
        self._f.stop()

    def count(self) -> int:
        return self._f.count()

    def path(self, i: int) -> str | None:
        return self._f.path(i)

    def label(self, i: int) -> str:
        return self._f.label(i)

    def status(self) -> str | None:
        return self._f.status()

    def has_more(self) -> bool:
        return self._f.has_more()

    def dead(self, i: int) -> bool:
        return self._f.dead(i)

    def set_playhead(self, i: int) -> None:
        self._f.set_playhead(i)


def _discover(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in _VIDEO_EXTS
    ]
    return sorted(files, key=_natural_key)


def _natural_key(path: str):
    name = os.path.basename(path)
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]
