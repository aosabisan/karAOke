"""The heavy lifting is done by other people's free tools, which YOU install (one button each on the Setup page):
the vocal splitter and the voice changers. None of them is part of this package. This file only knows how to
install them from their official sources into their own folders, and how to start them.

Every tool gets its own Python environment under <data>/engines/<name>, made with Astral's `uv`, so they can never
disturb each other, VTube Pro or anything else on the computer. Removing one is deleting its folder.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
from pathlib import Path

RUNNERS = Path(__file__).resolve().parent.parent / "runners"
TORCH_INDEX = {"cu124": "https://download.pytorch.org/whl/cu124", "cu128": "https://download.pytorch.org/whl/cu128"}

ENGINES: dict[str, dict] = {
    "audio-separator": {
        "kind": "split", "title": "Vocal splitter: audio-separator",
        "about": "Splits a song into the music and the singing. It downloads the splitting model you pick the first time you use it.",
        "homepage": "https://github.com/nomadkaraoke/python-audio-separator",
        "licence": "The program is MIT-licensed. Every splitting model has its own terms, set by whoever trained it: read them before you use a model for paid work.",
        "python": "3.11", "packages": {"cpu": ["audio-separator[cpu]"], "gpu": ["audio-separator[gpu]"]},
        "check": "audio_separator", "size": "about 2-6 GB with its models",
    },
    "rvc-python": {
        "kind": "voice", "format": "rvc", "title": "Voice changer for RVC models: rvc-python",
        "about": "Sings the vocal track with an RVC voice model (.pth, with its .index file if you have one).",
        "homepage": "https://github.com/daswer123/rvc-python",
        "licence": "MIT-licensed. Only use voices you have the right to use: your own, or with the person's permission.",
        # (setuptools<81: one of its parts, pyworld, still needs the "pkg_resources" module that newer setuptools dropped)
        "python": "3.10", "packages": {"cpu": ["rvc-python", "setuptools<81"], "gpu": ["rvc-python", "setuptools<81"]},
        "check": "rvc_python", "size": "about 3-6 GB",
    },
    "so-vits-svc-fork": {
        "kind": "voice", "format": "sovits", "title": "Voice changer for so-vits-svc models: so-vits-svc-fork",
        "about": "Sings the vocal track with a so-vits-svc 4.x model (a folder with G_....pth and config.json).",
        "homepage": "https://github.com/voicepaw/so-vits-svc-fork",
        "licence": "Apache-2.0 / MIT. Only use voices you have the right to use.",
        "python": "3.10", "packages": {"cpu": ["so-vits-svc-fork"], "gpu": ["so-vits-svc-fork"]},
        "check": "so_vits_svc_fork", "size": "about 3-6 GB",
    },
}

# Splitting models people commonly use with audio-separator. "karaoke" removes only the lead singer and keeps the
# backing vocals in the music, which is what a karaoke night wants. You can type any other model file name instead.
SPLIT_MODELS = {
    "karaoke": {"file": "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt", "title": "Karaoke (removes the lead singer, keeps backing vocals)"},
    "full": {"file": "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "title": "All vocals out (cleanest music, slow without an NVIDIA card)"},
    "fast": {"file": "UVR-MDX-NET-Inst_HQ_3.onnx", "title": "Fast (fine on a computer without an NVIDIA card)"},
}


def find_uv() -> str | None:
    exe = "uv.exe" if os.name == "nt" else "uv"
    return shutil.which("uv") or next((str(p) for p in (Path.home() / ".local" / "bin" / exe, Path.home() / ".cargo" / "bin" / exe) if p.exists()), None)


class Engines:
    def __init__(self, root: Path):
        self.root = root / "engines"

    def python(self, name: str) -> Path:
        d = self.root / name
        return d / "Scripts" / "python.exe" if os.name == "nt" else d / "bin" / "python"

    def installed(self, name: str) -> bool:
        return self.python(name).exists() and (self.root / name / ".installed").exists()

    def status(self) -> list[dict]:
        return [{"id": k, **{f: v[f] for f in ("kind", "title", "about", "homepage", "licence", "size")},
                 "format": v.get("format", ""), "installed": self.installed(k)} for k, v in ENGINES.items()]

    def install_steps(self, name: str, torch: str) -> list[list[str]]:
        e, uv = ENGINES[name], find_uv()
        if not uv:
            raise RuntimeError("The installer tool 'uv' was not found. Close this window and start Aosabi Karaoke again: the start file offers to get it.")
        env, py = str(self.root / name), str(self.python(name))
        steps = [[uv, "venv", "--python", e["python"], "--allow-existing", env],
                 [uv, "pip", "install", "--python", py, *e["packages"]["gpu" if torch in TORCH_INDEX else "cpu"]]]
        if torch in TORCH_INDEX:   # swap in the NVIDIA build of PyTorch (from pytorch.org)
            steps.append([uv, "pip", "install", "--python", py, "--reinstall-package", "torch", "--reinstall-package", "torchaudio",
                          "torch", "torchaudio", "--index-url", TORCH_INDEX[torch]])
        steps.append([py, "-c", f"import {e['check']}; print('{name} is ready')"])
        return steps

    def mark_installed(self, name: str) -> None:
        (self.root / name / ".installed").write_text("ok", "utf-8")

    def remove(self, name: str) -> None:
        if name in ENGINES:
            shutil.rmtree(self.root / name, ignore_errors=True)

    # ---- commands that do the work
    def split_command(self, settings: dict, source: Path, outdir: Path) -> list[str]:
        if not self.installed("audio-separator"):
            raise RuntimeError("The vocal splitter is not installed yet. Open Setup and press Install next to it "
                               "(or add the song with its two ready-made tracks instead).")
        model = SPLIT_MODELS.get(settings["splitModel"], {}).get("file", settings["splitModel"])
        return [str(self.python("audio-separator")), str(RUNNERS / "split_audio_separator.py"), "--input", str(source),
                "--outdir", str(outdir), "--model", model, "--models-dir", str(self.root / "split-models")]

    def voice_command(self, settings: dict, voice: dict, source: Path, out: Path, pitch: int) -> list[str]:
        custom = settings.get("customVoiceCommand", "").strip()
        fill = {"input": str(source), "output": str(out), "model": voice["model"], "index": voice.get("index", ""),
                "config": voice.get("config", ""), "pitch": str(pitch)}
        if custom:   # your own tool: any command line with {input} {output} {model} {index} {config} {pitch}
            return [part.format(**fill).strip('"') for part in shlex.split(custom, posix=os.name != "nt")]
        if voice["kind"] == "sovits":
            if not self.installed("so-vits-svc-fork"):
                raise RuntimeError("The voice changer for so-vits-svc models is not installed yet. Open Setup and press Install next to it.")
            return [str(self.python("so-vits-svc-fork")), str(RUNNERS / "voice_sovits.py"), "--input", fill["input"], "--output", fill["output"],
                    "--model", fill["model"], "--config", fill["config"], "--pitch", fill["pitch"]]
        if settings["voiceEngine"].get("rvc") == "applio":
            root = Path(settings.get("applioDir", ""))
            py = root / "env" / ("python.exe" if os.name == "nt" else "bin/python")
            if not (root / "core.py").exists() or not py.exists():
                raise RuntimeError("Applio was not found in the folder set on the Setup page (it should contain core.py and an env folder).")
            cmd = [str(py), str(root / "core.py"), "infer", "--pitch", fill["pitch"], "--input_path", fill["input"], "--output_path", fill["output"],
                   "--pth_path", fill["model"], "--f0_method", "rmvpe"]
            return cmd + (["--index_path", fill["index"]] if fill["index"] else [])
        if not self.installed("rvc-python"):
            raise RuntimeError("The voice changer for RVC models is not installed yet. Open Setup and press Install next to it.")
        return [str(self.python("rvc-python")), str(RUNNERS / "voice_rvc.py"), "--input", fill["input"], "--output", fill["output"],
                "--model", fill["model"], "--index", fill["index"], "--pitch", fill["pitch"]]


async def run(cmd: list[str], on_line, cwd: Path | None = None) -> None:
    """Run one command at below-normal priority, passing its output on line by line. Raises if it fails."""
    flags = 0x00004000 | 0x08000000 if os.name == "nt" else 0   # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=cwd,
                                                env=env, creationflags=flags) if os.name == "nt" else \
        await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=cwd, env=env,
                                             preexec_fn=lambda: os.nice(10))
    tail: list[str] = []
    try:
        buf = b""
        while chunk := await proc.stdout.read(4096):
            buf += chunk
            *lines, buf = buf.replace(b"\r", b"\n").split(b"\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    tail = (tail + [line])[-12:]
                    on_line(line)
        code = await proc.wait()
    except asyncio.CancelledError:
        proc.kill()
        raise
    if code != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} stopped with an error:\n" + "\n".join(tail[-6:]))
