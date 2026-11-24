"""The program itself: a small web server on this computer only (http://127.0.0.1:5290) that serves the Karaoke page,
keeps the song library, runs the splitting / voice jobs and sends the mouth to VTube Pro while a song plays.

Nothing is reachable from other computers or from web sites: it listens on 127.0.0.1 only, refuses requests whose
Host is not this computer, and refuses changes that do not come from its own page.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path

import aiohttp
import numpy as np
from aiohttp import web

from . import __version__, mouth, wavio
from .engines import ENGINES, SPLIT_MODELS, Engines, find_uv, run
from .face import Blinker, face_values
from .store import Store
from .vts import VtsLink

WEB = Path(__file__).resolve().parent / "web"
MAX_UPLOAD = 600 * 1024 * 1024
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


@web.middleware
async def local_only(request: web.Request, handler):
    host = request.headers.get("Host", "").rsplit(":", 1)[0] if not request.headers.get("Host", "").startswith("[") else request.headers["Host"].split("]")[0] + "]"
    if host not in LOCAL_HOSTS:
        raise web.HTTPMisdirectedRequest(text="This page only works on this computer.")
    origin = request.headers.get("Origin")
    if origin and origin.split("://")[-1].rsplit(":", 1)[0] not in LOCAL_HOSTS:
        raise web.HTTPForbidden(text="Not allowed from another site.")
    if request.method not in ("GET", "HEAD") and request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
        raise web.HTTPForbidden(text="Not allowed from another site.")
    return await handler(request)


class Karaoke:
    def __init__(self, store: Store):
        self.store = store
        self.engines = Engines(store.root)
        self.link = VtsLink(lambda: store.settings["vtsPort"], store.token, store.set_token)
        self.link.on_change = self.changed
        self.pages: set[web.WebSocketResponse] = set()
        self.jobs: list[dict] = []
        self.queue: asyncio.Queue = asyncio.Queue()
        self.clock = {"song": "", "pos": 0.0, "playing": False, "at": 0.0}
        self.track: tuple[str, dict | None] = ("", None)
        self.dancing = False
        self.dance_note = ""
        self.live: bool | None = None
        self._dirty = asyncio.Event()

    # ------------------------------------------------------------ state for the page
    def state(self) -> dict:
        s = self.store
        return {"version": __version__, "settings": s.settings, "songs": s.songs(), "voices": s.voices(), "voicesDir": str(s.voices_dir),
                "dataDir": str(s.root), "link": {"state": self.link.state, "detail": self.link.detail, "sent": self.link.sent},
                "engines": self.engines.status(), "splitModels": SPLIT_MODELS, "uv": bool(find_uv()), "jobs": self.jobs[-8:],
                "danceNote": self.dance_note, "live": self.live}

    def changed(self) -> None:
        self._dirty.set()

    async def pusher(self) -> None:
        while True:
            await self._dirty.wait()
            await asyncio.sleep(0.15)      # several changes in a row become one message
            self._dirty.clear()
            msg = json.dumps({"t": "state", "state": self.state()})
            for ws in list(self.pages):
                try:
                    await ws.send_str(msg)
                except (ConnectionError, RuntimeError):
                    self.pages.discard(ws)

    # ------------------------------------------------------------ jobs (one at a time)
    def add_job(self, title: str, work) -> dict:
        job = {"id": uuid.uuid4().hex[:8], "title": title, "state": "waiting", "line": "", "error": ""}
        self.jobs.append(job)
        self.queue.put_nowait((job, work))
        self.changed()
        return job

    async def worker(self) -> None:
        while True:
            job, work = await self.queue.get()
            job["state"] = "running"
            self.changed()

            def line(text: str, job=job) -> None:
                job["line"] = text[-160:]
                self.changed()
            try:
                await work(line)
                job["state"], job["line"] = "done", "Finished."
            except Exception as e:  # noqa: BLE001  (shown to the user in plain words)
                job["state"], job["error"] = "error", str(e)[-900:]
            self.changed()

    def install_engine(self, name: str) -> dict:
        if name not in ENGINES:
            raise web.HTTPNotFound()

        async def work(line) -> None:
            for step in self.engines.install_steps(name, self.store.settings["torch"]):
                line("Starting: " + " ".join(Path(step[0]).name if i == 0 else p for i, p in enumerate(step[:4])) + " ...")
                await run(step, line)
            self.engines.mark_installed(name)
        return self.add_job(f"Install {ENGINES[name]['title']}", work)

    def process_song(self, sid: str, vocals: str, voice_id: str, pitch: int) -> dict:
        meta = self.store.song(sid)
        d = self.store.song_dir(sid)

        async def work(line) -> None:
            meta["state"], meta["note"] = "working", ""
            self.store.save_song(meta)
            try:
                if not ((d / "vocals.wav").exists() and (d / "instrumental.wav").exists()):
                    tmp = d / "split.tmp"
                    shutil.rmtree(tmp, ignore_errors=True)
                    await run(self.engines.split_command(self.store.settings, d / meta["source"], tmp), line)
                    for name in ("vocals.wav", "instrumental.wav"):
                        os.replace(tmp / name, d / name)
                    shutil.rmtree(tmp, ignore_errors=True)
                if not (d / "mouth.json").exists():
                    line("Working out the mouth shapes from the singing...")
                    x, sr = await asyncio.to_thread(wavio.read_wav, d / "vocals.wav")
                    self.store.save_mouth(sid, await asyncio.to_thread(mouth.analyse, x, sr))
                if vocals == "voice":
                    voice = next((v for v in self.store.voices() if v["id"] == voice_id), None)
                    if not voice:
                        raise RuntimeError("That voice model is no longer in your voices folder.")
                    out = d / f"voice-{voice['id']}_{pitch:+d}.wav"
                    if not out.exists():
                        tmp_out = d / "voice.tmp.wav"
                        await run(self.engines.voice_command(self.store.settings, voice, d / "vocals.wav", tmp_out, pitch), line)
                        line("Matching the loudness of the new voice to the original...")
                        await asyncio.to_thread(match_loudness, d / "vocals.wav", tmp_out, out)
                        tmp_out.unlink(missing_ok=True)
                meta["state"] = "ready"
            except Exception as e:
                meta["state"], meta["note"] = ("ready" if (d / "mouth.json").exists() else "error"), str(e)[-600:]
                raise
            finally:
                self.store.save_song(meta)
        return self.add_job(f"Prepare \"{meta['title']}\"", work)

    # ------------------------------------------------------------ while a song plays
    def position(self) -> float | None:
        """Where the song is right now (seconds), or None when nothing is playing or the page went quiet."""
        c, now = self.clock, time.monotonic()
        if not c["playing"] or now - c["at"] > 1.5:
            return None
        return c["pos"] + (now - c["at"])

    async def injector(self) -> None:
        blink, tick = Blinker(), 1 / 60
        nxt = time.monotonic()
        while True:
            nxt += tick
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))
            if time.monotonic() - nxt > 0.5:
                nxt = time.monotonic()       # the computer was busy: do not send a burst to catch up
            pos, s = self.position(), self.store.settings
            want_dance = pos is not None and s["dance"]
            if want_dance != self.dancing:
                self.dancing = want_dance
                asyncio.create_task(self.dance(want_dance))
            if pos is None or not s["lipSync"] or not self.link.ready:
                continue
            sid = self.clock["song"]
            if self.track[0] != sid:
                self.track = (sid, self.store.mouth(sid) if sid else None)
            if not self.track[1]:
                continue
            m = mouth.sample(self.track[1], pos + s["mouthLeadMs"] / 1000)
            await self.link.inject(face_values(m, s["mouthStrength"], blink.value(time.monotonic()) if s["blink"] else 0.05))

    async def dance(self, on: bool) -> None:
        """Start / stop VTube Pro's looping dance through its own command door (the one Stream Deck keys use)."""
        body = {"command": "emote", "args": {"name": self.store.settings["danceEmote"], "loop": True} if on else {"stop": True}}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as http:
                async with http.post(f"http://127.0.0.1:{self.store.settings['vtpPort']}/api/command", json=body) as r:
                    note = "" if r.status == 200 else f"VTube Pro answered {r.status} to the dance command."
        except (aiohttp.ClientError, OSError, TimeoutError):
            note = "The dance could not be started: VTube Pro's helper is not answering on this computer."
        if note != self.dance_note:
            self.dance_note = note
            self.changed()

    async def live_watch(self) -> None:
        """Ask VTube Pro now and then whether you are live, so the page can warn before a heavy job."""
        while True:
            live = None
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as http:
                    async with http.get(f"http://127.0.0.1:{self.store.settings['vtpPort']}/api/gpu/status") as r:
                        if r.status == 200:
                            v = (await r.json()).get("live")
                            live = v if isinstance(v, bool) else None
            except (aiohttp.ClientError, OSError, TimeoutError, ValueError):
                pass
            if live != self.live:
                self.live = live
                self.changed()
            await asyncio.sleep(20)


