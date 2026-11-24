"""Read and write WAV files with numpy only (PCM 8/16/24/32-bit and 32/64-bit float)."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


class WavError(ValueError):
    pass


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Return (samples float32 shaped [frames, channels] in -1..1, sample rate)."""
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] not in (b"RIFF", b"RF64") or data[8:12] != b"WAVE":
        raise WavError(f"{Path(path).name} is not a WAV file")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        body = pos + 8
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack_from("<HHIIHH", data, body)
            if tag == 0xFFFE and size >= 26:  # WAVE_FORMAT_EXTENSIBLE: the real tag is in the sub-format
                tag = struct.unpack_from("<H", data, body + 24)[0]
            fmt = (tag, ch, sr, bits)
        elif cid == b"data":
            if size == 0xFFFFFFFF or body + size > len(data):  # streamed / truncated file: take what is there
                size = len(data) - body
            raw = data[body:body + size]
            break
        pos = body + size + (size & 1)
    if fmt is None or raw is None:
        raise WavError(f"{Path(path).name} has no audio data")
    tag, ch, sr, bits = fmt
    if ch < 1 or sr < 1:
        raise WavError(f"{Path(path).name} has a broken header")
    if tag == 1:  # integer PCM
        if bits == 8:
            x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
        elif bits == 16:
            x = np.frombuffer(raw[: len(raw) // 2 * 2], "<i2").astype(np.float32) / 32768.0
        elif bits == 24:
            b = np.frombuffer(raw[: len(raw) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            x = (v - ((v & 0x800000) << 1)).astype(np.float32) / 8388608.0
        elif bits == 32:
            x = np.frombuffer(raw[: len(raw) // 4 * 4], "<i4").astype(np.float32) / 2147483648.0
        else:
            raise WavError(f"{bits}-bit WAV files are not supported")
    elif tag == 3:  # IEEE float
        if bits not in (32, 64):
            raise WavError(f"{bits}-bit float WAV files are not supported")
        w = bits // 8
        x = np.frombuffer(raw[: len(raw) // w * w], "<f4" if bits == 32 else "<f8").astype(np.float32)
    else:
        raise WavError("This WAV file is compressed. Please use a plain (PCM) WAV file.")
    n = len(x) // ch
    return np.nan_to_num(x[: n * ch].reshape(n, ch)), sr


def write_wav(path: str | Path, samples: np.ndarray, sr: int) -> None:
    """Write 16-bit PCM. `samples` is [frames] or [frames, channels] in -1..1."""
    x = np.asarray(samples, np.float32)
    if x.ndim == 1:
        x = x[:, None]
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).round().astype("<i2").tobytes()
    ch = x.shape[1]
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * 2, ch * 2, 16)
    Path(path).write_bytes(head + b"data" + struct.pack("<I", len(pcm)) + pcm)


def duration(path: str | Path) -> float:
    x, sr = read_wav(path)
    return len(x) / sr
