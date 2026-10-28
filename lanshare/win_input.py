"""Windows mouse/keyboard injection via SendInput (more reliable than pynput for remote control)."""

import sys

if sys.platform != "win32":
    raise RuntimeError("win_input is Windows-only")

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


_VK = {
    "enter": 0x0D,
    "backspace": 0x08,
    "tab": 0x09,
    "space": 0x20,
    "escape": 0x1B,
    "delete": 0x2E,
    "ctrl": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}


def _vk(key: str) -> int | None:
    k = key.lower()
    if k in _VK:
        return _VK[k]
    if len(k) == 1:
        return _user32.VkKeyScanW(ord(k.upper())) & 0xFF
    return None


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    _user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))


def move_to(x: int, y: int):
    _user32.SetCursorPos(int(x), int(y))


def mouse_button(button: str, down: bool):
    if button == "l":
        flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    else:
        flag = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
    inp = INPUT(type=INPUT_MOUSE, u=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, flag, 0, None)))
    _send([inp])


def scroll(dy: int):
    inp = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(mi=MOUSEINPUT(0, 0, int(dy * WHEEL_DELTA), MOUSEEVENTF_WHEEL, 0, None)),
    )
    _send([inp])


def key_action(key: str, down: bool):
    vk = _vk(key)
    if vk is None:
        return
    flags = 0 if down else KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags, 0, None)))
    _send([inp])


def handle(cmd: dict, origin_x: int, origin_y: int, width: int, height: int):
    t = cmd.get("t")
    x = origin_x + int(float(cmd.get("x", 0)) * width)
    y = origin_y + int(float(cmd.get("y", 0)) * height)

    if t == "mm":
        move_to(x, y)
    elif t == "mc":
        move_to(x, y)
        mouse_button(str(cmd.get("b", "l")), bool(cmd.get("d")))
    elif t == "ms":
        move_to(x, y)
        scroll(int(cmd.get("dy", 0)))
    elif t == "kp":
        key_action(str(cmd.get("k", "")), True)
    elif t == "kr":
        key_action(str(cmd.get("k", "")), False)
