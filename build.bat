@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === LanShare Windows build ===
echo Python is only needed ONCE on this PC to create the green portable exe.
echo.

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    echo Python not found.
    echo.
    echo Option 1: Install Python 3.10+ from https://www.python.org/
    echo           Check "Add python.exe to PATH" during setup, then run this again.
    echo.
    echo Option 2: Right-click Build-LanShare.ps1 -^> Run with PowerShell
    echo           It can download portable Python into this folder automatically.
    echo.
    pause
    exit /b 1
)

echo Using: %PY%
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
%PY% -m PyInstaller --noconfirm --clean LanShare.spec
if errorlevel 1 (
    echo PyInstaller failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo OK: dist\LanShare-win32-x64\LanShare.exe
echo Copy the whole LanShare-win32-x64 folder to other PCs.
echo No Python needed on those PCs.
echo ========================================
pause
endlocal
