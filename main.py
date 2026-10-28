#!/usr/bin/env python3
"""LanShare: Windows LAN screen sharing (view + remote control)."""

import socket
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


def _ensure_runtime():
    """Packaged exe bundles everything; source run needs pip install."""
    if getattr(sys, "frozen", False):
        return
    try:
        import cv2  # noqa: F401
        import mss  # noqa: F401
        import websockets  # noqa: F401
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "LanShare",
            "当前是源码模式，需要先在本机执行：\n\n"
            "  pip install -r requirements.txt\n\n"
            "若不想装依赖：在 Windows 上运行 build.bat 生成\n"
            "LanShare-win32-x64 文件夹，双击其中的 LanShare.exe\n"
            "即可使用，其它电脑也无需安装任何东西。",
        )
        root.destroy()
        sys.exit(1)


_ensure_runtime()

from lanshare.config import DEFAULT_PORT
from lanshare.discovery import start_listener
from lanshare.host import ShareHost
from lanshare.netutil import local_ip
from lanshare import settings as app_settings
from lanshare import startup as win_startup
from lanshare.viewer import RemoteViewer


class LanShareApp:
    def __init__(self, auto_share: bool = False):
        self.root = tk.Tk()
        self.root.title("LanShare — 局域网屏幕共享")
        self.root.minsize(900, 560)
        self.root.geometry("1024x640")

        self._cfg = app_settings.load()
        self._auto_share_on_launch = auto_share or self._cfg.get("auto_share", False)

        self.host = ShareHost()
        self._discovered: dict[str, tuple[str, str, int]] = {}
        self._disc_stop = threading.Event()
        self._last_selected_key: str | None = None
        self._refresh_scheduled = False

        self._build_host_panel()
        self._build_viewer_panel()
        start_listener(self._on_discovered, self._disc_stop)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self._auto_share_on_launch:
            self.root.after(800, self._start_share)

    def _on_discovered(self, name: str, ip: str, port: int):
        key = f"{ip}:{port}"
        entry = (name, ip, port)
        if self._discovered.get(key) == entry:
            return
        self._discovered[key] = entry
        if not self._refresh_scheduled:
            self._refresh_scheduled = True
            self.root.after(0, self._refresh_hosts)

    def _refresh_hosts(self):
        self._refresh_scheduled = False
        selected = self._tree_target_key()

        for key in list(self.host_tree.get_children()):
            if key not in self._discovered:
                self.host_tree.delete(key)

        for key, (name, ip, port) in sorted(self._discovered.items(), key=lambda x: x[1][0].lower()):
            values = (name, ip, str(port))
            if self.host_tree.exists(key):
                if tuple(self.host_tree.item(key, "values")) != values:
                    self.host_tree.item(key, values=values)
            else:
                self.host_tree.insert("", tk.END, iid=key, values=values)

        if selected and self.host_tree.exists(selected):
            self.host_tree.selection_set(selected)
            self.host_tree.focus(selected)
            self._last_selected_key = selected

    def _on_tree_select(self, _event=None):
        sel = self.host_tree.selection()
        if sel:
            self._last_selected_key = sel[0]

    def _tree_target_key(self) -> str | None:
        sel = self.host_tree.selection()
        if sel:
            return sel[0]
        if self._last_selected_key and self.host_tree.exists(self._last_selected_key):
            return self._last_selected_key
        focus = self.host_tree.focus()
        if focus and self.host_tree.exists(focus):
            return focus
        return None

    def _build_host_panel(self):
        frame = ttk.LabelFrame(self.root, text="本机 — 允许他人观看/控制")
        frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=8)

        row = tk.Frame(frame)
        row.pack(fill=tk.X, padx=8, pady=6)

        name_default = self._cfg.get("device_name") or socket.gethostname()
        tk.Label(row, text="设备名:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=name_default)
        tk.Entry(row, textvariable=self.name_var, width=18).pack(side=tk.LEFT, padx=4)

        tk.Label(row, text="端口:").pack(side=tk.LEFT, padx=(12, 0))
        self.port_var = tk.StringVar(value=str(self._cfg.get("port", DEFAULT_PORT)))
        tk.Entry(row, textvariable=self.port_var, width=6).pack(side=tk.LEFT, padx=4)

        tk.Label(row, text="连接密码(可选):").pack(side=tk.LEFT, padx=(12, 0))
        self.pin_var = tk.StringVar(value=self._cfg.get("password", ""))
        tk.Entry(row, textvariable=self.pin_var, width=10, show="*").pack(side=tk.LEFT, padx=4)

        self.control_var = tk.BooleanVar(value=bool(self._cfg.get("allow_control", True)))
        ttk.Checkbutton(row, text="允许远程键鼠", variable=self.control_var).pack(side=tk.LEFT, padx=12)

        row_boot = tk.Frame(frame)
        row_boot.pack(fill=tk.X, padx=8, pady=(0, 4))

        self.boot_var = tk.BooleanVar(value=win_startup.is_enabled())
        self.auto_share_var = tk.BooleanVar(value=bool(self._cfg.get("auto_share", False)))
        boot_cb = ttk.Checkbutton(
            row_boot,
            text="开机自启（登录 Windows 后自动打开本程序）",
            variable=self.boot_var,
            command=self._on_boot_toggle,
        )
        boot_cb.pack(side=tk.LEFT)
        if not win_startup.is_supported():
            boot_cb.config(state=tk.DISABLED)

        ttk.Checkbutton(
            row_boot,
            text="启动后自动开始共享（配合开机自启，开机即可被连）",
            variable=self.auto_share_var,
            command=self._on_auto_share_toggle,
        ).pack(side=tk.LEFT, padx=(16, 0))

        row2 = tk.Frame(frame)
        row2.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.start_btn = ttk.Button(row2, text="开始共享", command=self._start_share)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(row2, text="停止共享", command=self._stop_share, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        self.host_info = tk.Label(row2, text=f"本机 IP: {local_ip()}", fg="#475569")
        self.host_info.pack(side=tk.LEFT, padx=16)
        self.viewer_count = tk.Label(row2, text="观看人数: 0")
        self.viewer_count.pack(side=tk.LEFT)

    def _build_viewer_panel(self):
        outer = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=4)
        outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        left = ttk.LabelFrame(outer, text="局域网内的共享电脑")
        outer.add(left, width=280)

        self.host_tree = ttk.Treeview(
            left, columns=("name", "ip", "port"), show="headings", height=12, selectmode="browse"
        )
        self.host_tree.heading("name", text="名称")
        self.host_tree.heading("ip", text="IP")
        self.host_tree.heading("port", text="端口")
        self.host_tree.column("name", width=90)
        self.host_tree.column("ip", width=100)
        self.host_tree.column("port", width=50)
        self.host_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.host_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.host_tree.bind("<Double-1>", lambda _e: self._connect_selected())
        self.host_tree.bind("<ButtonRelease-1>", self._on_tree_select)

        btns = tk.Frame(left)
        btns.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(btns, text="连接选中", command=self._connect_selected).pack(side=tk.LEFT)
        ttk.Button(btns, text="手动输入 IP…", command=self._connect_manual).pack(side=tk.LEFT, padx=6)

        right = ttk.LabelFrame(outer, text="远程画面")
        outer.add(right)

        self.viewer = RemoteViewer(right)
        self.viewer.start_polling()

    def _start_share(self):
        try:
            port = int(self.port_var.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("端口无效", "请输入 1–65535 之间的端口")
            return

        self.host.device_name = self.name_var.get().strip() or socket.gethostname()
        self.host.port = port
        self.host.password = self.pin_var.get().strip()
        self.host.allow_control = self.control_var.get()
        self._persist_prefs()

        ok, addr = self.host.start()
        if not ok:
            messagebox.showwarning("提示", addr)
            return

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.host_info.config(text=f"共享地址: {addr}  （局域网内输入此地址连接）")
        self._tick_host_status()

    def _stop_share(self):
        self.host.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.host_info.config(text=f"本机 IP: {local_ip()}")
        self.viewer_count.config(text="观看人数: 0")

    def _tick_host_status(self):
        if self.host.running:
            self.viewer_count.config(text=f"观看人数: {self.host.client_count}")
            self.root.after(1000, self._tick_host_status)

    def _connect_selected(self):
        key = self._tree_target_key()
        if not key:
            messagebox.showinfo("提示", "请先在列表中单击选中一台电脑（不要选本机）")
            return
        _name, ip, port = self.host_tree.item(key, "values")
        if ip == local_ip():
            messagebox.showwarning(
                "提示",
                "这是本机（正在共享的那台），不能连自己。\n请选择列表里另一台电脑的 IP。",
            )
            return
        pin = simpledialog.askstring("连接密码", "若对方设置了密码请输入（无则留空）:", show="*")
        if pin is None:
            return
        self.viewer.connect(str(ip), int(port), pin or "")

    def _persist_prefs(self):
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            port = DEFAULT_PORT
        app_settings.save(
            {
                "device_name": self.name_var.get().strip(),
                "port": port,
                "password": self.pin_var.get().strip(),
                "allow_control": self.control_var.get(),
                "auto_share": self.auto_share_var.get(),
            }
        )

    def _on_boot_toggle(self):
        ok, err = win_startup.set_enabled(self.boot_var.get(), self.auto_share_var.get())
        if not ok:
            self.boot_var.set(False)
            messagebox.showerror("开机自启", f"无法写入启动项：{err}\n\n打包后的 LanShare.exe 在 Windows 上可正常使用。")

    def _on_auto_share_toggle(self):
        self._persist_prefs()
        if self.boot_var.get():
            ok, err = win_startup.set_enabled(True, self.auto_share_var.get())
            if not ok:
                messagebox.showerror("开机自启", f"无法更新启动参数：{err}")

    def _connect_manual(self):
        addr = simpledialog.askstring("手动连接", "输入 IP:端口，例如 192.168.1.10:8765")
        if not addr:
            return
        if ":" in addr:
            ip, port_s = addr.rsplit(":", 1)
            try:
                port = int(port_s)
            except ValueError:
                messagebox.showerror("格式错误", "端口必须是数字")
                return
        else:
            ip, port = addr, DEFAULT_PORT
        pin = simpledialog.askstring("连接密码", "若对方设置了密码请输入（无则留空）:", show="*")
        if pin is None:
            return
        self.viewer.connect(ip.strip(), port, pin or "")

    def _on_close(self):
        self._persist_prefs()
        self._disc_stop.set()
        self.host.stop()
        self.viewer.disconnect()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if sys.platform != "win32":
        print("本程序面向 Windows 设计；在其他系统上可能无法捕获屏幕或注入键鼠。")
    auto = win_startup.parse_auto_share_flag()
    LanShareApp(auto_share=auto).run()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
