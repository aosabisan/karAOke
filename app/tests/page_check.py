"""Developer check of the real page in a MUTED headless Chrome (no sound is ever played):
    python -m tests.page_check --karaoke 5290 --helper 5391
Adds a synthetic song through the page's own form, presses Load and Play, and checks that the page's clock runs,
that the mouth reaches the helper's bus, and that Pause hands the mouth back."""
import argparse
import asyncio
import json
import subprocess
import tempfile
import time

import aiohttp
import numpy as np

from karaoke import wavio
from tests import synth


async def main(karaoke: int, helper: int) -> int:
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS  " if cond else "FAIL  ") + name + (f"  [{extra}]" if extra else ""))

    tmp = tempfile.mkdtemp()
    vocals = np.concatenate([synth.silence(1), synth.vowel("a", 3), synth.silence(1)])
    for name, x in (("song", vocals), ("inst", synth.vowel("u", 5, f0=110) * 0.2), ("voc", vocals)):
        wavio.write_wav(f"{tmp}/{name}.wav", x, 44100)
    chrome = subprocess.Popen(["google-chrome", "--headless=new", "--no-sandbox", "--mute-audio", "--disable-gpu", "--autoplay-policy=no-user-gesture-required",
                               "--remote-debugging-port=9333", f"--user-data-dir={tmp}/chrome", f"http://127.0.0.1:{karaoke}/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with aiohttp.ClientSession() as http:
            for _ in range(50):
                try:
                    tabs = await (await http.get("http://127.0.0.1:9333/json")).json()
                    break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.2)
            cdp = await http.ws_connect(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"], max_msg_size=0)
            n, errors = 0, []

            async def call(method, **params):
                nonlocal n
                n += 1
                await cdp.send_str(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    m = json.loads((await cdp.receive()).data)
                    if m.get("method") == "Runtime.exceptionThrown":
                        errors.append(m["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:200])
                    if m.get("id") == n:
                        return m.get("result", {})

            async def js(expr):
                r = await call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
                return r.get("result", {}).get("value")
            await call("Runtime.enable")
            await call("DOM.enable")
            await asyncio.sleep(1)
            # let the plugin in on the private helper (the Allow press)
            for _ in range(40):
                pend = await (await http.get(f"http://127.0.0.1:{helper}/api/external/vts/pending")).json()
                pend = pend.get("pending", pend) if isinstance(pend, dict) else pend
                if pend:
                    await http.post(f"http://127.0.0.1:{helper}/api/external/vts/approve", json={"id": pend[0]["id"], "allow": True})
                    break
                if await js("S && S.link.state") == "ready":
                    break
                await asyncio.sleep(0.25)
            doc = (await call("DOM.getDocument"))["root"]["nodeId"]
            for sel, f in (("#songFile", "song"), ("#instFile", "inst"), ("#vocFile", "voc")):
                node = (await call("DOM.querySelector", nodeId=doc, selector=sel))["nodeId"]
                await call("DOM.setFileInputFiles", nodeId=node, files=[f"{tmp}/{f}.wav"])
            await js("document.getElementById('add').click()")
            for _ in range(60):
                if await js("S.songs.some(m => m.title === 'song' && m.state === 'ready' && m.has.mouth)"):
                    break
                await asyncio.sleep(0.2)
            check("song added through the page's form and made ready", await js("S.songs.some(m => m.title === 'song' && m.state === 'ready' && m.has.mouth)"), await js("document.getElementById('addMsg').textContent"))
            check("plugin connected", await js("S.link.state") == "ready", await js("S.link.state"))

            bus = await http.ws_connect(f"ws://127.0.0.1:{helper}/ws")
            ext = []

            async def listen():
                async for msg in bus:
                    if msg.type == aiohttp.WSMsgType.TEXT and '"type":"ext"' in msg.data:
                        ext.append((time.monotonic(), json.loads(msg.data)["data"]))
            task = asyncio.create_task(listen())

            await js("document.querySelector('[data-load]').click()")
            await asyncio.sleep(0.6)
            check("vocals menu offers the original singer", await js("[...document.getElementById('vocalSrc').options].map(o => o.value).join()") == "none,original")
            await js("document.getElementById('vocalSrc').value = 'original'; document.getElementById('play').click()")
            await asyncio.sleep(3.0)
            pos = await js("position()")
            check("the page's clock runs while playing", pos and 2.2 < pos < 3.3, f"{pos:.2f} s after 3.0 s" if pos else str(pos))
            check("music and vocal tracks both started", await js("P.nodes.length") == 2 and await js("P.ctx.state") == "running")
            jaw = [d.get("blendshapes", {}).get("jawOpen", 0) for t, d in ext[-40:]]
            check("the mouth reaches VTube Pro while the vocal sings", len(ext) > 100 and min(jaw) > 0.5, f"{len(ext)} messages, jaw {min(jaw or [0]):.2f}")
            await js("document.getElementById('play').click()")     # Pause
            await asyncio.sleep(0.4)
            n_ext = len(ext)
            await asyncio.sleep(0.6)
            check("Pause hands the mouth back", len(ext) == n_ext and await js("P.playing") is False)
            await js("document.getElementById('lip').click()")
            await js("document.getElementById('play').click()")     # Play with the mouth switch off
            await asyncio.sleep(0.8)
            check("mouth switch off: music plays, nothing is sent", len(ext) == n_ext and await js("P.playing") is True and await js("S.settings.lipSync") is False)
            await js("document.getElementById('stop').click(); document.getElementById('lip').click()")
            check("no page errors", not errors, "; ".join(errors))
            task.cancel()
            await bus.close()
            await cdp.close()
    finally:
        chrome.terminate()
    print("page_check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--karaoke", type=int, default=5290)
    ap.add_argument("--helper", type=int, required=True)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.karaoke, a.helper)))
