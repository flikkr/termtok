"""The feed: drives the loop and composites the scroll transition over a Source."""

from __future__ import annotations

import logging
import math
import signal
import shutil
import time

import numpy as np

log = logging.getLogger("termtok.feed")

from .physics import ScrollPhysics
from .render import Renderer
from .source import Source
from .terminal import InputReader, Terminal
from .video import VideoReader

_TARGET_FPS = 30.0
# Keep decoders only for videos within this many steps of the playhead.
_READER_WINDOW = 2
_LOADING_BG = (12, 12, 14)


class Feed:
    def __init__(self, source: Source) -> None:
        self.source = source
        self.physics = ScrollPhysics(max(1, source.count()))
        self.renderer = Renderer()
        self.readers: dict[int, VideoReader] = {}
        self._quit = False
        self._epoch = time.monotonic()
        self._size: tuple[int, int] | None = None
        self._status: str | None = None

    def request_quit(self) -> None:
        self._quit = True

    def run(self) -> None:
        self.source.start()
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

                    self.physics.set_count(max(1, self.source.count()))
                    self.physics.update(dt)
                    playhead = int(round(self.physics.position))
                    self.source.set_playhead(playhead)
                    self._evict_readers(playhead)

                    cols, rows = self._viewport()
                    pixels = self._compose(cols, rows)
                    term.write(self.renderer.render(pixels))
                    self._draw_status(term, cols, rows, playhead)

                    slack = frame_dt - (time.monotonic() - now)
                    if slack > 0:
                        time.sleep(slack)
            finally:
                reader.stop()
                self.source.stop()
                for r in self.readers.values():
                    r.release()

    # -- layout ------------------------------------------------------------

    def _viewport(self) -> tuple[int, int]:
        cols, rows = shutil.get_terminal_size((80, 24))
        cols = max(8, cols)
        rows = max(4, rows)
        if (cols, rows) != self._size:
            self._size = (cols, rows)
            self.renderer.reset()
            self._status = None
        return cols, rows

    # -- composition -------------------------------------------------------

    def _compose(self, cols: int, rows: int) -> np.ndarray:
        view_h = (rows - 1) * 2  # reserve bottom row for status; 2 px per cell
        view_w = cols
        t = time.monotonic() - self._epoch

        count = self.source.count()
        if count <= 0:
            return self._loading_frame(view_w, view_h, t)

        last = count - 1
        pos = min(max(self.physics.position, 0.0), float(last))
        base = int(math.floor(pos))
        frac = pos - base
        offset = int(round(frac * view_h))

        top_buf = self._frame_for(base, t, view_w, view_h)
        if offset <= 0:
            return top_buf

        canvas = np.empty((view_h, view_w, 3), np.uint8)
        keep = view_h - offset
        canvas[:keep] = top_buf[offset:]
        canvas[keep:] = self._frame_for(base + 1, t, view_w, view_h)[:offset]
        return canvas

    def _frame_for(self, idx: int, t: float, w: int, h: int) -> np.ndarray:
        if idx < 0 or idx >= self.source.count():
            return self._loading_frame(w, h, t)
        path = self.source.path(idx)
        if path is None:
            if self.source.dead(idx):
                return self._unavailable_frame(w, h)
            return self._loading_frame(w, h, t)
        reader = self.readers.get(idx)
        if reader is None or reader.path != path:
            reader = VideoReader(path)
            self.readers[idx] = reader
        try:
            return reader.frame_at(t, w, h)
        except Exception:  # noqa: BLE001 - a bad/half file shouldn't crash the loop
            log.warning("decode failed for #%d (%s), showing loader", idx, path, exc_info=True)
            return self._loading_frame(w, h, t)

    @staticmethod
    def _loading_frame(w: int, h: int, t: float) -> np.ndarray:
        canvas = np.empty((h, w, 3), np.uint8)
        canvas[:] = _LOADING_BG
        # A gentle pulsing band at the vertical center, just to show life.
        pulse = int(30 + 25 * (0.5 + 0.5 * math.sin(t * 3.0)))
        mid = h // 2
        canvas[max(0, mid - 1) : mid + 1] = (pulse, pulse, pulse + 6)
        return canvas

    @staticmethod
    def _unavailable_frame(w: int, h: int) -> np.ndarray:
        canvas = np.empty((h, w, 3), np.uint8)
        canvas[:] = (24, 14, 14)  # dim red-tinted: distinct from the loader
        return canvas

    def _evict_readers(self, playhead: int) -> None:
        for idx in list(self.readers):
            if abs(idx - playhead) > _READER_WINDOW:
                self.readers.pop(idx).release()

    # -- status line -------------------------------------------------------

    def _draw_status(self, term: Terminal, cols: int, rows: int, playhead: int) -> None:
        banner = self.source.status()
        count = self.source.count()
        if banner:
            left = f" termtok · {banner} "
        elif count <= 0:
            left = " termtok · connecting… "
        else:
            idx = min(max(playhead, 0), count - 1)
            more = "+" if self.source.has_more() else ""
            head = f" {idx + 1}/{count}{more} "
            if self.source.dead(idx):
                left = f"{head} ✕ unavailable — scroll on"
            else:
                cap = self.source.label(idx)
                left = f"{head} {cap}" if cap else head

        right = " ▲▼ q "
        gap = cols - len(left) - len(right)
        if gap < 1:
            line = _trunc(left, cols)
            line = line + " " * max(0, cols - len(line))
        else:
            line = left + " " * gap + right

        if line == self._status:
            return
        self._status = line
        term.write(
            f"\x1b[{rows};1H\x1b[48;2;18;18;18m\x1b[38;2;235;235;235m"
            f"{line}\x1b[0m\x1b[K"
        )


def _trunc(s: str, width: int) -> str:
    return s if len(s) <= width else s[: max(0, width - 1)] + "…"
