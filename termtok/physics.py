"""TikTok-style scroll physics.

The feed position is a continuous float ``pos`` measured in video units: 0.0 is
the first video fully on screen, 1.0 the second, and 1.5 means we're halfway
through the transition between the second and third.

The feel we want:
  * a flick of the wheel kicks ``pos`` toward the next/previous video and it
    snaps cleanly into place (no manual half-scrolled resting state),
  * a fast multi-notch flick carries momentum across several videos,
  * the motion eases out smoothly rather than stopping abruptly,
  * you can't scroll past the ends — they damp to a stop.

This is modeled as a critically-damped spring pulling ``pos`` toward an integer
``target``. The target is chosen by the *direction of motion*: while the feed
is moving it aims at the next integer that way, so momentum naturally chains
from one video to the next; when nearly at rest it snaps to the closest video.
Wheel/key input injects velocity, which the spring then shapes into a clean,
eased landing.
"""

from __future__ import annotations

import threading


class ScrollPhysics:
    # Spring stiffness (rad/s). Higher = snappier, shorter settle time.
    OMEGA = 13.0
    # Velocity (videos/s) added per wheel notch / key press.
    KICK = 5.0
    # Hard cap on velocity so a frantic scroll stays controllable. This is the
    # main "sensitivity" lever: high-resolution wheels/trackpads fire many notch
    # events per gesture, and this bounds how many videos one burst can fling.
    MAX_VEL = 14.0
    # How far ahead current velocity "throws" the landing point (seconds).
    # Tuned to ~1/KICK so one notch lands one video on, two notches two on, etc.
    # This is what lets a flick carry momentum across videos instead of the
    # spring braking to the immediate neighbor.
    PROJECTION = 0.16
    # Stop integrating once we're this close to rest, to avoid endless jitter.
    SETTLE_POS = 1e-3
    SETTLE_VEL = 1e-3
    # Extra damping applied to motion that overshoots past the ends.
    EDGE_DAMP = 0.80

    def __init__(self, count: int) -> None:
        self.count = max(1, count)
        self._pos = 0.0
        self._vel = 0.0
        self._lock = threading.Lock()

    def kick(self, direction: int) -> None:
        """Nudge the feed by one notch. +1 = next video, -1 = previous."""
        with self._lock:
            self._vel += direction * self.KICK
            self._vel = _clamp(self._vel, -self.MAX_VEL, self.MAX_VEL)

    def update(self, dt: float) -> None:
        """Advance the simulation by ``dt`` seconds."""
        if dt <= 0:
            return
        # Sub-step for stability when the frame time is large.
        steps = max(1, int(dt / 0.008) + 1)
        h = dt / steps
        with self._lock:
            for _ in range(steps):
                self._step(h)

    def _step(self, h: float) -> None:
        pos, vel = self._pos, self._vel
        last = self.count - 1

        # Project where momentum is heading and snap to the nearest video there.
        # At rest this is just round(pos); under a flick it lands several ahead.
        target = round(pos + vel * self.PROJECTION)
        target = _clamp(target, 0, last)

        # Critically-damped spring toward the target video.
        accel = self.OMEGA * self.OMEGA * (target - pos) - 2.0 * self.OMEGA * vel
        vel += accel * h
        pos += vel * h

        # Rubber-band stop at the ends.
        if pos < 0.0:
            pos = 0.0
            vel *= self.EDGE_DAMP if vel < 0 else 1.0
            if vel < 0:
                vel = 0.0
        elif pos > last:
            pos = float(last)
            vel *= self.EDGE_DAMP if vel > 0 else 1.0
            if vel > 0:
                vel = 0.0

        # Snap to rest once close enough to the target with little speed.
        if (
            abs(vel) < self.SETTLE_VEL
            and abs(target - pos) < self.SETTLE_POS
        ):
            pos = float(target)
            vel = 0.0

        self._pos, self._vel = pos, vel

    @property
    def position(self) -> float:
        with self._lock:
            return self._pos

    @property
    def at_rest(self) -> bool:
        with self._lock:
            return self._vel == 0.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x
