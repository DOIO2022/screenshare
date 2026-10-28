@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === LanShare one-file build ===
echo.

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    echo Python not found. Install Python or run Build-LanShare.ps1
    pause
    exit /b 1
)

%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller
if exist build rmdir /s /q build
%PY% -m PyInstaller --noconfirm --clean LanShare-onefile.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo OK: dist\LanShare.exe
pause
endlocal