def match_loudness(reference: Path, converted: Path, out: Path) -> None:
    ref, _ = wavio.read_wav(reference)
    x, sr = wavio.read_wav(converted)
    a, b = float(np.sqrt(np.mean(ref ** 2)) + 1e-9), float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    gain = min(a / b, 0.98 / (float(np.abs(x).max()) + 1e-9))
    wavio.write_wav(out, x * gain, sr)


# ---------------------------------------------------------------- web routes
def make_app(store: Store | None = None) -> web.Application:
    k = Karaoke(store or Store())
    app = web.Application(middlewares=[local_only], client_max_size=MAX_UPLOAD)
    app[KEY] = k
    r = app.router

    async def index(_):
        return web.FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})

    async def state(_):
        return web.json_response(k.state())

    async def settings(req):
        patch = await req.json()
        k.store.update_settings(patch)
        if "vtsPort" in patch:
            k.link.retry()
        k.changed()
        return web.json_response(k.store.settings)

    async def add_song(req):
        """A song (any audio file) or its two ready-made tracks (WAV). Files are copied into the library on this PC."""
        reader, fields, meta = await req.multipart(), {}, None
        try:
            async for part in reader:
                if part.filename:
                    if part.name == "song":
                        meta = k.store.add_song(fields.get("title", ""), part.filename)
                        target = k.store.song_dir(meta["id"]) / meta["source"]
                    elif part.name in ("vocals", "instrumental") and meta:
                        target = k.store.song_dir(meta["id"]) / (part.name + ".wav")
                    else:
                        continue
                    with open(target, "wb") as f:
                        while chunk := await part.read_chunk(1 << 20):
                            f.write(chunk)
                    if part.name != "song":
                        wavio.read_wav(target)      # must be a plain WAV (raises a clear message otherwise)
                else:
                    fields[part.name] = (await part.text())[:200]
            if not meta:
                raise ValueError("No song file was chosen.")
        except (ValueError, wavio.WavError) as e:
            if meta:
                k.store.delete_song(meta["id"])
            return web.json_response({"error": str(e)}, status=400)
        k.process_song(meta["id"], fields.get("mode", "none"), fields.get("voice", ""), _pitch(fields.get("pitch")))
        return web.json_response(meta)

    async def process(req):
        b = await req.json()
        try:
            job = k.process_song(req.match_info["id"], b.get("vocals", "none"), str(b.get("voice", "")), _pitch(b.get("pitch")))
        except KeyError:
            raise web.HTTPNotFound()
        return web.json_response(job)

    async def delete_song(req):
        try:
            k.store.delete_song(req.match_info["id"])
        except KeyError:
            raise web.HTTPNotFound()
        k.changed()
        return web.json_response({"ok": True})

    async def media(req):
        name = req.match_info["name"]
        try:
            d = k.store.song_dir(req.match_info["id"])
        except KeyError:
            raise web.HTTPNotFound()
        if not (name in ("instrumental.wav", "vocals.wav") or (name.startswith("voice-") and name.endswith(".wav") and "/" not in name and "\\" not in name)):
            raise web.HTTPNotFound()
        if not (d / name).exists():
            raise web.HTTPNotFound()
        return web.FileResponse(d / name)

    async def engine(req):
        name, action = req.match_info["name"], req.match_info["action"]
        if name not in ENGINES:
            raise web.HTTPNotFound()
        if action == "install":
            return web.json_response(k.install_engine(name))
        k.engines.remove(name)
        k.changed()
        return web.json_response({"ok": True})

    async def connect(_):
        k.link.retry()
        return web.json_response({"ok": True})

    async def page_socket(req):
        ws = web.WebSocketResponse(heartbeat=15)
        await ws.prepare(req)
        k.pages.add(ws)
        await ws.send_str(json.dumps({"t": "state", "state": k.state()}))
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                m = json.loads(msg.data)
                if m.get("t") == "clock":
                    k.clock = {"song": str(m.get("song", ""))[:32], "pos": float(m.get("pos", 0)), "playing": bool(m.get("playing")), "at": time.monotonic()}
        finally:
            k.pages.discard(ws)
            if not k.pages:
                k.clock["playing"] = False      # the page was closed: stop the mouth and the dance
        return ws

    r.add_get("/", index)
    r.add_get("/api/state", state)
    r.add_post("/api/settings", settings)
    r.add_post("/api/songs", add_song)
    r.add_post("/api/songs/{id}/process", process)
    r.add_delete("/api/songs/{id}", delete_song)
    r.add_get("/media/{id}/{name}", media)
    r.add_post("/api/engines/{name}/{action:install|remove}", engine)
    r.add_post("/api/connect", connect)
    r.add_get("/ws", page_socket)

    async def background(app):
        tasks = [asyncio.create_task(c) for c in (k.link.run(), k.injector(), k.worker(), k.pusher(), k.live_watch())]
        yield
        if k.dancing:
            await k.dance(False)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    app.cleanup_ctx.append(background)
    return app


KEY = web.AppKey("karaoke", Karaoke)


def _pitch(v) -> int:
    try:
        return max(-24, min(24, int(v)))
    except (TypeError, ValueError):
        return 0
