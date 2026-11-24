"""The link to VTube Pro: a client for its "VTube Studio API (plugins)" port (ws://127.0.0.1:8001).

This is the same door every VTube Studio plugin uses, so nothing has to be changed inside VTube Pro:
  1. the plugin asks for a key, VTube Pro shows "Aosabi Karaoke by aosabi wants to control VTube Pro", you press Allow;
  2. from then on the plugin logs in with that key by itself;
  3. while a song plays it sends the mouth shapes ("InjectParameterDataRequest") about 60 times a second.
When it stops sending, VTube Pro goes back to your camera and microphone by itself within half a second.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import aiohttp

from . import PLUGIN_DEVELOPER, PLUGIN_NAME

API = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0"}


class VtsLink:
    def __init__(self, get_port, get_token, set_token):
        self._port, self._get_token, self._set_token = get_port, get_token, set_token
        self.state = "off"          # off | connecting | waiting | ready | denied
        self.detail = "Not connected yet."
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._wake = asyncio.Event()
        self.sent = 0
        self.on_change = lambda: None

    def _set(self, state: str, detail: str) -> None:
        if (state, detail) != (self.state, self.detail):
            self.state, self.detail = state, detail
            self.on_change()

    def retry(self) -> None:
        """The user pressed Connect again (after a denial, or after switching the plugin port on)."""
        self._wake.set()

    @property
    def ready(self) -> bool:
        return self.state == "ready" and self._ws is not None and not self._ws.closed

    async def _ask(self, ws, message_type: str, data: dict, timeout: float) -> tuple[str, dict]:
        rid = uuid.uuid4().hex
        await ws.send_str(json.dumps({**API, "requestID": rid, "messageType": message_type, "data": data}))
        async with asyncio.timeout(timeout):
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                m = json.loads(msg.data)
                if m.get("requestID") == rid:
                    return m.get("messageType", ""), m.get("data") or {}
        raise ConnectionError("VTube Pro closed the connection")

    async def _login(self, ws) -> bool:
        who = {"pluginName": PLUGIN_NAME, "pluginDeveloper": PLUGIN_DEVELOPER}
        token = self._get_token()
        if token:
            kind, data = await self._ask(ws, "AuthenticationRequest", {**who, "authenticationToken": token}, 10)
            if kind == "AuthenticationResponse" and data.get("authenticated"):
                return True
        self._set("waiting", "In VTube Pro, open the Track tab and press Allow next to \"Aosabi Karaoke\".")
        kind, data = await self._ask(ws, "AuthenticationTokenRequest", who, 75)
        token = data.get("authenticationToken") if kind == "AuthenticationTokenResponse" else None
        if not token:
            self._set("denied", "VTube Pro did not allow the plugin. Press Connect to ask again.")
            return False
        self._set_token(token)
        kind, data = await self._ask(ws, "AuthenticationRequest", {**who, "authenticationToken": token}, 10)
        return kind == "AuthenticationResponse" and bool(data.get("authenticated"))

    async def run(self) -> None:
        """Keeps the link up for as long as the program runs."""
        async with aiohttp.ClientSession() as http:
            while True:
                self._wake.clear()
                wait = 3.0
                try:
                    self._set("connecting", "Looking for VTube Pro...")
                    async with http.ws_connect(f"ws://127.0.0.1:{self._port()}", heartbeat=20, max_msg_size=1 << 20) as ws:
                        if await self._login(ws):
                            self._ws = ws
                            self._set("ready", "Connected to VTube Pro.")
                            async for _ in ws:      # read (and drop) the answers so nothing piles up
                                pass
                            self._set("connecting", "VTube Pro closed the connection. Trying again...")
                        elif self.state == "denied":
                            wait = 3600.0           # do not nag: wait for the Connect button
                except (aiohttp.ClientError, OSError, ConnectionError):
                    self._set("off", "VTube Pro's plugin port is not answering. In VTube Pro: Track tab, switch on "
                                     "\"VTube Studio API (plugins)\".")
                except TimeoutError:
                    self._set("denied", "Nobody pressed Allow in VTube Pro. Press Connect to ask again.")
                    wait = 3600.0
                finally:
                    self._ws = None
                try:
                    async with asyncio.timeout(wait):
                        await self._wake.wait()
                except TimeoutError:
                    pass

    async def inject(self, values: dict[str, float]) -> bool:
        """Send one set of face values. Returns False when the link is down (nothing is queued)."""
        ws = self._ws
        if not self.ready or ws is None:
            return False
        data = {"faceFound": True, "mode": "set",
                "parameterValues": [{"id": k, "value": round(float(v), 4)} for k, v in values.items()]}
        try:
            await ws.send_str(json.dumps({**API, "requestID": "inject", "messageType": "InjectParameterDataRequest", "data": data}))
            self.sent += 1
            return True
        except (ConnectionError, RuntimeError, aiohttp.ClientError):
            return False
