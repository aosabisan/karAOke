"""Turn a sung vocal track into a mouth track (numpy only, nothing is played).

For every 1/60 s it works out how open the jaw is, how wide the lips are ("ee") and how round they are ("oo"),
from how loud the voice is and where its energy sits:

    energy around 0.6-1.4 kHz -> open jaw ("aa")     energy at 1.7-3.4 kHz -> wide lips ("ee")
    energy only down low      -> round lips ("oo")
    hiss above 4 kHz with no voice ("s", "sh") -> teeth nearly together

The result is a small dictionary {fps, n, ch: {name: [0..255, ...]}} that is saved next to the song and
sampled while the song plays (see `sample`).
"""
from __future__ import annotations

import numpy as np

FPS = 60
SR = 16000
CHANNELS = ("jawOpen", "mouthStretch", "mouthPucker", "mouthFunnel", "level")
_WIN = 512          # 32 ms analysis window


def _to_mono_16k(x: np.ndarray, sr: int) -> np.ndarray:
    x = np.asarray(x, np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    if len(x) == 0 or sr == SR:
        return x
    if sr > SR:  # low-pass below the new Nyquist before picking samples
        taps = 63
        k = np.arange(taps) - (taps - 1) / 2
        h = np.sinc(k * (SR / sr) * 0.92) * np.hamming(taps)
        x = np.convolve(x, (h / h.sum()).astype(np.float32), mode="same")
    n = int(len(x) * SR / sr)
    return np.interp(np.arange(n) * (sr / SR), np.arange(len(x)), x).astype(np.float32)


def _frames(x: np.ndarray, fps: int) -> np.ndarray:
    n = int(np.ceil(len(x) / SR * fps))
    pad = np.concatenate([np.zeros(_WIN // 2, np.float32), x, np.zeros(_WIN, np.float32)])
    starts = (np.arange(n) * (SR / fps)).astype(int)
    return pad[starts[:, None] + np.arange(_WIN)[None, :]]


def _vowel_features(spec: np.ndarray, freqs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two numbers per frame from the voice's spectrum (0..1 each):
    openness  where the energy below 1.5 kHz sits (high = "aa", the first resonance is high)
    front     how much of the energy sits at 1.7-3.4 kHz (high = "ee", the second resonance is high)
    Band energies are used instead of exact formant tracking: they stay steady on high sung notes, where the
    harmonics are too far apart for a formant tracker."""
    w = spec * freqs[None, :]                      # undo part of the voice's natural downward tilt
    lo = (freqs >= 200) & (freqs < 1500)
    hi = (freqs >= 1700) & (freqs < 3400)
    e_lo = w[:, lo].sum(axis=1) + 1e-12
    e_hi = w[:, hi].sum(axis=1)
    centroid = (w[:, lo] * freqs[None, lo]).sum(axis=1) / e_lo
    openness = np.clip((centroid - 560) / (900 - 560), 0, 1)
    front = np.clip((e_hi / (e_lo + e_hi) - 0.45) / 0.3, 0, 1)
    return openness, front


def _median(x: np.ndarray, width: int = 5) -> np.ndarray:
    pad = width // 2
    xp = np.pad(x, pad, mode="edge")
    return np.median(np.stack([xp[i: i + len(x)] for i in range(width)]), axis=0)


def _ease(x: np.ndarray, attack_s: float, release_s: float, fps: int) -> np.ndarray:
    up, down = 1 - np.exp(-1 / (attack_s * fps)), 1 - np.exp(-1 / (release_s * fps))
    out = np.empty_like(x)
    v = 0.0
    for i, t in enumerate(x):
        v += (t - v) * (up if t > v else down)
        out[i] = v
    return out


def analyse(samples: np.ndarray, sr: int, fps: int = FPS) -> dict:
    x = _to_mono_16k(samples, sr)
    if len(x) == 0:
        return {"fps": fps, "n": 0, "ch": {c: [] for c in CHANNELS}}
    frames = _frames(x, fps)
    win = np.hanning(_WIN).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    freqs = np.fft.rfftfreq(_WIN, 1 / SR)
    spec[:, freqs < 150] = 0                                     # bass / kick-drum leftovers in a split vocal are not singing
    total = spec.sum(axis=1) + 1e-12
    high = spec[:, freqs >= 4000].sum(axis=1) / total            # share of the energy that is hiss
    db = 10 * np.log10(total / _WIN + 1e-12)

    # loudness, measured against this recording's own loud parts (so quiet and loud files behave the same)
    ref = np.percentile(db, 95)
    active = db > ref - 45
    if not active.any():
        return {"fps": fps, "n": len(frames), "ch": {c: [0] * len(frames) for c in CHANNELS}}
    floor = ref - 32
    level = np.clip((db - floor) / (ref - 8 - floor), 0, 1)
    level[db < ref - 38] = 0

    sib = np.clip((high - 0.45) / 0.3, 0, 1) * (level > 0)
    openness, front = _vowel_features(spec, freqs)
    openness = _median(np.where(level > 0, openness, 0.5))
    front = _median(np.where(level > 0, front, 0.5))
    wide = front * (1 - 0.6 * openness)                        # "ee"
    rnd = (1 - front) * np.clip((0.6 - openness) / 0.6, 0, 1)    # "oo" / "oh"

    voice = level * (1 - sib)
    jaw = voice * (0.38 + 0.62 * openness) * (1 - 0.35 * np.maximum(wide, rnd)) + level * sib * 0.12
    out = {
        "jawOpen": _ease(jaw, 0.022, 0.07, fps),
        "mouthStretch": _ease(voice * wide + level * sib * 0.35, 0.04, 0.09, fps),
        "mouthPucker": _ease(voice * rnd * 0.9, 0.04, 0.09, fps),
        "mouthFunnel": _ease(voice * rnd * 0.55, 0.04, 0.09, fps),
        "level": _ease(level, 0.02, 0.08, fps),
    }
    return {"fps": fps, "n": len(frames),
            "ch": {k: np.clip(np.round(v * 255), 0, 255).astype(int).tolist() for k, v in out.items()}}


def sample(track: dict, t: float) -> dict[str, float]:
    """Channel values (0..1) at song time `t` seconds, blended between the two nearest frames."""
    n, fps = track.get("n", 0), track.get("fps", FPS)
    pos = t * fps
    if n == 0 or pos < 0 or pos > n - 1:
        return {c: 0.0 for c in CHANNELS}
    i = int(pos)
    j = min(i + 1, n - 1)
    w = pos - i
    return {c: (track["ch"][c][i] * (1 - w) + track["ch"][c][j] * w) / 255.0 for c in CHANNELS}
