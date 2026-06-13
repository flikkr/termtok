"""The feed: discovers videos, runs the loop, composites the scroll transition."""

from __future__ import annotations

import math
import os
import re
import shutil
import signal
import time

import numpy as np

from .physics import ScrollPhysics
from .render import Renderer
from .terminal import InputReader, Terminal
from .video import VideoReader

_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
_TARGET_FPS = 30.0


def discover_videos(folder: str) -> list[str]:
    """Return video files in ``folder`` sorted naturally (1, 2, 10 — not 1, 10, 2)."""
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


class Feed:
    def __init__(self, paths: list[str]) -> None:
        if not paths:
            raise ValueError("no videos to play")
        self.paths = paths
        self.readers = [VideoReader(p) for p in paths]
        self.physics = ScrollPhysics(len(paths))
        self.renderer = Renderer()
        self._quit = False
        self._epoch = time.monotonic()
        self._size: tuple[int, int] | None = None  # (cols, rows)
        self._status: str | None = None

    def request_quit(self) -> None:
        self._quit = True

    def run(self) -> None:
        with Terminal() as term:
            reader = InputReader(self.physics.kick, self.request_quit)
            reader.start()
            try:
                signal.signal(signal.SIGINT, lambda *_: self.request_quit())
            except ValueError:
                pass  # not on the main thread; Ctrl-C handled by input parser

            frame_dt = 1.0 / _TARGET_FPS
            last = time.monotonic()
            try:
                while not self._quit:
                    now = time.monotonic()
                    dt = now - last
                    last = now

                    self.physics.update(dt)
                    cols, rows = self._viewport()
                    pixels = self._compose(cols, rows)
                    term.write(self.renderer.render(pixels))
                    self._draw_status(term, cols, rows)

                    slack = frame_dt - (time.monotonic() - now)
                    if slack > 0:
                        time.sleep(slack)
            finally:
                reader.stop()
                for r in self.readers:
                    r.release()

    # -- layout ------------------------------------------------------------

    def _viewport(self) -> tuple[int, int]:
        cols, rows = shutil.get_terminal_size((80, 24))
        cols = max(8, cols)
        rows = max(4, rows)
        if (cols, rows) != self._size:
            self._size = (cols, rows)
            self.renderer.reset()
            self._status = None  # force the status line to redraw too
        return cols, rows

    # -- composition -------------------------------------------------------

    def _compose(self, cols: int, rows: int) -> np.ndarray:
        video_rows = rows - 1  # reserve the bottom row for the status line
        view_h = video_rows * 2  # two stacked pixels per cell (half-block)
        view_w = cols

        last = len(self.readers) - 1
        pos = min(max(self.physics.position, 0.0), float(last))
        base = int(math.floor(pos))
        frac = pos - base
        offset = int(round(frac * view_h))

        t = time.monotonic() - self._epoch
        top_buf = self.readers[base].frame_at(t, view_w, view_h)

        if offset <= 0:
            return top_buf

        # Mid-transition: outgoing video slides up, incoming slides in below.
        canvas = np.empty((view_h, view_w, 3), np.uint8)
        keep = view_h - offset
        canvas[:keep] = top_buf[offset:]
        if base + 1 <= last:
            nxt = self.readers[base + 1].frame_at(t, view_w, view_h)
            canvas[keep:] = nxt[:offset]
        else:
            canvas[keep:] = 0
        return canvas

    # -- status line -------------------------------------------------------

    def _draw_status(self, term: Terminal, cols: int, rows: int) -> None:
        last = len(self.readers) - 1
        pos = min(max(self.physics.position, 0.0), float(last))
        idx = int(round(pos))
        name = os.path.basename(self.paths[idx])

        left = f" termtok  {idx + 1}/{last + 1}  {name} "
        right = " scroll ▲▼ · q quit "
        gap = cols - _vlen(left) - _vlen(right)
        if gap < 1:
            text = _trunc(left, cols)
            pad = cols - _vlen(text)
            line = text + " " * max(0, pad)
        else:
            line = left + " " * gap + right

        if line == self._status:
            return
        self._status = line
        # Dark bar, light text, drawn on the final row; \x1b[K clears the rest.
        term.write(
            f"\x1b[{rows};1H\x1b[48;2;18;18;18m\x1b[38;2;235;235;235m"
            f"{line}\x1b[0m\x1b[K"
        )


def _vlen(s: str) -> int:
    return len(s)


def _trunc(s: str, width: int) -> str:
    return s if len(s) <= width else s[: max(0, width - 1)] + "…"
