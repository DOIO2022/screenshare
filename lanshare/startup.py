"""Windows login startup (registry Run key)."""

import os
import sys

APP_NAME = "LanShare"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTO_SHARE_FLAG = "--auto-share"


def launch_executable() -> str:
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0])


def launch_command(auto_share: bool = False) -> str:
    exe = launch_executable()
    cmd = f'"{exe}"'
    if auto_share:
        cmd += f" {_AUTO_SHARE_FLAG}"
    if not getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}" {cmd}'
    return cmd


def is_supported() -> bool:
    return sys.platform == "win32"


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool, auto_share: bool = False) -> tuple[bool, str]:
    if not is_supported():
        return False, "仅支持 Windows"

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command(auto_share))
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except OSError:
                    pass
        return True, ""
    except OSError as exc:
        return False, str(exc)


def parse_auto_share_flag(argv: list[str] | None = None) -> bool:
    args = argv if argv is not None else sys.argv
    return _AUTO_SHARE_FLAG in args
