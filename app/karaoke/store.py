"""Where things are kept on this computer: settings, the song library and the voice models folder.

Nothing here ever leaves the computer. Default folder: %LOCALAPPDATA%\\AosabiKaraoke (Windows) or
~/.local/share/aosabi-karaoke; set AOSABI_KARAOKE_DATA to use another one.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

DEFAULTS = {
    "vtsPort": 8001,            # VTube Pro's plugin port (Track tab -> VTube Studio API (plugins))
    "vtpPort": 5191,            # VTube Pro helper (used only to start / stop the dance)
    "lipSync": True,
    "dance": True,
    "danceEmote": "dance",
    "mouthLeadMs": 60,          # send each mouth shape this much early (VTube Pro smooths, which adds a little delay)
    "mouthStrength": 1.0,
    "blink": True,
    "musicVolume": 0.9,
    "vocalVolume": 0.9,
    "splitter": "audio-separator",
    "splitModel": "karaoke",
    "torch": "cpu",             # cpu | cu124 | cu128 (NVIDIA; cu128 for RTX 50-series)
    "voicesDir": "",            # empty = <data>/voices
    "voiceEngine": {"rvc": "rvc-python", "sovits": "so-vits-svc-fork"},
    "applioDir": "",
    "customVoiceCommand": "",
}


def data_dir() -> Path:
    env = os.environ.get("AOSABI_KARAOKE_DATA")
    if env:
        p = Path(env)
    elif os.name == "nt":
        p = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "AosabiKaraoke"
    else:
        p = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "aosabi-karaoke"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, value) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=1), "utf-8")
    os.replace(tmp, path)


_ID = re.compile(r"^[a-z0-9]{8,32}$")
_SAFE = re.compile(r"[^\w .,()'&+-]+", re.UNICODE)
AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wma", ".aiff", ".aif"}


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else data_dir()
        self.songs_dir = self.root / "songs"
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        (self.root / "voices").mkdir(exist_ok=True)
        self.settings = {**DEFAULTS, **_read(self.root / "settings.json", {})}

    # ---- settings
    def update_settings(self, patch: dict) -> dict:
        for k, v in patch.items():
            if k in DEFAULTS and (type(v) is type(DEFAULTS[k]) or (isinstance(DEFAULTS[k], float) and isinstance(v, int))):
                if k in ("vtsPort", "vtpPort") and not 1024 <= v <= 65535:
                    continue
                self.settings[k] = v
        _write(self.root / "settings.json", self.settings)
        return self.settings

    @property
    def voices_dir(self) -> Path:
        return Path(self.settings["voicesDir"]) if self.settings["voicesDir"] else self.root / "voices"

    # ---- the plugin's key for VTube Pro (given once, when you press Allow there)
    def token(self) -> str:
        return _read(self.root / "vtube-pro-key.json", {}).get("token", "")

    def set_token(self, token: str) -> None:
        _write(self.root / "vtube-pro-key.json", {"token": token})

    # ---- songs
    def song_dir(self, sid: str) -> Path:
        if not _ID.match(sid):
            raise KeyError(sid)
        return self.songs_dir / sid

    def song(self, sid: str) -> dict:
        meta = _read(self.song_dir(sid) / "song.json", None)
        if not meta:
            raise KeyError(sid)
        d = self.song_dir(sid)
        meta["has"] = {"instrumental": (d / "instrumental.wav").exists(), "vocals": (d / "vocals.wav").exists(),
                       "mouth": (d / "mouth.json").exists(),
                       "voices": sorted(p.stem[6:] for p in d.glob("voice-*.wav"))}
        return meta

    def songs(self) -> list[dict]:
        out = []
        for d in self.songs_dir.iterdir():
            try:
                out.append(self.song(d.name))
            except KeyError:
                pass
        return sorted(out, key=lambda m: -m.get("added", 0))

    def add_song(self, title: str, original_name: str) -> dict:
        sid = uuid.uuid4().hex[:12]
        ext = Path(original_name).suffix.lower()
        if ext not in AUDIO_EXT:
            raise ValueError(f"'{ext or original_name}' is not an audio file this can read. Use one of: {', '.join(sorted(AUDIO_EXT))}")
        clean = re.sub(r"\s+", " ", _SAFE.sub(" ", title or Path(original_name).stem)).strip()[:80] or "Song"
        d = self.songs_dir / sid
        d.mkdir()
        meta = {"id": sid, "title": clean, "source": "source" + ext, "added": time.time(), "state": "new", "note": ""}
        _write(d / "song.json", meta)
        return meta

    def save_song(self, meta: dict) -> None:
        _write(self.song_dir(meta["id"]) / "song.json", {k: v for k, v in meta.items() if k != "has"})

    def delete_song(self, sid: str) -> None:
        shutil.rmtree(self.song_dir(sid), ignore_errors=True)

    def mouth(self, sid: str) -> dict | None:
        return _read(self.song_dir(sid) / "mouth.json", None)

    def save_mouth(self, sid: str, track: dict) -> None:
        (self.song_dir(sid) / "mouth.json").write_text(json.dumps(track, separators=(",", ":")), "utf-8")

    # ---- voice models the user put in the voices folder
    def voices(self) -> list[dict]:
        """RVC: a .pth file (+ optional .index beside it). so-vits-svc: a folder with G_*.pth and config.json."""
        out, root = [], self.voices_dir
        if not root.is_dir():
            return out
        for cfg in sorted(root.rglob("config.json")):
            g = sorted(cfg.parent.glob("G_*.pth"))
            if g:
                out.append({"id": _voice_id(cfg.parent, root), "name": cfg.parent.name, "kind": "sovits", "model": str(g[-1]), "config": str(cfg)})
        taken = {Path(v["model"]).parent for v in out}
        for pth in sorted(root.rglob("*.pth")):
            if pth.parent in taken or pth.name.startswith(("D_", "G_")):
                continue
            idx = sorted(pth.parent.glob("*.index"))
            pick = next((i for i in idx if pth.stem.lower() in i.stem.lower()), idx[0] if len(idx) == 1 else None)
            out.append({"id": _voice_id(pth, root), "name": pth.stem, "kind": "rvc", "model": str(pth), "index": str(pick) if pick else ""})
        return out


def _voice_id(p: Path, root: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(p.relative_to(root).with_suffix("")).lower()).strip("-")[:48] or "voice"
