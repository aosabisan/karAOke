"""Silent test signals: a sung-vowel synthesiser (harmonics shaped by formants). Nothing is ever played."""
import numpy as np

VOWELS = {"a": (800, 1200, 2600), "i": (300, 2300, 3000), "u": (320, 800, 2300)}


def vowel(kind: str, seconds: float, sr: int = 44100, f0: float = 190.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    f0t = f0 * (1 + 0.01 * np.sin(2 * np.pi * 5.5 * t))  # a little vibrato
    phase = 2 * np.pi * np.cumsum(f0t) / sr
    out = np.zeros_like(t)
    for k in range(1, int(5000 / f0)):
        f = k * f0
        gain = sum(1.0 / (1.0 + ((f - fc) / bw) ** 2) for fc, bw in zip(VOWELS[kind], (70, 90, 120))) / k ** 0.6
        out += gain * np.sin(k * phase)
    out *= amp / (np.abs(out).max() + 1e-9)
    fade = int(0.02 * sr)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out.astype(np.float32)


def hiss(seconds: float, sr: int = 44100, amp: float = 0.12, seed: int = 1) -> np.ndarray:
    """An 's' sound: noise above ~4 kHz."""
    n = int(seconds * sr)
    spec = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / sr)
    spec[f < 4500] = 0
    x = np.fft.irfft(spec, n)
    return (x * amp / (np.abs(x).max() + 1e-9)).astype(np.float32)


def silence(seconds: float, sr: int = 44100) -> np.ndarray:
    return np.zeros(int(seconds * sr), np.float32)
