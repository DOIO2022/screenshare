import asyncio
import json
import socket
import struct
import threading
import time
from typing import Optional

import cv2
import mss
import numpy as np
import websockets
from pynput.keyboard import Controller as KbCtrl, Key, KeyCode
from pynput.mouse import Button, Controller as MouseCtrl

from .config import DEFAULT_PORT, FPS_MAX, FPS_MIN, JPEG_QUALITY, STREAM_WIDTH
from .discovery import start_announcer
from .netutil import local_ip

_mouse = MouseCtrl()
_keyboard = KbCtrl()

_SPECIAL = {
    "enter": Key.enter,
    "backspace": Key.backspace,
    "tab": Key.tab,
    "space": Key.space,
    "escape": Key.esc,
    "delete": Key.delete,
    "ctrl": Key.ctrl_l,
    "alt": Key.alt_l,
    "shift": Key.shift_l,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)},
}


def _resolve_key(k: str):
    if k in _SPECIAL:
        return _SPECIAL[k]
    if len(k) == 1:
        return KeyCode.from_char(k)
    return None


def _screen_size():
    with mss.mss() as sct:
        mon = sct.monitors[1]
        return mon["width"], mon["height"]


def _handle_input(cmd: dict, sw: int, sh: int, allow_control: bool):
    if not allow_control:
        return
    t = cmd.get("t")
    if t == "mm":
        _mouse.position = (int(cmd["x"] * sw), int(cmd["y"] * sh))
    elif t == "mc":
        _mouse.position = (int(cmd["x"] * sw), int(cmd["y"] * sh))
        btn = Button.left if cmd.get("b") == "l" else Button.right
        (_mouse.press if cmd.get("d") else _mouse.release)(btn)
    elif t == "ms":
        _mouse.position = (int(cmd["x"] * sw), int(cmd["y"] * sh))
        _mouse.scroll(0, int(cmd.get("dy", 0)))
    elif t == "kp":
        key = _resolve_key(cmd.get("k", ""))
        if key:
            try:
                _keyboard.press(key)
            except Exception:
                pass
    elif t == "kr":
        key = _resolve_key(cmd.get("k", ""))
        if key:
            try:
                _keyboard.release(key)
            except Exception:
                pass


async def _capture_loop(ws, stop: asyncio.Event, sw: int, sh: int):
    dw = min(STREAM_WIDTH, sw)
    dh = int(sh * dw / sw)
    enc = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    frame_q: asyncio.Queue = asyncio.Queue(maxsize=1)
    interval = 1.0 / FPS_MAX

    async def capture():
        nonlocal interval
        with mss.mss() as sct:
            mon = sct.monitors[1]
            region = {"left": mon["left"], "top": mon["top"], "width": sw, "height": sh}
            while not stop.is_set():
                t0 = time.perf_counter()
                try:
                    shot = sct.grab(region)
                    frame = np.frombuffer(shot.raw, dtype=np.uint8).reshape((shot.height, shot.width, 4))[:, :, :3]
                    if frame.shape[1] != dw:
                        frame = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_LINEAR)
                    ok, buf = cv2.imencode(".jpg", frame, enc)
                    if not ok:
                        await asyncio.sleep(0.05)
                        continue
                    jpg = buf.tobytes()
                    payload = b"F" + struct.pack("!HHI", sw, sh, len(jpg)) + jpg
                    was_full = frame_q.full()
                    try:
                        frame_q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    frame_q.put_nowait(payload)
                    if was_full:
                        interval = min(1.0 / FPS_MIN, interval * 1.1)
                    else:
                        interval = max(1.0 / FPS_MAX, interval * 0.95)
                except Exception:
                    break
                dt = time.perf_counter() - t0
                await asyncio.sleep(max(0, interval - dt))

    async def send_frames():
        while not stop.is_set():
            try:
                payload = await asyncio.wait_for(frame_q.get(), timeout=1.0)
                await ws.send(payload)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    await asyncio.gather(capture(), send_frames())


async def _client_handler(ws, password: str, allow_control: bool, on_client_change):
    if password:
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=15.0)
            msg = json.loads(first)
            if msg.get("t") != "auth" or msg.get("pin") != password:
                await ws.send(json.dumps({"t": "auth_fail"}))
                await ws.close()
                return
            await ws.send(json.dumps({"t": "auth_ok"}))
        except Exception:
            await ws.close()
            return

    sw, sh = _screen_size()
    stop = asyncio.Event()
    task = asyncio.create_task(_capture_loop(ws, stop, sw, sh))
    on_client_change(1)
    try:
        async for raw in ws:
            if isinstance(raw, str):
                try:
                    cmd = json.loads(raw)
                    _handle_input(cmd, sw, sh, allow_control)
                except json.JSONDecodeError:
                    pass
    finally:
        stop.set()
        task.cancel()
        on_client_change(-1)


class ShareHost:
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_discovery = threading.Event()
        self._stop_serve: Optional[asyncio.Event] = None
        self._client_count = 0
        self._running = False
        self.port = DEFAULT_PORT
        self.password = ""
        self.allow_control = True
        self.device_name = socket.gethostname()

    @property
    def client_count(self) -> int:
        return self._client_count

    @property
    def running(self) -> bool:
        return self._running

    def _on_client_change(self, delta: int):
        self._client_count = max(0, self._client_count + delta)

    async def _serve(self):
        host_ref = self
        stop = asyncio.Event()
        self._stop_serve = stop

        async def handler(ws):
            await _client_handler(ws, host_ref.password, host_ref.allow_control, host_ref._on_client_change)

        async with websockets.serve(
            handler,
            "0.0.0.0",
            self.port,
            max_size=None,
            ping_interval=20,
            compression=None,
        ):
            await stop.wait()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    def start(self) -> tuple[bool, str]:
        if self._running:
            return False, "已在共享中"
        self._stop_discovery.clear()
        self._client_count = 0
        ip = local_ip()
        start_announcer(self.device_name, self.port, ip, self._stop_discovery)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="share-host")
        self._thread.start()
        self._running = True
        return True, f"{ip}:{self.port}"

    def stop(self):
        if not self._running:
            return
        self._stop_discovery.set()
        self._running = False
        if self._loop and self._stop_serve:
            self._loop.call_soon_threadsafe(self._stop_serve.set)
        if self._thread:
            self._thread.join(timeout=3.0)
        self._thread = None
        self._loop = None
        self._stop_serve = None
        self._client_count = 0
