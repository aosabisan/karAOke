"""The whole program, silently: a pretend VTube Pro (plugin port + command door), the real server, a pretend page.
Nothing is played: the "page" here only reports a clock, exactly as the real page does while it plays."""
import asyncio
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

import aiohttp
import numpy as np
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from karaoke import wavio
from karaoke.server import KEY, make_app
from karaoke.store import Store
from tests import synth


class FakeVTubePro:
    """Speaks just enough of the plugin protocol: key on Allow, login with the key, counts injected face values."""

    def __init__(self, allow=True):
        self.allow, self.token, self.injects, self.commands, self.asked = allow, "key-123", [], [], 0

    async def plugin(self, req):
        ws = web.WebSocketResponse()
        await ws.prepare(req)
        async for msg in ws:
            m = json.loads(msg.data)
            kind, d = m["messageType"], m.get("data", {})
            assert m["apiName"] == "VTubeStudioPublicAPI"
            if kind == "AuthenticationTokenRequest":
                self.asked += 1
                assert d["pluginName"] == "Aosabi Karaoke" and d["pluginDeveloper"] == "aosabi"
                out = ("AuthenticationTokenResponse", {"authenticationToken": self.token}) if self.allow else ("APIError", {"errorID": 50, "message": "denied"})
            elif kind == "AuthenticationRequest":
                out = ("AuthenticationResponse", {"authenticated": d.get("authenticationToken") == self.token})
            elif kind == "InjectParameterDataRequest":
                self.injects.append((time.monotonic(), {p["id"]: p["value"] for p in d["parameterValues"]}))
                out = ("InjectParameterDataResponse", {})
            else:
                out = ("APIError", {"errorID": 7, "message": "not supported"})
            await ws.send_str(json.dumps({"apiName": m["apiName"], "apiVersion": "1.0", "requestID": m["requestID"], "messageType": out[0], "data": out[1]}))
        return ws

    async def command(self, req):
        self.commands.append(await req.json())
        return web.json_response({"ok": True})

    async def start(self):
        app = web.Application()
        app.router.add_get("/", self.plugin)
        app.router.add_post("/api/command", self.command)
        async def gpu(_):
            return web.json_response({"live": False})
        app.router.add_get("/api/gpu/status", gpu)
        self.server = TestServer(app)
        await self.server.start_server()
        return self.server.port


def wav_bytes(x, sr=44100):
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        wavio.write_wav(f.name, x, sr)
        return Path(f.name).read_bytes()


