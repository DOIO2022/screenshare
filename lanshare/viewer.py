import asyncio
import json
import queue
import struct
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import numpy as np
import websockets
from PIL import Image, ImageTk


class RemoteViewer:
    BAR_H = 40
    MM_RATE = 1 / 25

    def __init__(self, root: tk.Tk):
        self.root = root
        self.frame_q: queue.Queue = queue.Queue(maxsize=1)
        self.screen_w = 1920
        self.screen_h = 1080
        self.connected = False
        self.fullscreen = False
        self._photo = None
        self._loop = None
        self._ws_thread = None
        self._send_q: asyncio.Queue | None = None
        self._last_mm = 0.0
        self._host_label = ""

        self._build_ui()

    def _build_ui(self):
        bar = tk.Frame(self.root, bg="#1e293b", height=self.BAR_H)
        bar.pack(side=tk.TOP, fill=tk.X)
        bar.pack_propagate(False)

        tk.Label(bar, text="LanShare 观看", fg="white", bg="#1e293b", font=("Segoe UI", 11, "bold")).pack(
            side=tk.LEFT, padx=12
        )
        self.status_lbl = tk.Label(bar, text="● 未连接", fg="#f87171", bg="#1e293b", font=("Segoe UI", 10))
        self.status_lbl.pack(side=tk.LEFT, padx=8)

        btn = dict(
            fg="white",
            bg="#334155",
            activebackground="#475569",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 10),
            padx=10,
            pady=4,
            cursor="hand2",
        )
        tk.Button(bar, text="断开", command=self.disconnect, **btn).pack(side=tk.RIGHT, padx=8)
        tk.Button(bar, text="全屏 F11", command=self.toggle_fullscreen, **btn).pack(side=tk.RIGHT, padx=4)

        self.canvas = tk.Canvas(self.root, bg="#0f172a", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<ButtonPress-1>", lambda e: self._on_click(e, "l", True))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._on_click(e, "l", False))
        self.canvas.bind("<ButtonPress-3>", lambda e: self._on_click(e, "r", True))
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._on_click(e, "r", False))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set(), add="+")
        self.canvas.bind("<Button-3>", lambda e: self.canvas.focus_set(), add="+")
        self.root.bind("<KeyPress>", self._on_key_down)
        self.root.bind("<KeyRelease>", self._on_key_up)
        self.root.bind("<F11>", lambda _e: self.toggle_fullscreen())

    def connect(self, host: str, port: int, password: str = ""):
        if self.connected:
            self.disconnect()
        self._host_label = f"{host}:{port}"
        self._ws_thread = threading.Thread(
            target=self._ws_main, args=(host, port, password), daemon=True, name="share-viewer-ws"
        )
        self._ws_thread.start()

    def disconnect(self):
        self.connected = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.status_lbl.config(text="● 未连接", fg="#f87171")
        self.canvas.delete("all")

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def _norm_pos(self, event):
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        scale = min(cw / self.screen_w, ch / self.screen_h)
        dw = self.screen_w * scale
        dh = self.screen_h * scale
        ox = (cw - dw) / 2
        oy = (ch - dh) / 2
        x = (event.x - ox) / dw
        y = (event.y - oy) / dh
        if 0 <= x <= 1 and 0 <= y <= 1:
            return x, y
        return None

    def _send(self, msg: dict):
        if not self.connected or not self._send_q or not self._loop:
            return
        asyncio.run_coroutine_threadsafe(self._send_q.put(msg), self._loop)

    def _on_motion(self, event):
        now = time.monotonic()
        if now - self._last_mm < self.MM_RATE:
            return
        pos = self._norm_pos(event)
        if pos is None:
            return
        self._last_mm = now
        x, y = pos
        self._send({"t": "mm", "x": x, "y": y})

    def _on_click(self, event, button: str, down: bool):
        pos = self._norm_pos(event)
        if pos is None:
            return
        x, y = pos
        self._send({"t": "mc", "x": x, "y": y, "b": button, "d": down})

    def _on_wheel(self, event):
        pos = self._norm_pos(event)
        if pos is None:
            return
        x, y = pos
        dy = int(-event.delta / 120)
        self._send({"t": "ms", "x": x, "y": y, "dy": dy})

    def _key_name(self, event) -> str | None:
        keysym = event.keysym.lower()
        if keysym in ("return", "enter"):
            return "enter"
        if len(keysym) == 1:
            return keysym
        if keysym.startswith("f") and keysym[1:].isdigit():
            return keysym
        mapping = {
            "backspace": "backspace",
            "tab": "tab",
            "space": "space",
            "escape": "escape",
            "delete": "delete",
            "control_l": "ctrl",
            "control_r": "ctrl",
            "alt_l": "alt",
            "shift_l": "shift",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
        }
        return mapping.get(keysym)

    def _on_key_down(self, event):
        if not self.connected:
            return
        k = self._key_name(event)
        if k:
            self._send({"t": "kp", "k": k})

    def _on_key_up(self, event):
        if not self.connected:
            return
        k = self._key_name(event)
        if k:
            self._send({"t": "kr", "k": k})

    def _push_frame(self, jpg: bytes):
        try:
            self.frame_q.get_nowait()
        except queue.Empty:
            pass
        try:
            self.frame_q.put_nowait(jpg)
        except queue.Full:
            pass

    def _poll_frame(self):
        try:
            jpg = self.frame_q.get_nowait()
            img = Image.open(__import__("io").BytesIO(jpg))
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())
            scale = min(cw / self.screen_w, ch / self.screen_h)
            dw = int(self.screen_w * scale)
            dh = int(self.screen_h * scale)
            img = img.resize((dw, dh), Image.Resampling.BILINEAR)
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image((cw - dw) // 2, (ch - dh) // 2, anchor=tk.NW, image=self._photo)
        except queue.Empty:
            pass
        except Exception:
            pass
        self.root.after(33, self._poll_frame)

    def _redraw(self):
        if self._photo:
            self._poll_frame()

    async def _session(self, host: str, port: int, password: str):
        uri = f"ws://{host}:{port}"
        async with websockets.connect(uri, max_size=None, compression=None) as ws:
            if password:
                await ws.send(json.dumps({"t": "auth", "pin": password}))
                reply = json.loads(await ws.recv())
                if reply.get("t") != "auth_ok":
                    raise RuntimeError("密码错误")

            self.connected = True

            def _on_connected():
                self.status_lbl.config(text=f"● 已连接 {self._host_label}", fg="#4ade80")
                self.canvas.focus_set()

            self.root.after(0, _on_connected)

            async def sender():
                while self.connected:
                    msg = await self._send_q.get()
                    await ws.send(json.dumps(msg))

            send_task = asyncio.create_task(sender())
            try:
                async for raw in ws:
                    if isinstance(raw, bytes) and raw[:1] == b"F" and len(raw) >= 9:
                        sw, sh, jlen = struct.unpack("!HHI", raw[1:9])
                        jpg = raw[9 : 9 + jlen]
                        self.screen_w, self.screen_h = sw, sh
                        self._push_frame(jpg)
            finally:
                send_task.cancel()
                self.connected = False
                self.root.after(0, lambda: self.status_lbl.config(text="● 未连接", fg="#f87171"))

    def _ws_main(self, host: str, port: int, password: str):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_q = asyncio.Queue()
        try:
            self._loop.run_until_complete(self._session(host, port, password))
        except Exception as exc:
            self.connected = False
            self.root.after(0, lambda: messagebox.showerror("连接失败", str(exc)))
            self.root.after(0, lambda: self.status_lbl.config(text="● 未连接", fg="#f87171"))
        finally:
            self._loop.close()

    def start_polling(self):
        self._poll_frame()
