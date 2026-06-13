"""Truecolor terminal renderer using half-block characters.

Each terminal cell shows two stacked pixels via the upper-half-block glyph
``▀``: the foreground color paints the top pixel, the background color the
bottom one. This doubles vertical resolution and yields roughly square pixels.

To stay flicker-free and fast, the renderer keeps the previously drawn frame
and only re-emits cells that changed, moving the cursor over unchanged runs.
ANSI color escapes are run-length coded — emitted only when the color differs
from the previous cell in a run.
"""

from __future__ import annotations

import numpy as np

UPPER_HALF = "▀"  # ▀


class Renderer:
    def __init__(self) -> None:
        self._prev_top: np.ndarray | None = None
        self._prev_bot: np.ndarray | None = None

    def reset(self) -> None:
        """Force a full redraw on the next frame (e.g. after a resize)."""
        self._prev_top = None
        self._prev_bot = None

    def render(self, pixels: np.ndarray) -> str:
        """Build the escape-sequence string for an RGB image.

        ``pixels`` has shape (rows*2, cols, 3); even rows are the top pixels of
        each cell, odd rows the bottom pixels.
        """
        top = pixels[0::2]
        bot = pixels[1::2]
        rows, cols = top.shape[0], top.shape[1]

        force = (
            self._prev_top is None
            or self._prev_top.shape != top.shape
        )
        if force:
            changed = np.ones((rows, cols), dtype=bool)
        else:
            changed = np.any(top != self._prev_top, axis=2) | np.any(
                bot != self._prev_bot, axis=2
            )

        top_l = top.tolist()
        bot_l = bot.tolist()
        chg_l = changed.tolist()

        out: list[str] = []
        for r in range(rows):
            row_changed = chg_l[r]
            tr = top_l[r]
            br = bot_l[r]
            c = 0
            while c < cols:
                if not row_changed[c]:
                    c += 1
                    continue
                # Start a run of changed cells; move the cursor to its start.
                out.append(f"\x1b[{r + 1};{c + 1}H")
                cur_fg: list[int] | None = None
                cur_bg: list[int] | None = None
                while c < cols and row_changed[c]:
                    fg = tr[c]
                    bg = br[c]
                    if fg != cur_fg or bg != cur_bg:
                        out.append(
                            f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}"
                            f";48;2;{bg[0]};{bg[1]};{bg[2]}m"
                        )
                        cur_fg = fg
                        cur_bg = bg
                    out.append(UPPER_HALF)
                    c += 1

        self._prev_top = top.copy()
        self._prev_bot = bot.copy()
        return "".join(out)
