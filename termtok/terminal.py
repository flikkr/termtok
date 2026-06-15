"""Terminal setup/teardown and a background input reader.

Handles raw mode, the alternate screen, cursor/wrap control and SGR mouse
tracking, plus a thread that parses wheel and key events from stdin.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import threading
import tty
from typing import Callable

# Enter: alt screen, hide cursor, disable line wrap, enable SGR mouse tracking.
_ENTER = "\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[?1000h\x1b[?1006h\x1b[2J"
# Leave: undo each of the above.
_LEAVE = "\x1b[?1000l\x1b[?1006l\x1b[?7h\x1b[?25h\x1b[?1049l"


class Terminal:
    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._saved: list | None = None
        self._saved_err: int | None = None
        self._devnull: int | None = None

    def __enter__(self) -> "Terminal":
        self._saved = termios.tcgetattr(self._fd)
        tty.setraw(self._fd)
        # Route native-library stderr (e.g. ffmpeg/libav decoder warnings) to
        # /dev/null for the duration of the session so it can't corrupt the
        # screen. Restored on exit, so crash tracebacks still surface.
        self._saved_err = os.dup(2)
        self._devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self._devnull, 2)
        sys.stdout.write(_ENTER)
        sys.stdout.flush()
        return self

    def __exit__(self, *exc) -> None:
        sys.stdout.write(_LEAVE)
        sys.stdout.flush()
        if self._saved is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        if self._saved_err is not None:
            os.dup2(self._saved_err, 2)
            os.close(self._devnull)
            os.close(self._saved_err)

    def write(self, data: str) -> None:
        sys.stdout.write(data)
        sys.stdout.flush()


class InputReader(threading.Thread):
    """Parses stdin in the background, dispatching scroll/pause/quit events.

    ``on_scroll(direction)`` is called with +1 (next) or -1 (previous).
    ``on_quit()`` is called to exit ('q', Ctrl-C, or a bare Escape).
    ``on_toggle()`` is called to toggle play/pause (Space).
    """

    # How long to wait after a lone ESC before deciding it's the Escape key
    # rather than the start of an escape sequence (arrows / mouse).
    _ESC_TIMEOUT = 0.15

    def __init__(
        self,
        on_scroll: Callable[[int], None],
        on_quit: Callable[[], None],
        on_toggle: Callable[[], None] = lambda: None,
        on_mute: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(daemon=True)
        self._fd = sys.stdin.fileno()
        self._on_scroll = on_scroll
        self._on_quit = on_quit
        self._on_toggle = on_toggle
        self._on_mute = on_mute
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        buf = b""
        while not self._stop.is_set():
            # Wait for input, but wake periodically to honour stop() and to
            # resolve a pending lone ESC into an Escape keypress.
            timeout = self._ESC_TIMEOUT if buf == b"\x1b" else 0.2
            r, _, _ = select.select([self._fd], [], [], timeout)
            if not r:
                if buf == b"\x1b":  # ESC with nothing following => Escape key
                    self._on_quit()
                    buf = b""
                continue
            try:
                data = os.read(self._fd, 1024)
            except (OSError, ValueError):
                break
            if not data:
                break
            buf = self._parse(buf + data)

    def _parse(self, buf: bytes) -> bytes:
        """Consume complete events from ``buf``, returning the leftover tail."""
        i = 0
        n = len(buf)
        while i < n:
            b = buf[i]
            if b in (ord("q"), 0x03):  # 'q' or Ctrl-C
                self._on_quit()
                return b""
            if b == 0x20:  # Space — play/pause
                self._on_toggle()
                i += 1
                continue
            if b in (ord("m"), ord("M")):  # mute/unmute
                self._on_mute()
                i += 1
                continue
            if b != 0x1b:  # not an escape sequence — ignore stray byte
                i += 1
                continue

            # Lone trailing ESC: keep it; run()'s timeout decides Escape-vs-seq.
            if i + 1 >= n:
                return buf[i:]
            if buf[i + 1] != ord("["):
                i += 1
                continue

            # SGR mouse: ESC [ < Cb ; Cx ; Cy (M|m)
            if i + 2 < n and buf[i + 2] == ord("<"):
                end = i + 3
                while end < n and buf[end] not in (ord("M"), ord("m")):
                    end += 1
                if end >= n:
                    return buf[i:]  # incomplete; wait for more
                self._handle_mouse(buf[i + 3 : end], buf[end])
                i = end + 1
                continue

            # Arrow keys: ESC [ A (up) / ESC [ B (down)
            if i + 2 < n:
                k = buf[i + 2]
                if k == ord("A"):
                    self._on_scroll(-1)
                    i += 3
                    continue
                if k == ord("B"):
                    self._on_scroll(1)
                    i += 3
                    continue
                # Some other CSI sequence; skip the ESC and continue.
                i += 2
                continue
            return buf[i:]
        return b""

    def _handle_mouse(self, params: bytes, term: int) -> None:
        try:
            cb = int(params.split(b";", 1)[0])
        except ValueError:
            return
        # Wheel events set bit 6 (64). 64 = wheel up, 65 = wheel down.
        if cb == 64:
            self._on_scroll(-1)
        elif cb == 65:
            self._on_scroll(1)
        # Left-button press (cb 0, 'M' = press not release) toggles play/pause.
        elif cb == 0 and term == ord("M"):
            self._on_toggle()
