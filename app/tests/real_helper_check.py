"""Developer check against a REAL VTube Pro helper running on a private test port (never the live one):
    python -m tests.real_helper_check --helper 5391 --plugin-port 8101
It switches that helper's plugin port on, lets the plugin in (the Allow press, done through the helper's own
approve call), "plays" a synthetic song by reporting a clock (no sound), and prints what the helper put on its bus.
"""
import argparse
import asyncio
import io
import json
import tempfile
import time
from pathlib import Path

import aiohttp
import numpy as np
from aiohttp.test_utils import TestClient, TestServer

from karaoke.server import KEY, make_app
from karaoke.store import Store
from tests import synth
from tests.test_end_to_end import wav_bytes


async def main(helper: int, plugin_port: int) -> int:
    base = f"http://127.0.0.1:{helper}"
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS  " if cond else "FAIL  ") + name + (f"  [{extra}]" if extra else ""))

    async with aiohttp.ClientSession() as http:
        r = await http.put(base + "/api/external", json={"vtsApi": {"enabled": True, "port": plugin_port}})
        check("helper switches its plugin port on", r.status == 200, str(r.status))
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d))
            store.update_settings({"vtsPort": plugin_port, "vtpPort": helper})
            client = TestClient(TestServer(make_app(store)))
            await client.start_server()
            k = client.app[KEY]

            pending = []
            for _ in range(80):
                pending = await (await http.get(base + "/api/external/vts/pending")).json()
                pending = pending.get("pending", pending) if isinstance(pending, dict) else pending
                if pending:
                    break
                await asyncio.sleep(0.1)
            check("VTube Pro shows the plugin waiting for Allow", pending and pending[0]["pluginName"] == "Aosabi Karaoke" and pending[0]["pluginDeveloper"] == "aosabi",
                  json.dumps(pending)[:160])
            check("the page says: press Allow", k.link.state == "waiting", k.link.state)
            r = await http.post(base + "/api/external/vts/approve", json={"id": pending[0]["id"], "allow": True})
            check("Allow accepted", r.status == 200, str(r.status))
            for _ in range(80):
                if k.link.ready:
                    break
                await asyncio.sleep(0.1)
            check("plugin is logged in", k.link.ready, k.link.detail)

            bus_ext, bus_cmd = [], []
            bus = await http.ws_connect(f"ws://127.0.0.1:{helper}/ws")

            async def listen():
                async for msg in bus:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        m = json.loads(msg.data)
                        if m.get("type") == "ext":
                            bus_ext.append((time.monotonic(), m["data"]))
                        elif m.get("type") == "command":
                            bus_cmd.append(m)
            task = asyncio.create_task(listen())

            vocals = np.concatenate([synth.silence(1), synth.vowel("a", 1), synth.vowel("i", 1), synth.vowel("u", 1), synth.silence(1)])
            fd = aiohttp.FormData()
            fd.add_field("mode", "none")
            fd.add_field("song", io.BytesIO(wav_bytes(vocals)), filename="check.wav")
            fd.add_field("instrumental", io.BytesIO(wav_bytes(vocals * 0)), filename="i.wav")
            fd.add_field("vocals", io.BytesIO(wav_bytes(vocals)), filename="v.wav")
            sid = (await (await client.post("/api/songs", data=fd)).json())["id"]
            for _ in range(100):
                if store.song(sid)["state"] == "ready":
                    break
                await asyncio.sleep(0.05)

            page = await client.ws_connect("/ws")
            await page.receive()
            t0 = time.monotonic()
            while time.monotonic() - t0 < 4.6:
                await page.send_str(json.dumps({"t": "clock", "song": sid, "pos": time.monotonic() - t0, "playing": True}))
                await asyncio.sleep(0.2)
            await page.send_str(json.dumps({"t": "clock", "song": sid, "pos": 4.6, "playing": False}))
            await asyncio.sleep(0.5)
            n_after_stop = len(bus_ext)
            await asyncio.sleep(0.7)

            got = [(t - t0, d) for t, d in bus_ext]
            check("helper publishes the plugin's face on its bus", len(got) > 150, f"{len(got)} messages in 4.6 s")
            check("marked as coming from a VTube Studio plugin", all(d.get("source") == "vts-api" and d.get("found") is True for _, d in got))

            def avg(name, a, b):
                v = [d.get("blendshapes", {}).get(name, 0) for t, d in got if a < t < b]
                return sum(v) / max(1, len(v))
            aa, ee, oo, sil = avg("jawOpen", 1.25, 1.9), avg("mouthStretchLeft", 2.25, 2.9), avg("mouthPucker", 3.25, 3.9), avg("jawOpen", 0.2, 0.8)
            check("silence: jaw closed", sil < 0.03, f"{sil:.2f}")
            check("'aa': jaw open", aa > 0.7, f"{aa:.2f}")
            check("'ee': lips wide", ee > 0.3, f"{ee:.2f}")
            check("'oo': lips round", oo > 0.3, f"{oo:.2f}")
            check("blinks are sent", any(d.get("blendshapes", {}).get("eyeBlinkLeft", 0) > 0.5 for _, d in got))
            check("head is left to the camera (not sent)", all("head" not in d and "headPos" not in d for _, d in got))
            check("stops sending after Pause", len(bus_ext) == n_after_stop, f"{len(bus_ext) - n_after_stop} late messages")
            emotes = [c for c in bus_cmd if c.get("command") == "emote"]
            check("dance started through the command door", emotes[:1] == [{"type": "command", "command": "emote", "args": {"name": "dance", "loop": True}}], json.dumps(emotes[:1]))
            check("dance stopped", emotes[-1:] == [{"type": "command", "command": "emote", "args": {"stop": True}}], json.dumps(emotes[-1:]))
            task.cancel()
            await bus.close()
            await page.close()
            await client.close()
    print("real_helper_check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--helper", type=int, required=True)
    ap.add_argument("--plugin-port", type=int, default=8101)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.helper, a.plugin_port)))
