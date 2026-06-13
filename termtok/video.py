"""Per-video frame decoding, looping and aspect-fit padding.

Each video is rendered into a buffer that exactly fills the viewport
(``height`` x ``width`` pixels, RGB). The original frame is scaled to fit
while preserving aspect ratio and centered on a black canvas. Because every
video buffer has identical dimensions, the feed can composite two of them with
a simple vertical slice during a scroll transition (see ``feed.py``).
"""

from __future__ import annotations

import cv2
import numpy as np


class VideoReader:
    """Lazily decodes a single video, looping forever, fit to a viewport.

    Frames are addressed by wall-clock time so a video keeps playing at its
    native frame rate regardless of how fast the render loop runs. Decoding is
    sequential (cheap) for normal forward playback and only seeks when the
    timeline wraps or jumps.
    """

    # If the desired frame is more than this many frames ahead, seek instead of
    # grabbing intermediate frames one by one.
    _SEEK_GAP = 8

    def __init__(self, path: str) -> None:
        self.path = path
        self._cap: cv2.VideoCapture | None = None
        self.fps = 30.0
        self.nframes = 1
        self._idx = -1
        self._buf: np.ndarray | None = None
        self._target: tuple[int, int] | None = None  # (width, height)

    def _open(self) -> None:
        if self._cap is not None:
            return
        self._cap = cv2.VideoCapture(self.path)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open video: {self.path}")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 1 else 30.0
        n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.nframes = n if n > 0 else 1

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._idx = -1
        self._buf = None

    def frame_at(self, t: float, width: int, height: int) -> np.ndarray:
        """Return the RGB buffer (height, width, 3) for playback time ``t``."""
        self._open()
        target = (width, height)
        fi = int(t * self.fps) % self.nframes

        if self._buf is not None and fi == self._idx and self._target == target:
            return self._buf

        assert self._cap is not None
        if fi < self._idx or fi > self._idx + self._SEEK_GAP or self._idx < 0:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        else:
            # Skip intermediate frames cheaply without decoding them.
            for _ in range(fi - self._idx - 1):
                self._cap.grab()

        ok, frame = self._cap.read()
        if not ok or frame is None:
            # End of stream or decode hiccup: rewind and try once more.
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            fi = 0
            if not ok or frame is None:
                # Give up gracefully with a black frame.
                self._idx = fi
                self._target = target
                self._buf = np.zeros((height, width, 3), np.uint8)
                return self._buf

        self._idx = fi
        self._target = target
        self._buf = self._fit(frame, width, height)
        return self._buf

    @staticmethod
    def _fit(frame: np.ndarray, width: int, height: int) -> np.ndarray:
        """Scale ``frame`` to fit (width, height), centered on black, as RGB."""
        vh, vw = frame.shape[:2]
        scale = min(width / vw, height / vh)
        nw = max(1, int(round(vw * scale)))
        nh = max(1, int(round(vh * scale)))
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        small = cv2.resize(frame, (nw, nh), interpolation=interp)

        canvas = np.zeros((height, width, 3), np.uint8)
        x = (width - nw) // 2
        y = (height - nh) // 2
        canvas[y : y + nh, x : x + nw] = small
        # OpenCV decodes BGR; the renderer emits RGB escapes.
        return np.ascontiguousarray(canvas[:, :, ::-1])
