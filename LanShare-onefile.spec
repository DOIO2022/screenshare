# Single-file exe — all libraries bundled inside LanShare.exe (no pip on target PC).
# Build: pyinstaller --noconfirm LanShare-onefile.spec

block_cipher = None

hidden = [
    "PIL._tkinter_finder",
    "asyncio",
    "cv2",
    "numpy",
    "mss",
    "mss.windows",
    "websockets",
    "websockets.asyncio",
    "websockets.asyncio.server",
    "websockets.asyncio.client",
    "websockets.legacy",
    "websockets.legacy.server",
    "websockets.legacy.client",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("使用说明.txt", ".")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="LanShare",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
