"""From one moment of the mouth track to the face values sent to VTube Pro (ARKit / "Perfect Sync" names)."""
from __future__ import annotations

import random


def face_values(m: dict[str, float], strength: float = 1.0, blink: float = 0.0) -> dict[str, float]:
    jaw_in, level = m["jawOpen"], m["level"]
    # VTube Pro treats small mouth openings (below about a third) as tracker noise while your own microphone is quiet,
    # so every sung sound starts a little above that. Real silence stays at exactly 0, and the short ramp keeps the
    # mouth from popping open at the start of a note.
    jaw = min(1.0, min(1.0, jaw_in / 0.06) * (0.22 + 0.8 * jaw_in) * strength)
    wide = min(1.0, m["mouthStretch"] * strength)
    v = {
        "jawOpen": jaw,
        "mouthStretchLeft": wide * 0.8, "mouthStretchRight": wide * 0.8,
        "mouthPucker": min(1.0, m["mouthPucker"] * strength),
        "mouthFunnel": min(1.0, m["mouthFunnel"] * strength),
        "mouthLowerDownLeft": jaw * 0.25, "mouthLowerDownRight": jaw * 0.25,
        "mouthUpperUpLeft": jaw * 0.12, "mouthUpperUpRight": jaw * 0.12,
        "mouthSmileLeft": 0.1 * level + 0.25 * wide, "mouthSmileRight": 0.1 * level + 0.25 * wide,
        "browInnerUp": 0.3 * max(0.0, level - 0.6) / 0.4 * jaw_in,   # brows lift a little on big notes
        "eyeBlinkLeft": blink, "eyeBlinkRight": blink,
    }
    return {k: max(0.0, min(1.0, x)) for k, x in v.items()}


class Blinker:
    """Natural-looking blinks. While the plugin drives the face, VTube Pro takes the eyelids from the plugin too
    (they would otherwise stay wide open), so the plugin blinks for you."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self._next = self._rng.uniform(1.5, 4.0)
        self._start = -1.0

    def value(self, t: float) -> float:
        if self._start < 0 and t >= self._next:
            self._start = t
        if self._start >= 0:
            x = (t - self._start) / 0.17
            if x >= 1:
                self._start = -1.0
                self._next = t + (0.35 if self._rng.random() < 0.12 else self._rng.uniform(2.2, 6.0))
                return 0.05
            return 0.05 + 0.9 * (1 - abs(2 * x - 1))
        return 0.05
