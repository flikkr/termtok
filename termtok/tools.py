"""Locating the external tools termtok shells out to (yt-dlp, ffplay, deno/node).

The released build is a PyInstaller ``--onefile`` binary, so it can't rely on a
Python environment: there ``sys.executable`` is *termtok itself*, not a Python
interpreter, and ``yt_dlp`` isn't importable. So we invoke the **standalone**
``yt-dlp`` executable instead, looked up in this order:

  1. an explicit env override (``TERMTOK_YTDLP`` / ``TERMTOK_FFPLAY``),
  2. termtok's own bin dir (where ``install.sh`` drops downloaded binaries),
  3. the system ``PATH``.

For source/dev runs where the standalone binary isn't around but ``yt_dlp`` is
importable, we fall back to ``python -m yt_dlp``.

``subprocess_env()`` prepends termtok's bin dir to ``PATH`` so yt-dlp can find a
JS runtime (deno/node) and ffmpeg there too, without the user editing their
shell profile.
"""

from __future__ import annotations

import os
import shutil
import sys

# Kept in sync with install.sh's TERMTOK_BIN.
_BIN_SUBPATH = ("termtok", "bin")


def bin_dir() -> str:
    """The directory install.sh downloads helper binaries into."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, *_BIN_SUBPATH)


def _resolve(name: str, env_override: str | None) -> str | None:
    """Find executable ``name`` via env override, termtok's bin dir, then PATH."""
    if env_override:
        val = os.environ.get(env_override)
        if val:
            return val
    local = os.path.join(bin_dir(), name)
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return shutil.which(name)


def ffplay() -> str | None:
    """Path to the ``ffplay`` executable, or ``None`` if unavailable."""
    return _resolve("ffplay", "TERMTOK_FFPLAY")


def ytdlp_cmd() -> list[str]:
    """The command prefix that runs yt-dlp (e.g. ``["/path/to/yt-dlp"]``)."""
    found = _resolve("yt-dlp", "TERMTOK_YTDLP")
    if found:
        return [found]
    # Dev/source fallback: no standalone binary, but yt_dlp may be importable.
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "yt_dlp"]
    # Frozen with nothing found — return the bare name for a clear "not found".
    return ["yt-dlp"]


def subprocess_env() -> dict[str, str]:
    """A copy of the environment with termtok's bin dir prepended to PATH.

    Lets the yt-dlp subprocess discover a JS runtime (deno/node) and ffmpeg that
    install.sh placed in termtok's bin dir, even when it isn't on the user's PATH.
    """
    env = os.environ.copy()
    env["PATH"] = bin_dir() + os.pathsep + env.get("PATH", "")
    return env
