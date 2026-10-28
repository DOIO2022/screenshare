import asyncio
import json
import socket
import struct
import sys
import threading
import time
from typing import Optional

import cv2
import mss
import numpy as np
import websockets

from .config import DEFAULT_PORT
from .discovery import start_announcer
from .netutil import local_ip
from .stream_profiles import StreamProfile, get_profile

_IS_WIN = sys.platform == "win32"
if _IS_WIN:
    from . import win_input as _input_backend
else:
    from pynput.keyboard import Controller as KbCtrl, Key, KeyCode
    from pynput.mouse import Button, Controller as MouseCtrl

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
    if not _IS_WIN:
        if k in _SPECIAL:
            return _SPECIAL[k]
        if len(k) == 1:
            return KeyCode.from_char(k)
    return None


def _screen_size():
    with mss.mss() as sct:
        mon = sct.monitors[1]
        return mon["left"], mon["top"], mon["width"], mon["height"]


def _parse_control_message(raw) -> dict | None:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _handle_input(cmd: dict, origin_x: int, origin_y: int, sw: int, sh: int, allow_control: bool):
    if not allow_control:
        return
    try:
        if _IS_WIN:
            _input_backend.handle(cmd, origin_x, origin_y, sw, sh)
            return
        t = cmd.get("t")
        if t == "mm":
            _mouse.position = (origin_x + int(cmd["x"] * sw), origin_y + int(cmd["y"] * sh))
        elif t == "mc":
            _mouse.position = (origin_x + int(cmd["x"] * sw), origin_y + int(cmd["y"] * sh))
            btn = Button.left if cmd.get("b") == "l" else Button.right
            (_mouse.press if cmd.get("d") else _mouse.release)(btn)
        elif t == "ms":
            _mouse.position = (origin_x + int(cmd["x"] * sw), origin_y + int(cmd["y"] * sh))
            _mouse.scroll(0, int(cmd.get("dy", 0)))
        elif t == "kp":
            key = _resolve_key(cmd.get("k", ""))
            if key:
                _keyboard.press(key)
        elif t == "kr":
            key = _resolve_key(cmd.get("k", ""))
            if key:
                _keyboard.release(key)
    except Exception:
        pass


def _jpeg_params(profile: StreamProfile) -> list[int]:
    params = [cv2.IMWRITE_JPEG_QUALITY, profile.jpeg_quality]
    if profile.jpeg_subsample is not None:
        params.extend([cv2.IMWRITE_JPEG_SAMPLING_FACTOR, profile.jpeg_subsample])
    return params


def _encode_shot(raw: bytes, width: int, height: int, sw: int, sh: int, profile: StreamProfile) -> bytes | None:
    frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))[:, :, :3]
    dw = sw if profile.max_width <= 0 else min(profile.max_width, sw)
    dh = int(sh * dw / sw)
    if frame.shape[1] != dw or frame.shape[0] != dh:
        frame = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, _jpeg_params(profile))
    if not ok:
        return None
    jpg = buf.tobytes()
    return b"F" + struct.pack("!HHI", sw, sh, len(jpg)) + jpg


async def _capture_loop(ws, stop: asyncio.Event, sw: int, sh: int, profile_key: str):
    profile = get_profile(profile_key)
    frame_q: asyncio.Queue = asyncio.Queue(maxsize=1)
    interval = 1.0 / profile.fps_max

    async def capture():
        nonlocal interval
        with mss.mss() as sct:
            mon = sct.monitors[1]
            region = {"left": mon["left"], "top": mon["top"], "width": sw, "height": sh}
            while not stop.is_set():
                t0 = time.perf_counter()
                try:
                    shot = sct.grab(region)
                    payload = await asyncio.to_thread(
                        _encode_shot, shot.raw, shot.width, shot.height, sw, sh, profile
                    )
                    if payload is None:
                        await asyncio.sleep(0.01)
                        continue
                    was_full = frame_q.full()
                    try:
                        frame_q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    frame_q.put_nowait(payload)
                    if was_full:
                        interval = min(1.0 / profile.fps_min, interval * 1.08)
                    else:
                        interval = max(1.0 / profile.fps_max, interval * 0.97)
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


async def _client_handler(
    ws, password: str, allow_control: bool, on_client_change, stream_profile_key: str
):
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

    ox, oy, sw, sh = _screen_size()
    stop = asyncio.Event()
    task = asyncio.create_task(_capture_loop(ws, stop, sw, sh, stream_profile_key))
    on_client_change(1)
    try:
        async for raw in ws:
            cmd = _parse_control_message(raw)
            if cmd:
                await asyncio.to_thread(_handle_input, cmd, ox, oy, sw, sh, allow_control)
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
        self.stream_profile = "balanced"

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
            await _client_handler(
                ws,
                host_ref.password,
                host_ref.allow_control,
                host_ref._on_client_change,
                host_ref.stream_profile,
            )

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
