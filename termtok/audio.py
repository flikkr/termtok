"""Audio playback for the focused video, via ffplay.

The player decodes video frames itself, but has no audio. This controller runs
``ffplay`` as a detached subprocess to play the *focused* video's soundtrack —
started when the feed settles on a video, stopped when you scroll away, pause,
or mute. ffplay loops the audio (``-loop 0``) and seeks (``-ss``) so it joins at
the video's current position and re-syncs on every loop.

If ffplay isn't installed, audio is silently disabled (the player still runs).
"""

from __future__ import annotations

import logging
import subprocess

from . import tools

log = logging.getLogger("termtok.audio")


class AudioController:
    def __init__(self, volume: int = 70) -> None:
        self._volume = max(0, min(100, volume))
        self._muted = False
        self._proc: subprocess.Popen | None = None
        self._ffplay = tools.ffplay()
        if self._ffplay is None:
            log.warning("ffplay not found — audio disabled (install ffmpeg)")

    def available(self) -> bool:
        return self._ffplay is not None

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        self._muted = muted

    def _effective_volume(self) -> int:
        return 0 if self._muted else self._volume

    def play(self, path: str, offset: float = 0.0) -> None:
        """Play ``path`` looping, starting at ``offset`` seconds."""
        self.stop()
        if not self.available() or self._effective_volume() == 0:
            return
        cmd = [
            self._ffplay,
            "-nodisp",            # no video window
            "-hide_banner",
            "-loglevel", "quiet",
            "-loop", "0",          # loop forever
            "-volume", str(self._effective_volume()),
            "-ss", f"{max(0.0, offset):.3f}",
            path,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,   # don't let ffplay eat our keystrokes
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            log.exception("failed to start ffplay")
            self._proc = None

    def stop(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=0.3)
        except subprocess.TimeoutExpired:
            proc.kill()