class EndToEnd(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vtp = FakeVTubePro()
        port = await self.vtp.start()
        self.store = Store(Path(self.tmp.name))
        self.store.update_settings({"vtsPort": port, "vtpPort": port})
        self.client = TestClient(TestServer(make_app(self.store)))
        await self.client.start_server()
        self.k = self.client.app[KEY]

    async def asyncTearDown(self):
        await self.client.close()
        await self.vtp.server.close()
        self.tmp.cleanup()

    async def wait(self, cond, seconds=8.0, what=""):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if cond():
                return
            await asyncio.sleep(0.03)
        self.fail("timed out waiting for " + what)

    async def add_song(self):
        # 0-1 s silence, 1-3 s "aa", 3-4 s silence
        vocals = np.concatenate([synth.silence(1), synth.vowel("a", 2), synth.silence(1)])
        music = synth.vowel("u", 4, f0=110) * 0.3
        fd = aiohttp.FormData()
        fd.add_field("title", "Test: song")
        fd.add_field("mode", "none")
        fd.add_field("song", io.BytesIO(wav_bytes(vocals + music)), filename="test song.wav")
        fd.add_field("instrumental", io.BytesIO(wav_bytes(music)), filename="i.wav")
        fd.add_field("vocals", io.BytesIO(wav_bytes(vocals)), filename="v.wav")
        r = await self.client.post("/api/songs", data=fd)
        self.assertEqual(r.status, 200, await r.text())
        sid = (await r.json())["id"]
        await self.wait(lambda: self.store.song(sid)["state"] == "ready", what="the song to be ready")
        return sid

    async def test_song_plays_mouth_dances_and_stops(self):
        sid = await self.add_song()
        song = self.store.song(sid)
        self.assertEqual(song["title"], "Test song")
        self.assertTrue(song["has"]["mouth"] and song["has"]["instrumental"] and song["has"]["vocals"])
        r = await self.client.get(f"/media/{sid}/instrumental.wav")
        self.assertEqual(r.status, 200)
        self.assertEqual((await self.client.get(f"/media/{sid}/song.json")).status, 404)
        self.assertEqual((await self.client.get("/media/../../etc/passwd")).status, 404)

        await self.wait(lambda: self.k.link.ready, what="the plugin link")
        self.assertEqual(self.vtp.asked, 1)
        self.assertEqual(self.store.token(), "key-123")

        ws = await self.client.ws_connect("/ws")
        self.assertEqual(json.loads((await ws.receive()).data)["t"], "state")
        self.assertEqual(self.vtp.injects, [])                       # nothing is sent while nothing plays

        await ws.send_str(json.dumps({"t": "clock", "song": sid, "pos": 0.0, "playing": True}))
        t0 = time.monotonic()
        for _ in range(12):                                          # the page reports its clock 5 times a second
            await asyncio.sleep(0.2)
            await ws.send_str(json.dumps({"t": "clock", "song": sid, "pos": time.monotonic() - t0, "playing": True}))
        got = [(t - t0, v) for t, v in self.vtp.injects]
        self.assertGreater(len(got), 100)                            # about 60 a second
        self.assertLess(len(got), 200)
        quiet = [v["jawOpen"] for t, v in got if 0.2 < t < 0.8]
        sung = [v["jawOpen"] for t, v in got if 1.3 < t < 2.3]
        self.assertLess(max(quiet), 0.05)
        self.assertGreater(min(sung), 0.6)
        self.assertTrue(all("eyeBlinkLeft" in v and "mouthFunnel" in v for _, v in got))
        self.assertEqual(self.vtp.commands[0], {"command": "emote", "args": {"name": "dance", "loop": True}})

        await ws.send_str(json.dumps({"t": "clock", "song": sid, "pos": 2.4, "playing": False}))   # Pause
        await asyncio.sleep(0.15)
        n = len(self.vtp.injects)
        await asyncio.sleep(0.4)
        self.assertEqual(len(self.vtp.injects), n)                   # the mouth is handed back to VTube Pro
        self.assertEqual(self.vtp.commands[-1], {"command": "emote", "args": {"stop": True}})
        await ws.close()

    async def test_mouth_switch_off_and_page_closing(self):
        sid = await self.add_song()
        await self.wait(lambda: self.k.link.ready, what="the plugin link")
        r = await self.client.post("/api/settings", json={"lipSync": False, "dance": False})
        self.assertFalse((await r.json())["lipSync"])
        ws = await self.client.ws_connect("/ws")
        await ws.receive()
        await ws.send_str(json.dumps({"t": "clock", "song": sid, "pos": 1.5, "playing": True}))
        await asyncio.sleep(0.4)
        self.assertEqual(self.vtp.injects, [])                       # switch off = nothing sent
        self.assertEqual(self.vtp.commands, [])
        await self.client.post("/api/settings", json={"lipSync": True})
        await self.wait(lambda: len(self.vtp.injects) > 5, what="the mouth after switching it back on")
        await ws.close()                                             # the page is closed while "playing"
        await asyncio.sleep(0.3)
        n = len(self.vtp.injects)
        await asyncio.sleep(0.4)
        self.assertEqual(len(self.vtp.injects), n)

    async def test_refuses_other_sites_and_bad_files(self):
        r = await self.client.post("/api/settings", json={"dance": False}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status, 403)
        r = await self.client.get("/api/state", headers={"Host": "evil.example:5290"})
        self.assertEqual(r.status, 421)
        fd = aiohttp.FormData()
        fd.add_field("song", io.BytesIO(b"hello"), filename="notes.txt")
        r = await self.client.post("/api/songs", data=fd)
        self.assertEqual(r.status, 400)
        self.assertIn("not an audio file", (await r.json())["error"])
        self.assertEqual(self.store.songs(), [])

    async def test_song_without_a_splitter_explains_what_to_do(self):
        fd = aiohttp.FormData()
        fd.add_field("song", io.BytesIO(wav_bytes(synth.vowel("a", 0.5))), filename="solo.wav")
        r = await self.client.post("/api/songs", data=fd)
        sid = (await r.json())["id"]
        await self.wait(lambda: self.store.song(sid)["state"] == "error", what="the job to stop")
        self.assertIn("splitter is not installed", self.store.song(sid)["note"])


class Denied(unittest.IsolatedAsyncioTestCase):
    async def test_denied_plugin_does_not_nag(self):
        vtp = FakeVTubePro(allow=False)
        port = await vtp.start()
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            store.update_settings({"vtsPort": port, "vtpPort": port})
            client = TestClient(TestServer(make_app(store)))
            await client.start_server()
            k = client.app[KEY]
            for _ in range(100):
                if k.link.state == "denied":
                    break
                await asyncio.sleep(0.05)
            self.assertEqual(k.link.state, "denied")
            await asyncio.sleep(0.5)
            self.assertEqual(vtp.asked, 1)                           # asked once, then waits for the Connect button
            vtp.allow = True
            await client.post("/api/connect")
            for _ in range(100):
                if k.link.ready:
                    break
                await asyncio.sleep(0.05)
            self.assertTrue(k.link.ready)
            await client.close()
        await vtp.server.close()


if __name__ == "__main__":
    unittest.main()
